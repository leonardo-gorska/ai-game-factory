"""
GORVAX GAME FACTORY — Code Quality Gate

Pre-build static analysis for JavaScript/TypeScript files.
Catches obvious errors (syntax, unresolved imports, bracket mismatches)
BEFORE spending time on a full build, giving instant feedback.

Roadmap v2 Item #2.
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ── Issue severity ────────────────────────────────────────

SEVERITY_ERROR = "error"
SEVERITY_WARNING = "warning"


@dataclass
class GateIssue:
    """A single issue found by the quality gate."""

    file: str
    line: int | None
    severity: str              # SEVERITY_ERROR | SEVERITY_WARNING
    rule: str                  # e.g. "bracket_balance", "unresolved_import"
    message: str
    fix_hint: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "file": self.file,
            "line": self.line,
            "severity": self.severity,
            "rule": self.rule,
            "message": self.message,
            "fix_hint": self.fix_hint,
        }


@dataclass
class GateResult:
    """Result of a quality gate check."""

    passed: bool
    issues: list[GateIssue] = field(default_factory=list)

    @property
    def blocking(self) -> list[GateIssue]:
        """Issues with severity=error that would definitely break the build."""
        return [i for i in self.issues if i.severity == SEVERITY_ERROR]

    @property
    def warnings(self) -> list[GateIssue]:
        return [i for i in self.issues if i.severity == SEVERITY_WARNING]

    def to_developer_prompt(self) -> str:
        """Format issues for the Developer agent."""
        if not self.issues:
            return ""
        lines = ["🚧 Quality Gate encontrou problemas PRÉ-BUILD:\n"]
        for i, issue in enumerate(self.issues, 1):
            loc = f"{issue.file}"
            if issue.line:
                loc += f":{issue.line}"
            label = "❌" if issue.severity == SEVERITY_ERROR else "⚠️"
            lines.append(f"{i}. {label} [{issue.rule}] {loc}")
            lines.append(f"   {issue.message}")
            if issue.fix_hint:
                lines.append(f"   💡 {issue.fix_hint}")
        return "\n".join(lines)


# ── Individual checks ─────────────────────────────────────

def _check_bracket_balance(
    filepath: str, content: str,
) -> list[GateIssue]:
    """Detect unmatched brackets, braces, and parentheses."""
    issues: list[GateIssue] = []
    openers = {"(": ")", "[": "]", "{": "}"}
    closers = {v: k for k, v in openers.items()}
    stack: list[tuple[str, int]] = []

    # Strip strings and comments to avoid false positives
    cleaned = _strip_strings_and_comments(content)

    for line_num, line in enumerate(cleaned.splitlines(), 1):
        for ch in line:
            if ch in openers:
                stack.append((ch, line_num))
            elif ch in closers:
                if not stack:
                    issues.append(GateIssue(
                        file=filepath,
                        line=line_num,
                        severity=SEVERITY_ERROR,
                        rule="bracket_balance",
                        message=f"'{ch}' sem abertura correspondente",
                        fix_hint=f"Adicione '{closers[ch]}' antes desta linha ou remova '{ch}'",
                    ))
                elif stack[-1][0] != closers[ch]:
                    expected = openers[stack[-1][0]]
                    issues.append(GateIssue(
                        file=filepath,
                        line=line_num,
                        severity=SEVERITY_ERROR,
                        rule="bracket_balance",
                        message=f"Esperava '{expected}' mas encontrou '{ch}'",
                        fix_hint=f"Verifique o bloco que começa na linha {stack[-1][1]}",
                    ))
                    stack.pop()
                else:
                    stack.pop()

    for opener, line_num in stack:
        issues.append(GateIssue(
            file=filepath,
            line=line_num,
            severity=SEVERITY_ERROR,
            rule="bracket_balance",
            message=f"'{opener}' aberto na linha {line_num} nunca foi fechado",
            fix_hint=f"Adicione '{openers[opener]}' no final do bloco",
        ))

    return issues


def _check_import_resolution(
    filepath: str,
    content: str,
    all_files: dict[str, str],
    src_root: Path | None = None,
) -> list[GateIssue]:
    """Check that relative imports point to existing files."""
    issues: list[GateIssue] = []
    import_pattern = re.compile(
        r"""(?:import\s+.*?from\s+|require\s*\(\s*)['"](\.[^'"]+)['"]""",
    )

    file_path = Path(filepath)
    file_dir = file_path.parent

    for line_num, line in enumerate(content.splitlines(), 1):
        for match in import_pattern.finditer(line):
            import_path = match.group(1)
            # Resolve relative to the importing file
            target = (file_dir / import_path).resolve()
            # Try common extensions
            candidates = [
                target,
                target.with_suffix(".js"),
                target.with_suffix(".jsx"),
                target.with_suffix(".ts"),
                target.with_suffix(".tsx"),
                target / "index.js",
                target / "index.ts",
            ]

            # Also check against the keys in all_files
            target_str = str(target).replace("\\", "/")
            found = any(
                str(c).replace("\\", "/") in all_files
                or c.exists()
                for c in candidates
            )
            if not found:
                # Check with normalized keys
                norm_candidates = [
                    str(c).replace("\\", "/") for c in candidates
                ]
                found = any(
                    any(k.endswith(nc.split("/src/")[-1]) for k in all_files)
                    for nc in norm_candidates
                    if "/src/" in nc
                )

            if not found:
                issues.append(GateIssue(
                    file=filepath,
                    line=line_num,
                    severity=SEVERITY_ERROR,
                    rule="unresolved_import",
                    message=f"Import '{import_path}' não resolve para nenhum arquivo",
                    fix_hint="Verifique o caminho ou crie o arquivo",
                ))

    return issues


def _check_duplicate_declarations(
    filepath: str, content: str,
) -> list[GateIssue]:
    """Detect duplicate const/let/var/function declarations in the same scope level."""
    issues: list[GateIssue] = []
    # Simple top-level declaration detector (not full AST, but catches common cases)
    decl_pattern = re.compile(
        r"^(?:export\s+)?(?:const|let|var|function|class)\s+(\w+)",
        re.MULTILINE,
    )
    seen: dict[str, int] = {}
    for line_num, line in enumerate(content.splitlines(), 1):
        m = decl_pattern.match(line.strip())
        if m:
            name = m.group(1)
            if name in seen:
                issues.append(GateIssue(
                    file=filepath,
                    line=line_num,
                    severity=SEVERITY_ERROR,
                    rule="duplicate_declaration",
                    message=f"'{name}' já declarado na linha {seen[name]}",
                    fix_hint="Renomeie uma das declarações ou remova a duplicata",
                ))
            else:
                seen[name] = line_num

    return issues


def _check_syntax_basics(
    filepath: str, content: str,
) -> list[GateIssue]:
    """Catch basic syntax problems without a full parser."""
    issues: list[GateIssue] = []
    cleaned = _strip_strings_and_comments(content)

    for line_num, line in enumerate(cleaned.splitlines(), 1):
        stripped = line.rstrip()
        if not stripped:
            continue

        # Unterminated template literal (backtick count should be even)
        backtick_count = stripped.count("`")
        if backtick_count % 2 != 0:
            # Could be multi-line template — only flag if line has other issues
            pass

        # Double semicolons
        if ";;" in stripped and "for" not in stripped:
            issues.append(GateIssue(
                file=filepath,
                line=line_num,
                severity=SEVERITY_WARNING,
                rule="double_semicolon",
                message="Ponto-e-vírgula duplicado",
                fix_hint="Remova o ponto-e-vírgula extra",
            ))

        # Assignment in condition (common bug)
        cond_match = re.search(r"\b(?:if|while)\s*\(([^)]+)\)", stripped)
        if cond_match:
            cond = cond_match.group(1)
            # Single = that isn't == or === or !=
            if re.search(r"(?<![!=<>])=(?!=)", cond):
                issues.append(GateIssue(
                    file=filepath,
                    line=line_num,
                    severity=SEVERITY_WARNING,
                    rule="assignment_in_condition",
                    message="Possível atribuição em condição (usou '=' em vez de '==' ou '===')",
                    fix_hint="Use '===' para comparação",
                ))

    return issues


# ── Main entry point ──────────────────────────────────────

def run_quality_gate(
    files: dict[str, str],
    src_root: Path | None = None,
) -> GateResult:
    """Run all quality checks on the given source files.

    Args:
        files: Mapping of filepath → file content.
        src_root: Optional root directory for import resolution.

    Returns:
        GateResult with all found issues.
    """
    all_issues: list[GateIssue] = []

    js_extensions = {".js", ".jsx", ".ts", ".tsx", ".mjs"}

    for filepath, content in files.items():
        ext = Path(filepath).suffix.lower()
        if ext not in js_extensions:
            continue

        all_issues.extend(_check_bracket_balance(filepath, content))
        all_issues.extend(_check_import_resolution(filepath, content, files, src_root))
        all_issues.extend(_check_duplicate_declarations(filepath, content))
        all_issues.extend(_check_syntax_basics(filepath, content))

    passed = not any(i.severity == SEVERITY_ERROR for i in all_issues)

    if all_issues:
        logger.info(
            "🚧 Quality Gate: %d issues (%d blocking, %d warnings)",
            len(all_issues),
            sum(1 for i in all_issues if i.severity == SEVERITY_ERROR),
            sum(1 for i in all_issues if i.severity == SEVERITY_WARNING),
        )
    else:
        logger.debug("✅ Quality Gate: all checks passed")

    return GateResult(passed=passed, issues=all_issues)


# ── Utilities ─────────────────────────────────────────────

def _strip_strings_and_comments(source: str) -> str:
    """Remove string literals and comments to avoid false positives.

    Replaces string contents and comment text with spaces (preserving
    line structure) so bracket-matching and other checks don't trigger
    inside strings or comments.
    """
    result: list[str] = []
    i = 0
    in_template = False
    length = len(source)

    while i < length:
        ch = source[i]

        # Single-line comment
        if ch == "/" and i + 1 < length and source[i + 1] == "/":
            # Skip to end of line
            while i < length and source[i] != "\n":
                result.append(" ")
                i += 1
            continue

        # Multi-line comment
        if ch == "/" and i + 1 < length and source[i + 1] == "*":
            result.append(" ")
            result.append(" ")
            i += 2
            while i < length:
                if source[i] == "*" and i + 1 < length and source[i + 1] == "/":
                    result.append(" ")
                    result.append(" ")
                    i += 2
                    break
                result.append("\n" if source[i] == "\n" else " ")
                i += 1
            continue

        # String literals (single/double quote)
        if ch in ("'", '"'):
            quote = ch
            result.append(ch)
            i += 1
            while i < length and source[i] != quote:
                if source[i] == "\\" and i + 1 < length:
                    result.append(" ")
                    result.append(" ")
                    i += 2
                    continue
                if source[i] == "\n":
                    break  # unterminated string
                result.append(" ")
                i += 1
            if i < length:
                result.append(ch)
                i += 1
            continue

        # Template literal
        if ch == "`":
            result.append(ch)
            i += 1
            while i < length and source[i] != "`":
                if source[i] == "\\" and i + 1 < length:
                    result.append(" ")
                    result.append(" ")
                    i += 2
                    continue
                if source[i] == "\n":
                    result.append("\n")
                else:
                    result.append(" ")
                i += 1
            if i < length:
                result.append(ch)
                i += 1
            continue

        result.append(ch)
        i += 1

    return "".join(result)
