"""
GORVAX GAME FACTORY — Diff Analyzer
Analisa risco de mudanças no código entre iterações.
Gera risk_score que penaliza o quality score quando há mudanças perigosas.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from backend.config import GAME_DIR

logger = logging.getLogger(__name__)

# Arquivos considerados críticos (mudanças aqui são de alto risco)
CRITICAL_FILES = {
    "main.js", "config.js", "BootScene.js",
}

# Padrões que indicam código potencialmente perigoso
RISKY_PATTERNS = [
    (r"while\s*\(\s*true\s*\)", "infinite loop"),
    (r"eval\s*\(", "eval usage"),
    (r"setTimeout\s*\([^,]+,\s*0\s*\)", "zero timeout"),
    (r"\.innerHTML\s*=", "innerHTML assignment"),
    (r"delete\s+", "delete operator"),
]


@dataclass
class DiffReport:
    """Relatório de análise de diff."""
    # Métricas de mudança
    files_added: int = 0
    files_modified: int = 0
    files_deleted: int = 0
    lines_added: int = 0
    lines_removed: int = 0
    total_churn: int = 0  # added + removed

    # Risco
    critical_files_touched: list[str] = field(default_factory=list)
    risky_patterns_found: list[str] = field(default_factory=list)
    cyclomatic_complexity: float = 0.0  # estimativa
    bundle_size_delta_kb: float = 0.0

    # Score
    risk_score: float = 0.0  # 0-100 (0=seguro, 100=perigoso)
    risk_level: str = "low"  # low, medium, high, critical

    def to_dict(self) -> dict[str, Any]:
        return {
            "files_added": self.files_added,
            "files_modified": self.files_modified,
            "files_deleted": self.files_deleted,
            "lines_added": self.lines_added,
            "lines_removed": self.lines_removed,
            "total_churn": self.total_churn,
            "critical_files_touched": self.critical_files_touched,
            "risky_patterns_found": self.risky_patterns_found,
            "cyclomatic_complexity": self.cyclomatic_complexity,
            "risk_score": self.risk_score,
            "risk_level": self.risk_level,
        }


class DiffAnalyzer:
    """
    Analisa mudanças no código entre iterações.
    Calcula risk_score baseado em:
    - Volume de mudanças (churn)
    - Arquivos críticos tocados
    - Padrões de código perigosos
    - Complexidade ciclomática estimada
    """

    def __init__(self, game_dir: Path | None = None) -> None:
        self._game_dir = game_dir or GAME_DIR

    def analyze(
        self,
        previous_files: dict[str, str],
        current_files: dict[str, str],
    ) -> DiffReport:
        """
        Compara dois snapshots de arquivos e gera relatório de risco.

        Args:
            previous_files: {path: content} da iteração anterior
            current_files: {path: content} da iteração atual

        Returns:
            DiffReport com métricas e risk_score
        """
        report = DiffReport()

        all_paths = set(previous_files.keys()) | set(current_files.keys())

        for path in all_paths:
            prev = previous_files.get(path, "")
            curr = current_files.get(path, "")

            if not prev and curr:
                # Arquivo novo
                report.files_added += 1
                report.lines_added += curr.count("\n") + 1
            elif prev and not curr:
                # Arquivo deletado
                report.files_deleted += 1
                report.lines_removed += prev.count("\n") + 1
                # Deletar é arriscado
                basename = Path(path).name
                if basename in CRITICAL_FILES:
                    report.critical_files_touched.append(f"DELETED: {basename}")
            elif prev != curr:
                # Arquivo modificado
                report.files_modified += 1
                added, removed = self._count_line_changes(prev, curr)
                report.lines_added += added
                report.lines_removed += removed

                basename = Path(path).name
                if basename in CRITICAL_FILES:
                    report.critical_files_touched.append(basename)

        report.total_churn = report.lines_added + report.lines_removed

        # Análise de padrões perigosos no código atual
        for path, content in current_files.items():
            for pattern, desc in RISKY_PATTERNS:
                if re.search(pattern, content):
                    report.risky_patterns_found.append(
                        f"{Path(path).name}: {desc}"
                    )

        # Complexidade ciclomática estimada
        report.cyclomatic_complexity = self._estimate_complexity(current_files)

        # Bundle size delta estimado (1 linha ≈ 0.05 KB)
        prev_lines = sum(c.count("\n") for c in previous_files.values())
        curr_lines = sum(c.count("\n") for c in current_files.values())
        report.bundle_size_delta_kb = (curr_lines - prev_lines) * 0.05

        # Calcular risk score
        report.risk_score = self._compute_risk_score(report)
        report.risk_level = self._classify_risk(report.risk_score)

        logger.info(
            "📊 Diff: +%d/-%d lines | %d files | risk=%.0f (%s) | "
            "critical=%d | risky_patterns=%d",
            report.lines_added, report.lines_removed,
            report.files_modified,
            report.risk_score, report.risk_level,
            len(report.critical_files_touched),
            len(report.risky_patterns_found),
        )

        return report

    def generate_diff(
        self,
        previous_files: dict[str, str],
        current_files: dict[str, str],
        max_chars: int = 6000,
    ) -> str:
        """Generate unified diff text between two file snapshots.

        Args:
            previous_files: {path: content} from the previous iteration.
            current_files: {path: content} from the current iteration.
            max_chars: Maximum characters in the output (prevents token bloat).

        Returns:
            Unified diff string, or empty string if no changes.
        """
        import difflib

        all_paths = sorted(set(previous_files.keys()) | set(current_files.keys()))
        diffs: list[str] = []

        for path in all_paths:
            old = previous_files.get(path, "")
            new = current_files.get(path, "")
            if old == new:
                continue

            old_lines = old.splitlines(keepends=True)
            new_lines = new.splitlines(keepends=True)
            diff_lines = difflib.unified_diff(
                old_lines, new_lines,
                fromfile=f"old/{path}", tofile=f"new/{path}",
                lineterm="",
            )
            diff_text = "\n".join(diff_lines)
            if diff_text:
                diffs.append(diff_text)

        result = "\n---\n".join(diffs)
        if len(result) > max_chars:
            result = result[:max_chars] + "\n... [truncated]"
        return result

    def _count_line_changes(self, prev: str, curr: str) -> tuple[int, int]:
        """Conta linhas adicionadas e removidas via difflib (M3: diff preciso)."""
        import difflib

        prev_lines = prev.strip().splitlines(keepends=True)
        curr_lines = curr.strip().splitlines(keepends=True)

        added = 0
        removed = 0
        for line in difflib.unified_diff(prev_lines, curr_lines, n=0):
            if line.startswith("+++") or line.startswith("---") or line.startswith("@@"):
                continue
            if line.startswith("+"):
                added += 1
            elif line.startswith("-"):
                removed += 1

        return added, removed

    def _estimate_complexity(self, files: dict[str, str]) -> float:
        """
        Estima complexidade ciclomática total.
        Conta: if, else, for, while, switch, case, &&, ||, ternário
        """
        total = 0
        patterns = [
            r"\bif\s*\(", r"\belse\b", r"\bfor\s*\(", r"\bwhile\s*\(",
            r"\bswitch\s*\(", r"\bcase\b", r"&&", r"\|\|", r"\?.*:",
        ]

        for content in files.values():
            for pattern in patterns:
                total += len(re.findall(pattern, content))

        return total

    def _compute_risk_score(self, report: DiffReport) -> float:
        """
        Calcula risk_score (0-100) baseado em múltiplos fatores.
        """
        score = 0.0

        # Churn alto → risco alto
        if report.total_churn > 500:
            score += 25
        elif report.total_churn > 200:
            score += 15
        elif report.total_churn > 50:
            score += 5

        # Arquivos deletados → risco
        score += report.files_deleted * 10

        # Arquivos críticos tocados
        score += len(report.critical_files_touched) * 15

        # Padrões perigosos
        score += len(report.risky_patterns_found) * 8

        # Complexidade alta
        if report.cyclomatic_complexity > 100:
            score += 15
        elif report.cyclomatic_complexity > 50:
            score += 8

        # Bundle cresceu muito
        if report.bundle_size_delta_kb > 50:
            score += 10

        # Muitos arquivos novos de uma vez → risco de inconsistência
        if report.files_added > 5:
            score += 10

        return min(100.0, score)

    def _classify_risk(self, score: float) -> str:
        """Classifica o nível de risco."""
        if score >= 70:
            return "critical"
        elif score >= 40:
            return "high"
        elif score >= 20:
            return "medium"
        return "low"

    def get_current_files(self) -> dict[str, str]:
        """Lê todos os arquivos JS do game/src."""
        game_src = self._game_dir / "src"
        files: dict[str, str] = {}

        if not game_src.exists():
            return files

        for path in game_src.rglob("*.js"):
            relative = str(path.relative_to(self._game_dir))
            try:
                files[relative] = path.read_text(encoding="utf-8")
            except Exception:
                pass

        return files
