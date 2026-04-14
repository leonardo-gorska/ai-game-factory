"""
GORVAX GAME FACTORY — Stagnation Guard
Detects stagnation in the evolutionary pipeline and activates exploration mode.
Monitors a sliding window of scores, novelty, and variance.
"""

from __future__ import annotations

import logging
import statistics
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# ── Configuration ──────────────────────────────────────
WINDOW_SIZE = 10               # Observation window
PLATEAU_THRESHOLD = 1.0        # Minimum improvement (%) — relaxed from 2.0
PLATEAU_CONSECUTIVE = 7        # Consecutive iterations — relaxed from 5
NOVELTY_THRESHOLD = 15.0       # Minimum novelty score — relaxed from 20.0
VARIANCE_THRESHOLD = 0.5       # Minimum variance — relaxed from 1.0
EXPLORATION_TIMEOUT = 8        # Iterations in exploration — extended from 5
DEFAULT_TEMPERATURE = 0.7      # Normal temperature
EXPLORATION_TEMPERATURE = 0.95 # Temperature in exploration mode
MIN_SYSTEMS_CHANGE = 2         # Minimum GDD systems to change in exploration


@dataclass
class StagnationResult:
    """Stagnation check result."""
    is_stagnated: bool = False
    exploration_mode: bool = False
    should_rollback: bool = False
    reason: str = ""
    recommended_temperature: float = DEFAULT_TEMPERATURE
    min_systems_to_change: int = 0
    exploration_iterations: int = 0

    def to_dict(self) -> dict:
        return {
            "is_stagnated": self.is_stagnated,
            "exploration_mode": self.exploration_mode,
            "should_rollback": self.should_rollback,
            "reason": self.reason,
            "recommended_temperature": self.recommended_temperature,
            "min_systems_to_change": self.min_systems_to_change,
            "exploration_iterations": self.exploration_iterations,
        }


class StagnationGuard:
    """
    Monitors the pipeline to detect stagnation and activate exploration mode.

    Detects 3 types of stagnation:
    1. Plateau: improvement < 2% for 5 consecutive iterations
    2. Low novelty: diversity < threshold
    3. Score plateau: variance < 1.0

    When stagnated:
    - Activates exploration mode (high temperature, force changes)
    - If exploration fails for 5 iterations → signals rollback

    Usage:
        guard = StagnationGuard()
        guard.record(score=65.0, novelty=45.0)
        result = guard.check()
        if result.exploration_mode:
            # Inject into Designer
    """

    def __init__(self) -> None:
        self._scores: list[float] = []
        self._novelties: list[float] = []
        self._in_exploration: bool = False
        self._exploration_count: int = 0
        self._best_score_before_exploration: float = 0.0
        self._best_score_ever: float = 0.0

    # ── Public API ────────────────────────────────────

    def record(self, score: float, novelty: float = 50.0) -> None:
        """
        Record the results of an iteration.

        Args:
            score: Composite score of the iteration (0-100)
            novelty: Novelty score of the iteration (0-100)
        """
        self._scores.append(score)
        self._novelties.append(novelty)

        if score > self._best_score_ever:
            self._best_score_ever = score

        # Limit history size
        if len(self._scores) > 200:
            self._scores = self._scores[-100:]
            self._novelties = self._novelties[-100:]

    def check(self) -> StagnationResult:
        """
        Check if the pipeline is stagnated.

        Returns:
            StagnationResult with diagnosis and recommendations
        """
        # Insufficient data
        if len(self._scores) < PLATEAU_CONSECUTIVE:
            return StagnationResult()

        # If already in exploration mode, check timeout
        if self._in_exploration:
            return self._check_exploration()

        # Check for stagnation
        reasons: list[str] = []

        if self._detect_plateau():
            reasons.append("plateau")

        if self._detect_low_novelty():
            reasons.append("low_novelty")

        if self._detect_low_variance():
            reasons.append("low_variance")

        if not reasons:
            return StagnationResult()

        # Stagnation detected → activate exploration
        self._in_exploration = True
        self._exploration_count = 0
        self._best_score_before_exploration = max(
            self._scores[-WINDOW_SIZE:]
        )

        reason = f"Stagnation detected: {', '.join(reasons)}"
        logger.warning("🔀 %s — activating exploration mode", reason)

        return StagnationResult(
            is_stagnated=True,
            exploration_mode=True,
            reason=reason,
            recommended_temperature=EXPLORATION_TEMPERATURE,
            min_systems_to_change=MIN_SYSTEMS_CHANGE,
            exploration_iterations=0,
        )

    def reset_exploration(self) -> None:
        """Reset exploration mode (called after improvement or rollback)."""
        self._in_exploration = False
        self._exploration_count = 0
        logger.info("🔄 Exploration mode reset")

    @property
    def is_exploring(self) -> bool:
        """Whether in exploration mode."""
        return self._in_exploration

    @property
    def best_score(self) -> float:
        """Best recorded score."""
        return self._best_score_ever

    def get_stats(self) -> dict:
        """Current guard statistics."""
        window = self._scores[-WINDOW_SIZE:] if self._scores else []
        return {
            "total_recorded": len(self._scores),
            "window_avg": statistics.mean(window) if window else 0,
            "window_variance": (
                statistics.variance(window) if len(window) > 1 else 0
            ),
            "is_exploring": self._in_exploration,
            "exploration_count": self._exploration_count,
            "best_score": self._best_score_ever,
        }

    # ── Detection ──────────────────────────────────────

    def _detect_plateau(self) -> bool:
        """
        Detecta platô: melhoria < 2% nas últimas N iterações consecutivas.
        """
        recent = self._scores[-PLATEAU_CONSECUTIVE:]
        if len(recent) < PLATEAU_CONSECUTIVE:
            return False

        # Calculate improvement between each consecutive pair
        improvements = [
            ((recent[i] - recent[i - 1]) / max(recent[i - 1], 1.0)) * 100
            for i in range(1, len(recent))
        ]

        # All improvements below the threshold
        return all(imp < PLATEAU_THRESHOLD for imp in improvements)

    def _detect_low_novelty(self) -> bool:
        """
        Detecta novelty persistentemente baixa.
        """
        window = self._novelties[-WINDOW_SIZE:]
        if len(window) < PLATEAU_CONSECUTIVE:
            return False

        avg_novelty = statistics.mean(window[-PLATEAU_CONSECUTIVE:])
        return avg_novelty < NOVELTY_THRESHOLD

    def _detect_low_variance(self) -> bool:
        """
        Detecta variância muito baixa nos scores (convergência prematura).
        """
        window = self._scores[-WINDOW_SIZE:]
        if len(window) < 3:
            return False

        return statistics.variance(window) < VARIANCE_THRESHOLD

    # ── Exploration Mode ───────────────────────────────

    def _check_exploration(self) -> StagnationResult:
        """
        Verifica progresso durante modo exploração.
        Se sem melhoria por EXPLORATION_TIMEOUT iterações → rollback.
        """
        self._exploration_count += 1

        # Check if there was improvement during exploration
        if self._scores:
            current_best = max(self._scores[-self._exploration_count:])
            improved = current_best > self._best_score_before_exploration + 2.0

            if improved:
                logger.info(
                    "✅ Exploration successful! Score improved: %.1f → %.1f",
                    self._best_score_before_exploration,
                    current_best,
                )
                self.reset_exploration()
                return StagnationResult(
                    reason="Exploration successful — improvement found",
                )

        # Exploration timeout
        if self._exploration_count >= EXPLORATION_TIMEOUT:
            logger.warning(
                "⏱️ Exploration timeout (%d iterations without improvement) "
                "— signaling rollback",
                EXPLORATION_TIMEOUT,
            )
            self.reset_exploration()
            return StagnationResult(
                is_stagnated=True,
                should_rollback=True,
                reason=(
                    f"Exploration timeout after {EXPLORATION_TIMEOUT} "
                    f"iterations — rollback recommended"
                ),
            )

        # Continue exploring
        return StagnationResult(
            is_stagnated=True,
            exploration_mode=True,
            reason=(
                f"Exploring ({self._exploration_count}/{EXPLORATION_TIMEOUT})"
            ),
            recommended_temperature=EXPLORATION_TEMPERATURE,
            min_systems_to_change=MIN_SYSTEMS_CHANGE,
            exploration_iterations=self._exploration_count,
        )
