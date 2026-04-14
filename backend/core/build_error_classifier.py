"""
Build Error Classifier — Categorizes build/lint errors for targeted fixes.

Parses raw ESLint/Vite output and produces structured error dicts
so the Developer agent gets actionable, categorized diagnostics.
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# ── Error categories ─────────────────────────────────────

CATEGORY_IMPORT  = "import"
CATEGORY_SYNTAX  = "syntax"
CATEGORY_TYPE    = "type"
CATEGORY_RUNTIME = "runtime"
CATEGORY_CONFIG  = "config"
CATEGORY_UNKNOWN = "unknown"

# Patterns mapped to categories
_PATTERNS: list[tuple[str, str, str]] = [
    # (regex, category, fix_hint)
    (r"Cannot find module ['\"](.*?)['\"]",
     CATEGORY_IMPORT,
     "Verifique se o arquivo existe ou remova o import"),
    (r"Module not found.*['\"](.*?)['\"]",
     CATEGORY_IMPORT,
     "Crie o módulo ou corrija o caminho de importação"),
    (r"is not exported from",
     CATEGORY_IMPORT,
     "Verifique os exports do módulo importado"),
    (r"Unexpected token",
     CATEGORY_SYNTAX,
     "Corrija a sintaxe — provavelmente falta }, ) ou ;"),
    (r"Parsing error",
     CATEGORY_SYNTAX,
     "Erro de parsing — verifique chaves e parênteses"),
    (r"Unterminated string",
     CATEGORY_SYNTAX,
     "Feche a string com a aspa correspondente"),
    (r"Missing semicolon",
     CATEGORY_SYNTAX,
     "Adicione ponto-e-vírgula no final da linha"),
    (r"is not defined",
     CATEGORY_RUNTIME,
     "A variável/função não foi declarada — importe ou declare-a"),
    (r"is not a function",
     CATEGORY_TYPE,
     "Verifique a assinatura do método ou o tipo do objeto"),
    (r"Cannot read propert",
     CATEGORY_RUNTIME,
     "O objeto pode ser null/undefined — adicione checagem"),
    (r"'.*?' is defined but never used",
     CATEGORY_RUNTIME,
     "Remova a variável/import não utilizado"),
    (r"vite.*config",
     CATEGORY_CONFIG,
     "Problema na configuração do Vite — verifique vite.config.js"),
]

# File + line extraction: "src/systems/Foo.js:10:5" or "src/systems/Foo.js(10,5)"
_FILE_LINE_RE = re.compile(
    r"(?:^|\s)((?:src|game)[/\\]\S+\.js)[:\(](\d+)",
    re.MULTILINE,
)


@dataclass
class ClassifiedError:
    """A single classified build error."""
    category: str
    file: str
    line: int
    message: str
    fix_hint: str

    def to_dict(self) -> dict[str, str | int]:
        return {
            "category": self.category,
            "file": self.file,
            "line": self.line,
            "message": self.message,
            "fix_hint": self.fix_hint,
        }


@dataclass
class ClassificationResult:
    """Result of classifying build errors."""
    errors: list[ClassifiedError] = field(default_factory=list)
    summary: str = ""
    broken_files: set[str] = field(default_factory=set)

    @property
    def has_errors(self) -> bool:
        return len(self.errors) > 0

    def category_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for e in self.errors:
            counts[e.category] = counts.get(e.category, 0) + 1
        return counts

    def to_developer_prompt(self, diff: "ErrorDiffResult | None" = None) -> str:
        """Format errors as a structured prompt section for the Developer agent.

        If *diff* is provided, errors are labeled as [NOVO] or [PERSISTENTE]
        and a resolved-count line is included so the Developer can focus on
        what actually changed since the last build.
        """
        if not self.errors:
            return ""

        counts = self.category_counts()
        parts = [
            "## 🔍 Erros Classificados do Build\n",
            f"Total: {len(self.errors)} erro(s) em {len(self.broken_files)} arquivo(s)\n",
            "Categorias: " + ", ".join(
                f"{cat}={n}" for cat, n in sorted(counts.items(), key=lambda x: -x[1])
            ) + "\n",
        ]

        # Diff summary when available
        if diff is not None:
            parts.append(
                f"🆕 Novos: {len(diff.new)} | 🔄 Persistentes: {len(diff.persistent)}"
                f" | ✅ Resolvidos: {diff.resolved_count}\n"
            )

        # Build a set of "new" signatures for quick lookup
        new_sigs: set[tuple[str, int, str]] = set()
        if diff is not None:
            new_sigs = {(e.file, e.line, e.category) for e in diff.new}

        # Group by file
        by_file: dict[str, list[ClassifiedError]] = {}
        for e in self.errors:
            by_file.setdefault(e.file, []).append(e)

        for fname, errs in sorted(by_file.items()):
            parts.append(f"\n### {fname}")
            for e in errs[:5]:  # Max 5 per file to save tokens
                if diff is not None:
                    sig = (e.file, e.line, e.category)
                    label = "🆕 NOVO" if sig in new_sigs else "🔄 PERSISTENTE"
                    parts.append(
                        f"- [{label}][{e.category.upper()}] Linha {e.line}: {e.message}\n"
                        f"  → Dica: {e.fix_hint}"
                    )
                else:
                    parts.append(
                        f"- [{e.category.upper()}] Linha {e.line}: {e.message}\n"
                        f"  → Dica: {e.fix_hint}"
                    )
            if len(errs) > 5:
                parts.append(f"  ... +{len(errs) - 5} erro(s) adicional(is)")

        return "\n".join(parts)


def classify_build_errors(raw_output: str) -> ClassificationResult:
    """
    Parse raw ESLint/Vite output and return ClassificationResult.

    Returns structured errors with category, file, line, message, and fix hints.
    """
    result = ClassificationResult()

    if not raw_output or raw_output.strip() == "":
        return result

    # Split into individual error blocks (line-by-line)
    lines = raw_output.split("\n")
    current_file = "unknown"
    current_line = 0

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue

        # Try to extract file + line number
        file_match = _FILE_LINE_RE.search(line)
        if file_match:
            current_file = file_match.group(1).replace("\\", "/")
            current_line = int(file_match.group(2))
            result.broken_files.add(current_file)

        # Skip non-error lines
        if not any(kw in line.lower() for kw in ("error", "cannot", "unexpected", "missing", "not found", "not defined", "not a function", "parsing")):
            continue

        # Classify the error
        category = CATEGORY_UNKNOWN
        fix_hint = "Revise o código nesta linha"

        for pattern, cat, hint in _PATTERNS:
            if re.search(pattern, line, re.IGNORECASE):
                category = cat
                fix_hint = hint
                break

        error = ClassifiedError(
            category=category,
            file=current_file,
            line=current_line,
            message=line[:200],  # Truncate long messages
            fix_hint=fix_hint,
        )
        result.errors.append(error)

    # Deduplicate similar errors in same file
    seen: set[str] = set()
    unique_errors: list[ClassifiedError] = []
    for e in result.errors:
        key = f"{e.file}:{e.line}:{e.category}"
        if key not in seen:
            seen.add(key)
            unique_errors.append(e)
    result.errors = unique_errors

    # Build summary
    counts = result.category_counts()
    if counts:
        result.summary = (
            f"{len(result.errors)} erro(s) classificado(s): "
            + ", ".join(f"{c}={n}" for c, n in sorted(counts.items(), key=lambda x: -x[1]))
        )
        logger.info("🏷️ %s", result.summary)

    return result


# ── Build Error Diffing ──────────────────────────────────


@dataclass
class ErrorDiffResult:
    """Result of comparing errors between two consecutive builds."""
    new: list[ClassifiedError] = field(default_factory=list)
    persistent: list[ClassifiedError] = field(default_factory=list)
    resolved_count: int = 0


def diff_errors(
    previous: list[ClassifiedError],
    current: list[ClassifiedError],
) -> ErrorDiffResult:
    """Compare build errors between consecutive builds.

    Each error is identified by its (file, line, category) signature.

    Returns an ``ErrorDiffResult`` with:
    - *new*: errors present in *current* but not in *previous*
    - *persistent*: errors present in both
    - *resolved_count*: number of *previous* errors no longer in *current*
    """
    prev_sigs = {(e.file, e.line, e.category) for e in previous}
    curr_sigs = {(e.file, e.line, e.category) for e in current}

    new = [e for e in current if (e.file, e.line, e.category) not in prev_sigs]
    persistent = [e for e in current if (e.file, e.line, e.category) in prev_sigs]
    resolved_count = len(prev_sigs - curr_sigs)

    result = ErrorDiffResult(new=new, persistent=persistent, resolved_count=resolved_count)

    if previous:
        logger.info(
            "📊 Error diff: %d novo(s), %d persistente(s), %d resolvido(s)",
            len(new), len(persistent), resolved_count,
        )

    return result
