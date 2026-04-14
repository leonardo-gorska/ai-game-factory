"""
GORVAX GAME FACTORY — Competitive Benchmark (Roadmap v2 Item 10)

Compara métricas do jogo com benchmarks de referência por gênero.
Permite que o Critic diga "engagement está 20% abaixo de RPGs típicos"
em vez de apenas "engagement está baixo".
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ── Genre Reference Benchmarks ─────────────────────────────
# Cada gênero tem targets baseados em jogos bem-sucedidos do gênero.
# Métricas: session_length_avg (min), engagement_rate (0-1),
#   crash_rate_max (0-1), retention_d1 (0-1), retention_d7 (0-1),
#   economy_inflation_max (0-1).

GENRE_BENCHMARKS: dict[str, dict[str, float]] = {
    "idle_rpg": {
        "session_length_avg": 12.0,
        "engagement_rate": 0.68,
        "crash_rate_max": 0.02,
        "retention_d1": 0.45,
        "retention_d7": 0.18,
        "economy_inflation_max": 0.03,
    },
    "rpg": {
        "session_length_avg": 15.0,
        "engagement_rate": 0.72,
        "crash_rate_max": 0.02,
        "retention_d1": 0.40,
        "retention_d7": 0.15,
        "economy_inflation_max": 0.05,
    },
    "roguelike": {
        "session_length_avg": 20.0,
        "engagement_rate": 0.75,
        "crash_rate_max": 0.03,
        "retention_d1": 0.35,
        "retention_d7": 0.12,
        "economy_inflation_max": 0.08,
    },
    "puzzle": {
        "session_length_avg": 8.0,
        "engagement_rate": 0.80,
        "crash_rate_max": 0.01,
        "retention_d1": 0.50,
        "retention_d7": 0.22,
        "economy_inflation_max": 0.02,
    },
    "platformer": {
        "session_length_avg": 10.0,
        "engagement_rate": 0.70,
        "crash_rate_max": 0.02,
        "retention_d1": 0.38,
        "retention_d7": 0.14,
        "economy_inflation_max": 0.04,
    },
    "action": {
        "session_length_avg": 12.0,
        "engagement_rate": 0.74,
        "crash_rate_max": 0.03,
        "retention_d1": 0.36,
        "retention_d7": 0.13,
        "economy_inflation_max": 0.06,
    },
    "tower_defense": {
        "session_length_avg": 10.0,
        "engagement_rate": 0.72,
        "crash_rate_max": 0.02,
        "retention_d1": 0.42,
        "retention_d7": 0.17,
        "economy_inflation_max": 0.04,
    },
    "racing": {
        "session_length_avg": 8.0,
        "engagement_rate": 0.65,
        "crash_rate_max": 0.03,
        "retention_d1": 0.32,
        "retention_d7": 0.10,
        "economy_inflation_max": 0.05,
    },
    "survival": {
        "session_length_avg": 18.0,
        "engagement_rate": 0.70,
        "crash_rate_max": 0.04,
        "retention_d1": 0.38,
        "retention_d7": 0.14,
        "economy_inflation_max": 0.06,
    },
    "strategy": {
        "session_length_avg": 15.0,
        "engagement_rate": 0.68,
        "crash_rate_max": 0.02,
        "retention_d1": 0.40,
        "retention_d7": 0.16,
        "economy_inflation_max": 0.04,
    },
    "simulation": {
        "session_length_avg": 14.0,
        "engagement_rate": 0.66,
        "crash_rate_max": 0.02,
        "retention_d1": 0.42,
        "retention_d7": 0.18,
        "economy_inflation_max": 0.03,
    },
}


@dataclass
class MetricGap:
    """Gap between actual and target for a single metric."""
    metric: str
    actual: float
    target: float
    gap_pct: float       # Positive = above target, negative = below
    is_inverted: bool    # True for metrics like crash_rate where lower is better

    @property
    def is_good(self) -> bool:
        """Whether the actual value meets/exceeds the target."""
        if self.is_inverted:
            return self.actual <= self.target
        return self.actual >= self.target


@dataclass
class BenchmarkReport:
    """Result of comparing game metrics against genre benchmarks."""
    genre: str
    gaps: dict[str, MetricGap] = field(default_factory=dict)
    above_average: list[str] = field(default_factory=list)
    below_average: list[str] = field(default_factory=list)

    @property
    def summary(self) -> str:
        """Generate a human-readable summary of the benchmark comparison."""
        if not self.gaps:
            return f"No benchmark data available for genre '{self.genre}'."

        parts: list[str] = [f"Benchmark vs {self.genre} reference:"]
        if self.above_average:
            parts.append(f"  ✅ Above average: {', '.join(self.above_average)}")
        if self.below_average:
            items = []
            for metric_name in self.below_average:
                gap = self.gaps[metric_name]
                items.append(f"{metric_name} ({gap.gap_pct:+.0f}%)")
            parts.append(f"  ⚠️ Below average: {', '.join(items)}")
        if not self.above_average and not self.below_average:
            parts.append("  All metrics at target level.")
        return "\n".join(parts)

    def to_dict(self) -> dict[str, Any]:
        """Serialize for pipeline events and Critic input."""
        return {
            "genre": self.genre,
            "gaps": {
                k: {
                    "metric": v.metric,
                    "actual": round(v.actual, 4),
                    "target": round(v.target, 4),
                    "gap_pct": round(v.gap_pct, 1),
                    "is_good": v.is_good,
                }
                for k, v in self.gaps.items()
            },
            "above_average": self.above_average,
            "below_average": self.below_average,
            "summary": self.summary,
        }


# Metrics where LOWER is BETTER (inverted)
_INVERTED_METRICS = {"crash_rate_max", "economy_inflation_max"}


class BenchmarkComparator:
    """Compares game quality metrics against genre-specific benchmarks."""

    def compare(
        self,
        metrics: dict[str, float],
        genre: str,
    ) -> BenchmarkReport:
        """
        Compare actual metrics with genre reference.

        Args:
            metrics: Dict with keys matching GENRE_BENCHMARKS keys.
                     e.g. {"session_length_avg": 10.5, "engagement_rate": 0.65, ...}
            genre: Game genre key (e.g. "rpg", "idle_rpg", "puzzle").

        Returns:
            BenchmarkReport with per-metric gaps and summary.
        """
        ref = GENRE_BENCHMARKS.get(genre)
        if ref is None:
            logger.warning(
                "No benchmark data for genre '%s'. Known: %s",
                genre, list(GENRE_BENCHMARKS.keys()),
            )
            return BenchmarkReport(genre=genre)

        gaps: dict[str, MetricGap] = {}
        above: list[str] = []
        below: list[str] = []

        for key, target in ref.items():
            actual = metrics.get(key)
            if actual is None:
                continue

            is_inverted = key in _INVERTED_METRICS

            # Calculate gap percentage relative to target
            if target != 0:
                if is_inverted:
                    # For inverted metrics: negative gap = bad (actual > target)
                    gap_pct = (target - actual) / target * 100
                else:
                    gap_pct = (actual - target) / target * 100
            else:
                gap_pct = 0.0

            gap = MetricGap(
                metric=key,
                actual=actual,
                target=target,
                gap_pct=gap_pct,
                is_inverted=is_inverted,
            )
            gaps[key] = gap

            if gap.is_good:
                above.append(key)
            else:
                below.append(key)

        report = BenchmarkReport(
            genre=genre,
            gaps=gaps,
            above_average=sorted(above),
            below_average=sorted(below),
        )

        logger.info(
            "📊 Benchmark [%s]: %d above, %d below average",
            genre, len(above), len(below),
        )

        return report
