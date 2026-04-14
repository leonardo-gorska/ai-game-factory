"""
GORVAX GAME FACTORY — Auto-Fixer (Rule-Based Build Error Fixes)

Applies deterministic fixes for common build errors WITHOUT spending
an LLM call.  Works with the ``ClassifiedError`` objects produced by
``build_error_classifier.py``.

Roadmap v2 Item #1.
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class FixResult:
    """Result of an auto-fix attempt."""

    fixed: bool
    file: str = ""
    description: str = ""
    original_line: int | None = None
    rule: str = ""


@dataclass
class AutoFixReport:
    """Aggregate result of all auto-fix attempts for a build cycle."""

    fixes: list[FixResult] = field(default_factory=list)

    @property
    def any_fixed(self) -> bool:
        return any(f.fixed for f in self.fixes)

    @property
    def count(self) -> int:
        return sum(1 for f in self.fixes if f.fixed)

    @property
    def summary(self) -> str:
        if not self.any_fixed:
            return "Nenhum fix automático aplicado"
        items = [f"  - {f.description} ({f.file}:{f.original_line})" for f in self.fixes if f.fixed]
        return f"🔧 Auto-Fix: {self.count} correções aplicadas:\n" + "\n".join(items)


# ── Fix Rules ─────────────────────────────────────────────

def _fix_missing_semicolon(
    content: str, error_line: int | None,
) -> tuple[str, bool]:
    """Add missing semicolon at the end of a line."""
    if error_line is None:
        return content, False

    lines = content.splitlines(keepends=True)
    idx = error_line - 1
    if idx < 0 or idx >= len(lines):
        return content, False

    stripped = lines[idx].rstrip()
    # Don't add semicolon after block openers/closers or comments
    if stripped and not stripped.endswith((";", "{", "}", "//", "*/", ",")):
        # Preserve trailing whitespace/newline
        trailing = lines[idx][len(stripped):]
        lines[idx] = stripped + ";" + trailing
        return "".join(lines), True

    return content, False


def _fix_trailing_comma(
    content: str, error_line: int | None,
) -> tuple[str, bool]:
    """Remove trailing comma before closing bracket/brace/paren."""
    if error_line is None:
        return content, False

    lines = content.splitlines(keepends=True)
    idx = error_line - 1
    if idx < 0 or idx >= len(lines):
        return content, False

    # Look for pattern: something, } or , ] or , )
    line = lines[idx]
    fixed = re.sub(r",(\s*[}\])])", r"\1", line)
    if fixed != line:
        lines[idx] = fixed
        return "".join(lines), True

    # Also check if the comma is on the previous line
    if idx > 0:
        prev = lines[idx - 1]
        if prev.rstrip().endswith(",") and lines[idx].strip().startswith(("}", "]", ")")):
            lines[idx - 1] = prev.rstrip().rstrip(",") + "\n"
            return "".join(lines), True

    return content, False


def _fix_double_semicolon(
    content: str, error_line: int | None,
) -> tuple[str, bool]:
    """Replace ;; with ;."""
    if error_line is None:
        # Scan entire file
        if ";;" in content:
            # Avoid modifying for-loops
            lines = content.splitlines(keepends=True)
            changed = False
            for i, line in enumerate(lines):
                if ";;" in line and "for" not in line.lower():
                    lines[i] = line.replace(";;", ";")
                    changed = True
            if changed:
                return "".join(lines), True
        return content, False

    lines = content.splitlines(keepends=True)
    idx = error_line - 1
    if idx < 0 or idx >= len(lines):
        return content, False

    if ";;" in lines[idx] and "for" not in lines[idx].lower():
        lines[idx] = lines[idx].replace(";;", ";")
        return "".join(lines), True

    return content, False


def _fix_unused_import(
    content: str, error_line: int | None,
) -> tuple[str, bool]:
    """Remove an unused import line entirely."""
    if error_line is None:
        return content, False

    lines = content.splitlines(keepends=True)
    idx = error_line - 1
    if idx < 0 or idx >= len(lines):
        return content, False

    line = lines[idx].strip()
    if line.startswith(("import ", "import{")) or "require(" in line:
        lines[idx] = ""
        return "".join(lines), True

    return content, False


def _fix_duplicate_declaration(
    content: str, error_line: int | None,
) -> tuple[str, bool]:
    """Convert duplicate const/let to assignment (remove const/let keyword)."""
    if error_line is None:
        return content, False

    lines = content.splitlines(keepends=True)
    idx = error_line - 1
    if idx < 0 or idx >= len(lines):
        return content, False

    line = lines[idx]
    # Replace 'const X =' or 'let X =' with just 'X ='
    fixed = re.sub(
        r"^(\s*)(?:const|let|var)\s+(\w+\s*=)",
        r"\1\2",
        line,
    )
    if fixed != line:
        lines[idx] = fixed
        return "".join(lines), True

    return content, False


# ── Mapping: error category + pattern → fix function ──────

_FIX_RULES: list[dict[str, Any]] = [
    {
        "name": "missing_semicolon",
        "category": "syntax",
        "patterns": [r"missing semicolon", r"Missing semicolon"],
        "fixer": _fix_missing_semicolon,
    },
    {
        "name": "trailing_comma",
        "category": "syntax",
        "patterns": [r"trailing comma", r"Trailing comma", r"Unexpected token.*[}\])]"],
        "fixer": _fix_trailing_comma,
    },
    {
        "name": "double_semicolon",
        "category": "syntax",
        "patterns": [r"Unexpected token ;", r"empty statement"],
        "fixer": _fix_double_semicolon,
    },
    {
        "name": "unused_import",
        "category": "import",
        "patterns": [r"is defined but never used", r"no-unused-vars.*import"],
        "fixer": _fix_unused_import,
    },
    {
        "name": "duplicate_declaration",
        "category": "syntax",
        "patterns": [r"already been declared", r"Identifier.*has already been declared", r"redeclaration"],
        "fixer": _fix_duplicate_declaration,
    },
]


# ── Main entry point ──────────────────────────────────────

def try_auto_fix(
    errors: list[dict[str, Any]],
    files: dict[str, str],
    error_db: Any | None = None,
) -> tuple[dict[str, str], AutoFixReport]:
    """Try to auto-fix classified build errors without LLM.

    Args:
        errors: List of classified error dicts with keys:
            ``category``, ``message``, ``file``, ``line``.
        files: Mapping of filepath → file content (will be modified in-place
            for fixed files).
        error_db: Optional ``ErrorPatternDB`` instance.  When provided,
            known patterns are tried **before** static rules.

    Returns:
        Tuple of (updated files dict, AutoFixReport).
    """
    report = AutoFixReport()
    modified_files = dict(files)  # shallow copy

    for error in errors:
        msg = error.get("message", "")
        category = error.get("category", "")
        error_file = error.get("file", "")
        error_line = error.get("line")

        if not error_file or error_file not in modified_files:
            continue

        # ── Priority 1: Error Pattern DB lookup ──
        if error_db is not None:
            db_match = error_db.lookup(msg, category)
            if db_match and db_match.fix_code:
                result = FixResult(
                    fixed=True,
                    file=error_file,
                    description=f"error_db: {db_match.fix_description}",
                    original_line=error_line,
                    rule="error_db",
                )
                report.fixes.append(result)
                logger.info(
                    "📚 Error DB fix [%s]: %s:%s",
                    db_match.fix_description, error_file, error_line,
                )
                continue  # Skip static rules for this error

        # ── Priority 2: Static rules ──
        for rule in _FIX_RULES:
            # Match by category (if specified) and message pattern
            if rule["category"] and category and rule["category"] != category:
                continue

            matched = any(
                re.search(pat, msg, re.IGNORECASE)
                for pat in rule["patterns"]
            )
            if not matched:
                continue

            content = modified_files[error_file]
            new_content, fixed = rule["fixer"](content, error_line)

            result = FixResult(
                fixed=fixed,
                file=error_file,
                description=rule["name"],
                original_line=error_line,
                rule=rule["name"],
            )
            report.fixes.append(result)

            if fixed:
                modified_files[error_file] = new_content
                logger.info(
                    "🔧 Auto-fix [%s]: %s:%s",
                    rule["name"], error_file, error_line,
                )
            break  # One rule per error

    if report.any_fixed:
        logger.info(report.summary)

    return modified_files, report
