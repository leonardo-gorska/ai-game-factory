"""
GORVAX GAME FACTORY — Game Evaluator
Automated game evaluation through code analysis.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from backend.config import GAME_DIR

logger = logging.getLogger(__name__)

# Patterns for counting JS functions
_RE_FUNCTION = re.compile(r'\bfunction\s+\w+\s*\(')
_RE_ARROW = re.compile(r'(?:const|let|var)\s+\w+\s*=\s*(?:\([^)]*\)|[a-zA-Z_]\w*)\s*=>')
_RE_METHOD = re.compile(r'^\s+\w+\s*\([^)]*\)\s*\{', re.MULTILINE)


class GameEvaluator:
    """
    Evaluates game quality through static code analysis.
    Provides metrics that complement the Tester agent's LLM-based evaluation.
    """

    def __init__(self, game_dir: Path | None = None) -> None:
        self._game_dir = game_dir or GAME_DIR

    def evaluate(self) -> dict[str, Any]:
        """
        Run automated evaluation on the game codebase.
        Returns metrics dictionary.
        """
        game_src = self._game_dir / "src"

        if not game_src.exists():
            return {
                "code_exists": False,
                "total_files": 0,
                "total_lines": 0,
                "score_bonus": 0,
            }

        files = list(game_src.rglob("*.js"))
        total_lines = 0
        total_functions = 0
        total_classes = 0
        has_main = False
        has_scenes = False
        has_systems = False
        issues: list[str] = []

        for f in files:
            try:
                content = f.read_text(encoding="utf-8")
                lines = content.split("\n")
                total_lines += len(lines)

                # Count functions and classes
                for line in lines:
                    stripped = line.strip()
                    if stripped.startswith("class "):
                        total_classes += 1
                total_functions += len(_RE_FUNCTION.findall(content))
                total_functions += len(_RE_ARROW.findall(content))
                total_functions += len(_RE_METHOD.findall(content))

                # Check for key files
                name = f.name.lower()
                if name == "main.js":
                    has_main = True
                if "scene" in name:
                    has_scenes = True
                if "system" in name:
                    has_systems = True

                # Check for common issues
                if "console.error" in content:
                    issues.append(f"{f.name}: Contains console.error calls")
                if "TODO" in content or "FIXME" in content:
                    issues.append(f"{f.name}: Contains TODO/FIXME")

            except Exception as exc:
                issues.append(f"{f.name}: Read error: {exc}")

        # Calculate a bonus score based on code structure
        score_bonus = 0
        if has_main:
            score_bonus += 5
        if has_scenes:
            score_bonus += 5
        if has_systems:
            score_bonus += 5
        if total_classes >= 3:
            score_bonus += 5
        if total_lines >= 100:
            score_bonus += 5

        return {
            "code_exists": True,
            "total_files": len(files),
            "total_lines": total_lines,
            "total_functions": total_functions,
            "total_classes": total_classes,
            "has_main": has_main,
            "has_scenes": has_scenes,
            "has_systems": has_systems,
            "issues": issues,
            "score_bonus": min(score_bonus, 25),
        }
