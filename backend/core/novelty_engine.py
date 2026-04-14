"""
GORVAX GAME FACTORY — Novelty Engine
Measures the distance/novelty of each iteration relative to the history.
Uses Jaccard Distance on GDD features and code fingerprint.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from backend.config import GAME_DIR

logger = logging.getLogger(__name__)


class NoveltyEngine:
    """
    Lightweight novelty engine (no external embeddings).

    Computes novelty as weighted Jaccard distance between:
    - Features extracted from the GDD (60% weight)
    - JS code fingerprint — class names, functions, imports (40% weight)

    Maintains a cumulative "historical centroid" for comparison.

    Usage:
        engine = NoveltyEngine()
        engine.record_iteration(gdd_dict, code_fingerprint_set)
        score = engine.compute_novelty(new_gdd, new_code_fingerprint)
    """

    GDD_WEIGHT = 0.6
    CODE_WEIGHT = 0.4

    # M4: Sliding window size for centroid computation
    CENTROID_WINDOW = 50

    def __init__(self, game_dir: Path | None = None) -> None:
        self._game_dir = game_dir or GAME_DIR
        self._gdd_history: list[set[str]] = []
        self._code_history: list[set[str]] = []
        self._gdd_centroid: set[str] = set()
        self._code_centroid: set[str] = set()

    # ── Public API ────────────────────────────────────

    def record_iteration(
        self,
        gdd: dict[str, Any],
        code_fingerprint: set[str] | None = None,
    ) -> None:
        """
        Record an iteration in the history for future computation.

        Args:
            gdd: GDD dictionary of the iteration
            code_fingerprint: Set of strings for the code fingerprint.
                If None, it will be automatically extracted from the game dir.
        """
        gdd_features = self.extract_gdd_features(gdd)
        self._gdd_history.append(gdd_features)

        if code_fingerprint is None:
            code_fingerprint = self.extract_code_fingerprint()

        self._code_history.append(code_fingerprint)

        # Limit history
        if len(self._gdd_history) > 200:
            self._gdd_history = self._gdd_history[-100:]
            self._code_history = self._code_history[-100:]

        # M4: Rebuild centroid from sliding window instead of union-forever
        window = self._gdd_history[-self.CENTROID_WINDOW:]
        self._gdd_centroid = set().union(*window) if window else set()
        code_window = self._code_history[-self.CENTROID_WINDOW:]
        self._code_centroid = set().union(*code_window) if code_window else set()

    def compute_novelty(
        self,
        gdd: dict[str, Any],
        code_fingerprint: set[str] | None = None,
    ) -> float:
        """
        Compute the novelty score (0-100) of the current iteration
        relative to the historical centroid.

        Args:
            gdd: GDD of the current iteration
            code_fingerprint: Code fingerprint of the current iteration

        Returns:
            Score 0-100 (0 = clone, 100 = completely new)
        """
        if not self._gdd_history:
            return 50.0  # First iteration — neutral

        gdd_features = self.extract_gdd_features(gdd)

        if code_fingerprint is None:
            code_fingerprint = self.extract_code_fingerprint()

        # Jaccard distance against centroid
        gdd_distance = self._jaccard_distance(gdd_features, self._gdd_centroid)
        code_distance = self._jaccard_distance(code_fingerprint, self._code_centroid)

        # Weighted score
        raw_score = (
            self.GDD_WEIGHT * gdd_distance
            + self.CODE_WEIGHT * code_distance
        )

        # Scale to 0-100
        score = raw_score * 100.0

        # Bonus/penalty
        if score < 10:
            logger.warning("⚠️ Novelty very low (%.1f) — possible clone", score)
        elif score > 60:
            logger.info("🌟 Novelty high (%.1f) — good diversity", score)

        return min(100.0, max(0.0, score))

    def get_stats(self) -> dict[str, Any]:
        """Engine statistics."""
        return {
            "iterations_recorded": len(self._gdd_history),
            "gdd_centroid_size": len(self._gdd_centroid),
            "code_centroid_size": len(self._code_centroid),
            "recent_gdd_features": len(self._gdd_history[-1]) if self._gdd_history else 0,
        }

    # ── Feature Extraction ────────────────────────────

    @staticmethod
    def extract_gdd_features(gdd: dict[str, Any]) -> set[str]:
        """
        Extract a set of feature strings from the GDD.
        Recursively navigates the dict looking for feature names.

        Args:
            gdd: GDD dictionary

        Returns:
            Set of strings representing features
        """
        features: set[str] = set()

        def _extract(obj: Any, prefix: str = "") -> None:
            if isinstance(obj, dict):
                for key, value in obj.items():
                    # Register the key as a feature
                    clean_key = key.lower().strip().replace(" ", "_")
                    if prefix:
                        features.add(f"{prefix}.{clean_key}")
                    else:
                        features.add(clean_key)

                    _extract(value, clean_key)

            elif isinstance(obj, list):
                for item in obj:
                    if isinstance(item, str):
                        features.add(item.lower().strip().replace(" ", "_"))
                    elif isinstance(item, dict):
                        _extract(item, prefix)

            elif isinstance(obj, str) and len(obj) > 2:
                # Longer strings that look like feature names
                clean = obj.lower().strip().replace(" ", "_")
                if len(clean) < 50:  # Ignore long texts
                    features.add(clean)

        _extract(gdd)

        return features

    def extract_code_fingerprint(self, game_dir: Path | None = None) -> set[str]:
        """
        Extract code fingerprint from JS code: class names,
        functions, imports, and exports.

        Args:
            game_dir: Game directory (default: self._game_dir)

        Returns:
            Set of strings representing the code structure
        """
        target_dir = game_dir or self._game_dir
        src_dir = target_dir / "src"

        if not src_dir.exists():
            return set()

        fingerprint: set[str] = set()

        # Patterns to extract JS structure
        class_pattern = re.compile(r"class\s+(\w+)")
        func_pattern = re.compile(r"(?:function|const|let|var)\s+(\w+)\s*(?:=\s*(?:\([^)]*\)\s*=>|function)|\()")
        method_pattern = re.compile(r"^\s+(\w+)\s*\([^)]*\)\s*{", re.MULTILINE)
        import_pattern = re.compile(r"import\s+.*?from\s+['\"](.+?)['\"]")
        export_pattern = re.compile(r"export\s+(?:default\s+)?(?:class|function|const)\s+(\w+)")

        try:
            for js_file in src_dir.rglob("*.js"):
                try:
                    content = js_file.read_text(encoding="utf-8")
                    rel_path = js_file.relative_to(src_dir).as_posix()

                    # Filename as feature
                    fingerprint.add(f"file:{rel_path}")

                    # Classes
                    for match in class_pattern.finditer(content):
                        fingerprint.add(f"class:{match.group(1)}")

                    # Functions
                    for match in func_pattern.finditer(content):
                        fingerprint.add(f"func:{match.group(1)}")

                    # Methods
                    for match in method_pattern.finditer(content):
                        name = match.group(1)
                        if name not in ("if", "for", "while", "switch", "return"):
                            fingerprint.add(f"method:{name}")

                    # Imports
                    for match in import_pattern.finditer(content):
                        fingerprint.add(f"import:{match.group(1)}")

                    # Exports
                    for match in export_pattern.finditer(content):
                        fingerprint.add(f"export:{match.group(1)}")

                except Exception:
                    continue

        except Exception as exc:
            logger.warning("Error extracting code fingerprint: %s", exc)

        return fingerprint

    # ── Helpers ────────────────────────────────────────

    @staticmethod
    def _jaccard_distance(set_a: set[str], set_b: set[str]) -> float:
        """
        Calculate Jaccard Distance between two sets.
        distance = 1 - |A ∩ B| / |A ∪ B|

        Returns:
            0.0 (identical) to 1.0 (completely different)
        """
        if not set_a and not set_b:
            return 0.0

        union = set_a | set_b
        if not union:
            return 0.0

        intersection = set_a & set_b
        return 1.0 - len(intersection) / len(union)
