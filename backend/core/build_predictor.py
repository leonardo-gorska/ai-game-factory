"""
GORVAX GAME FACTORY — Predictive Build Failure

Heuristic-based build risk scoring that predicts whether a build
will fail BEFORE executing it. Uses diff analysis, error pattern
matching, import detection, and history trends.

Advisory only (v1) — warns but does not block builds.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# ── Thresholds ─────────────────────────────────────────

# If failure_probability exceeds this, should_review = True
REVIEW_THRESHOLD = 0.65

# Weight configuration for each heuristic
DEFAULT_WEIGHTS: dict[str, float] = {
    "diff_risk": 0.25,
    "error_pattern": 0.30,
    "import_risk": 0.15,
    "file_count": 0.10,
    "history_trend": 0.20,
}


@dataclass
class BuildPrediction:
    """Result of a build failure prediction."""
    failure_probability: float
    risk_factors: list[str]
    should_review: bool
    confidence: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "failure_probability": round(self.failure_probability, 3),
            "risk_factors": self.risk_factors,
            "should_review": self.should_review,
            "confidence": round(self.confidence, 3),
        }


class BuildPredictor:
    """
    Predicts build failure probability using heuristics (no LLM).

    Heuristics:
    1. Diff risk - proportion of lines changed vs. total
    2. Error pattern match - known error patterns in diffs
    3. Import analysis - new dependencies increase risk
    4. File count - many files changed = more risk
    5. History trend - recent build failure streak

    Usage::

        predictor = BuildPredictor()
        prediction = predictor.predict(
            code_changes="def new_function():\\n    ...",
            error_pattern_db=error_db,
            changed_files_count=5,
            has_new_imports=True,
        )
        if prediction.should_review:
            print(f"⚠️ High failure risk: {prediction.failure_probability:.0%}")

        # After build, calibrate with actual result
        predictor.calibrate(build_succeeded=True)
    """

    def __init__(self, weights: dict[str, float] | None = None) -> None:
        self._weights = weights or DEFAULT_WEIGHTS.copy()
        self._history: list[bool] = []  # True = success, False = failure
        self._prediction_history: list[tuple[float, bool]] = []  # (predicted, actual)
        self._total_predictions = 0
        self._correct_predictions = 0
        self._last_prediction: BuildPrediction | None = None

    # ── Prediction ─────────────────────────────────────

    def predict(
        self,
        code_changes: str = "",
        error_pattern_db: Any = None,
        changed_files_count: int = 0,
        has_new_imports: bool = False,
        total_lines: int = 0,
    ) -> BuildPrediction:
        """
        Predict build failure probability.

        Args:
            code_changes: The diff/code changes to analyze
            error_pattern_db: ErrorPatternDB instance for pattern matching
            changed_files_count: Number of files modified
            has_new_imports: Whether new import statements were added
            total_lines: Total lines in the project (for proportional risk)

        Returns:
            BuildPrediction with failure probability and risk factors
        """
        risk_factors: list[str] = []
        scores: dict[str, float] = {}

        # 1. Diff risk score
        scores["diff_risk"] = self._score_diff_risk(
            code_changes, total_lines, risk_factors,
        )

        # 2. Error pattern match
        scores["error_pattern"] = self._score_error_patterns(
            code_changes, error_pattern_db, risk_factors,
        )

        # 3. Import analysis
        scores["import_risk"] = self._score_import_risk(
            code_changes, has_new_imports, risk_factors,
        )

        # 4. File count risk
        scores["file_count"] = self._score_file_count(
            changed_files_count, risk_factors,
        )

        # 5. History trend
        scores["history_trend"] = self._score_history_trend(risk_factors)

        # Weighted sum
        failure_probability = sum(
            scores.get(k, 0) * self._weights.get(k, 0)
            for k in self._weights
        )
        failure_probability = max(0.0, min(1.0, failure_probability))

        # Confidence based on history size
        confidence = min(1.0, len(self._history) / 10.0) if self._history else 0.3

        should_review = failure_probability >= REVIEW_THRESHOLD

        prediction = BuildPrediction(
            failure_probability=failure_probability,
            risk_factors=risk_factors,
            should_review=should_review,
            confidence=confidence,
        )
        self._last_prediction = prediction
        self._total_predictions += 1

        if should_review:
            logger.warning(
                "⚠️ Build risk: %.0f%% — %s",
                failure_probability * 100,
                ", ".join(risk_factors[:3]),
            )

        return prediction

    # ── Calibration ────────────────────────────────────

    def calibrate(self, build_succeeded: bool) -> None:
        """
        Calibrate the predictor with the actual build result.

        Args:
            build_succeeded: Whether the build actually passed
        """
        self._history.append(build_succeeded)

        # Keep only last 20 results
        if len(self._history) > 20:
            self._history = self._history[-20:]

        if self._last_prediction is not None:
            predicted_fail = self._last_prediction.should_review
            actual_fail = not build_succeeded

            # Track if prediction was correct direction
            if predicted_fail == actual_fail:
                self._correct_predictions += 1

            self._prediction_history.append(
                (self._last_prediction.failure_probability, build_succeeded)
            )
            if len(self._prediction_history) > 50:
                self._prediction_history = self._prediction_history[-50:]

    # ── Individual Heuristics ──────────────────────────

    def _score_diff_risk(
        self,
        code_changes: str,
        total_lines: int,
        risk_factors: list[str],
    ) -> float:
        """Score based on proportion of lines changed."""
        if not code_changes:
            return 0.0

        changed_lines = len(code_changes.splitlines())

        if total_lines > 0:
            ratio = changed_lines / total_lines
        else:
            # No total reference, use absolute thresholds
            ratio = min(1.0, changed_lines / 500)

        if ratio > 0.3:
            risk_factors.append(f"Large diff ({changed_lines} lines, {ratio:.0%} of project)")
            return 1.0
        elif ratio > 0.15:
            risk_factors.append(f"Medium diff ({changed_lines} lines)")
            return 0.6
        elif ratio > 0.05:
            return 0.3
        return 0.1

    def _score_error_patterns(
        self,
        code_changes: str,
        error_pattern_db: Any,
        risk_factors: list[str],
    ) -> float:
        """Score based on known error patterns found in the diff."""
        if not code_changes or error_pattern_db is None:
            return 0.0

        score = 0.0
        try:
            # Check if ErrorPatternDB has a lookup/match method
            if hasattr(error_pattern_db, "lookup"):
                # Extract potential error-prone snippets from the diff
                lines = code_changes.splitlines()
                matches = 0
                for line in lines[:100]:  # Limit to first 100 lines
                    line_stripped = line.strip()
                    if line_stripped and len(line_stripped) > 10:
                        result = error_pattern_db.lookup(line_stripped)
                        if result:
                            matches += 1

                if matches > 5:
                    risk_factors.append(f"Multiple error pattern matches ({matches})")
                    score = 1.0
                elif matches > 2:
                    risk_factors.append(f"Some error pattern matches ({matches})")
                    score = 0.6
                elif matches > 0:
                    score = 0.3

        except Exception as exc:
            logger.debug("Error pattern check failed: %s", exc)

        return score

    def _score_import_risk(
        self,
        code_changes: str,
        has_new_imports: bool,
        risk_factors: list[str],
    ) -> float:
        """Score based on new imports detected."""
        if not has_new_imports and not code_changes:
            return 0.0

        score = 0.0

        if has_new_imports:
            risk_factors.append("New imports detected")
            score = 0.5

        # Also scan diff for import statements
        if code_changes:
            import_lines = [
                line for line in code_changes.splitlines()
                if re.match(r'^\+\s*(import |from \S+ import )', line)
            ]
            if len(import_lines) > 5:
                risk_factors.append(f"Many new imports ({len(import_lines)})")
                score = max(score, 0.8)
            elif len(import_lines) > 2:
                score = max(score, 0.5)

        return score

    def _score_file_count(
        self,
        changed_files_count: int,
        risk_factors: list[str],
    ) -> float:
        """Score based on number of files changed."""
        if changed_files_count > 15:
            risk_factors.append(f"Many files changed ({changed_files_count})")
            return 1.0
        elif changed_files_count > 8:
            risk_factors.append(f"Several files changed ({changed_files_count})")
            return 0.6
        elif changed_files_count > 3:
            return 0.3
        return 0.1

    def _score_history_trend(self, risk_factors: list[str]) -> float:
        """Score based on recent build history."""
        if len(self._history) < 2:
            return 0.3  # neutral when not enough data

        recent = self._history[-5:]
        fail_rate = 1.0 - (sum(1 for x in recent if x) / len(recent))

        if fail_rate >= 0.8:
            risk_factors.append(f"Recent build failure streak ({fail_rate:.0%} failures)")
            return 1.0
        elif fail_rate >= 0.5:
            risk_factors.append(f"Elevated failure rate ({fail_rate:.0%})")
            return 0.7
        elif fail_rate >= 0.3:
            return 0.4
        return 0.1

    # ── Stats ──────────────────────────────────────────

    def get_stats(self) -> dict[str, Any]:
        """Return predictor statistics."""
        accuracy = (
            self._correct_predictions / self._total_predictions
            if self._total_predictions > 0 else 0.0
        )
        return {
            "total_predictions": self._total_predictions,
            "correct_predictions": self._correct_predictions,
            "accuracy": round(accuracy, 3),
            "build_history_length": len(self._history),
            "recent_fail_rate": (
                round(1.0 - sum(1 for x in self._history[-5:] if x) / max(1, len(self._history[-5:])), 3)
                if self._history else 0.0
            ),
        }
