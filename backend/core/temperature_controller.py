"""
GORVAX GAME FACTORY — Dynamic Agent Temperature Controller

Adjusts LLM temperature per agent based on quality trends:
- Quality rising  → decrease temperature (converge)
- Plateau         → increase temperature (explore)
- Quality falling → restore conservative (stabilize)

Each agent maintains an independent quality history curve.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# ── Thresholds ─────────────────────────────────────────

# Minimum iterations before any adjustment kicks in
MIN_HISTORY = 3

# Window size for trend detection
DEFAULT_WINDOW = 5

# Trend thresholds (relative to the score range 0-100)
RISING_THRESHOLD = 2.0      # avg improvement > +2 per iteration → converging
PLATEAU_THRESHOLD = 2.0     # abs(change) < 2 over full window → plateau
FALLING_THRESHOLD = -5.0    # avg decline < -5 per iteration → falling

# Temperature adjustments
CONVERGE_DELTA = -0.15      # Reduce when rising
EXPLORE_DELTA = 0.20        # Increase when plateau
STABILIZE_DELTA = -0.10     # Slightly reduce when falling

# Absolute bounds
TEMP_MIN = 0.3
TEMP_MAX = 1.0


@dataclass
class TemperatureRecommendation:
    """Result of a temperature query."""
    agent: str
    recommended: float
    default: float
    trend: str          # "rising", "plateau", "falling", "insufficient_data"
    adjustment: float   # delta applied

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent": self.agent,
            "recommended": round(self.recommended, 3),
            "default": self.default,
            "trend": self.trend,
            "adjustment": round(self.adjustment, 3),
        }


class TemperatureController:
    """
    Dynamically adjusts LLM temperature per agent based on quality trends.

    Usage::

        ctrl = TemperatureController()
        ctrl.record("designer", iteration=1, quality_score=45.0)
        ctrl.record("designer", iteration=2, quality_score=50.0)
        ctrl.record("designer", iteration=3, quality_score=56.0)

        rec = ctrl.get_recommendation("designer", default=0.7)
        # rec.recommended ≈ 0.55 (converging — quality rising)
    """

    def __init__(self, window: int = DEFAULT_WINDOW) -> None:
        self._window = max(MIN_HISTORY, window)
        self._agent_history: dict[str, list[float]] = defaultdict(list)
        self._total_adjustments = 0

    # ── Recording ──────────────────────────────────────

    def record(self, agent: str, iteration: int, quality_score: float) -> None:
        """
        Record the quality score produced after an agent's contribution.

        Args:
            agent: Agent name (designer, developer, etc.)
            iteration: Current pipeline iteration number
            quality_score: Composite quality score (0-100)
        """
        self._agent_history[agent].append(quality_score)

        # Keep only the last N*2 entries to avoid unbounded growth
        max_keep = self._window * 2
        if len(self._agent_history[agent]) > max_keep:
            self._agent_history[agent] = self._agent_history[agent][-max_keep:]

    # ── Recommendation ─────────────────────────────────

    def get_recommendation(
        self,
        agent: str,
        default: float = 0.7,
    ) -> TemperatureRecommendation:
        """
        Get the recommended temperature for an agent.

        Args:
            agent: Agent name
            default: Default temperature if no adjustment needed

        Returns:
            TemperatureRecommendation with trend analysis and adjusted temp
        """
        history = self._agent_history.get(agent, [])

        if len(history) < MIN_HISTORY:
            return TemperatureRecommendation(
                agent=agent,
                recommended=default,
                default=default,
                trend="insufficient_data",
                adjustment=0.0,
            )

        # Use the last `window` entries
        window = history[-self._window:]
        trend, adjustment = self._analyze_trend(window)

        recommended = default + adjustment
        recommended = max(TEMP_MIN, min(TEMP_MAX, recommended))

        if adjustment != 0.0:
            self._total_adjustments += 1
            logger.debug(
                "🌡️ Temperature adjustment: %s → %.2f (trend=%s, delta=%+.2f)",
                agent, recommended, trend, adjustment,
            )

        return TemperatureRecommendation(
            agent=agent,
            recommended=recommended,
            default=default,
            trend=trend,
            adjustment=adjustment,
        )

    def get_temperature(self, agent: str, default: float = 0.7) -> float:
        """Convenience: return just the recommended temperature float."""
        return self.get_recommendation(agent, default).recommended

    # ── Trend Analysis ─────────────────────────────────

    def _analyze_trend(self, window: list[float]) -> tuple[str, float]:
        """
        Analyze quality trend over a window of scores.

        Returns:
            (trend_name, temperature_adjustment)
        """
        if len(window) < MIN_HISTORY:
            return "insufficient_data", 0.0

        # Calculate per-iteration average change
        changes = [window[i] - window[i - 1] for i in range(1, len(window))]
        avg_change = sum(changes) / len(changes)

        # Total change over the window
        total_change = window[-1] - window[0]

        # Variance of scores (for plateau detection)
        mean = sum(window) / len(window)
        variance = sum((x - mean) ** 2 for x in window) / len(window)

        # ── Decision logic ──

        # Rising: consistent improvement
        if avg_change >= RISING_THRESHOLD:
            return "rising", CONVERGE_DELTA

        # Falling: consistent decline
        if avg_change <= FALLING_THRESHOLD:
            return "falling", STABILIZE_DELTA

        # Plateau: low variance AND small total change over full window
        if (
            len(window) >= self._window
            and abs(total_change) < PLATEAU_THRESHOLD * len(window)
            and variance < (PLATEAU_THRESHOLD * 2) ** 2
        ):
            return "plateau", EXPLORE_DELTA

        # No clear trend
        return "stable", 0.0

    # ── Stats ──────────────────────────────────────────

    def get_stats(self) -> dict[str, Any]:
        """Return current controller statistics."""
        agent_info: dict[str, dict[str, Any]] = {}

        for agent, history in self._agent_history.items():
            rec = self.get_recommendation(agent)
            agent_info[agent] = {
                "history_length": len(history),
                "trend": rec.trend,
                "current_temperature": rec.recommended,
                "last_scores": history[-5:] if history else [],
            }

        return {
            "agents": agent_info,
            "total_adjustments": self._total_adjustments,
            "window_size": self._window,
        }

    def reset(self, agent: str | None = None) -> None:
        """Reset history for a specific agent or all agents."""
        if agent:
            self._agent_history.pop(agent, None)
        else:
            self._agent_history.clear()
            self._total_adjustments = 0
