"""
GORVAX GAME FACTORY — Pipeline Analytics (Roadmap v3 Item #16)
Real-Time Dashboard Analytics: aggregation helpers that combine
experiment tracker, cost guard, and quality engine data into
rich analytics payloads for the dashboard.
"""

from __future__ import annotations

import logging
import math
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from backend.core.experiment_tracker import ExperimentTracker
    from backend.core.cost_guard import CostGuard
    from backend.core.quality_engine import QualityEngine

logger = logging.getLogger(__name__)


class PipelineAnalytics:
    """Aggregates cross-system metrics for the real-time dashboard."""

    # ── Agent Latency ─────────────────────────────────

    @staticmethod
    def get_agent_latency_breakdown(
        tracker: ExperimentTracker,
    ) -> dict[str, Any]:
        """Compute latency stats per agent from experiment extra data.

        Expects each experiment's ``extra`` dict to contain an
        ``agent_latencies`` sub-dict mapping agent names to duration
        in seconds.  Returns mean, p50, and p95 per agent.
        """
        raw: dict[str, list[float]] = {}
        for snap in tracker._experiments.values():
            latencies = snap.extra.get("agent_latencies", {})
            for agent, dur in latencies.items():
                raw.setdefault(agent, []).append(float(dur))

        result: dict[str, Any] = {}
        for agent, durations in raw.items():
            durations.sort()
            n = len(durations)
            result[agent] = {
                "mean": round(sum(durations) / n, 3),
                "p50": round(durations[n // 2], 3),
                "p95": round(durations[int(n * 0.95)], 3) if n >= 2 else round(durations[-1], 3),
                "count": n,
            }
        return result

    # ── Agent Cost ────────────────────────────────────

    @staticmethod
    def get_agent_cost_breakdown(
        cost_guard: CostGuard,
    ) -> dict[str, Any]:
        """Per-agent cost breakdown from the cost guard.

        Returns total cost, call count, and avg cost per call for
        each agent.
        """
        stats = cost_guard.get_stats()
        by_agent: dict[str, float] = stats.get("by_agent", {})
        total_calls = max(stats.get("total_calls", 1), 1)

        # Count calls per agent from entries
        agent_calls: dict[str, int] = {}
        for entry in cost_guard._entries:
            agent_calls[entry.agent] = agent_calls.get(entry.agent, 0) + 1

        result: dict[str, Any] = {}
        for agent, cost in by_agent.items():
            calls = agent_calls.get(agent, 1)
            result[agent] = {
                "total_cost_usd": round(cost, 6),
                "calls": calls,
                "avg_cost_per_call": round(cost / max(calls, 1), 6),
                "pct_of_total": round(cost / max(stats.get("total_cost_usd", 0.001), 0.0001) * 100, 1),
            }
        return result

    # ── Quality Projection ────────────────────────────

    @staticmethod
    def get_quality_projection(
        quality_engine: QualityEngine,
        window: int = 10,
        horizon: int = 5,
    ) -> dict[str, Any]:
        """Linear regression projection of quality score.

        Uses the last ``window`` scores to extrapolate the next
        ``horizon`` iterations.  Returns slope, projected scores,
        and confidence.
        """
        history = quality_engine.get_history()
        if len(history) < 2:
            return {
                "slope": 0.0,
                "projected_scores": [],
                "confidence": "insufficient_data",
                "data_points": len(history),
            }

        # Take last `window` scores
        recent = history[-window:]
        scores = [h.get("composite", 0) for h in recent]
        n = len(scores)

        # Linear regression: y = mx + b
        x_mean = (n - 1) / 2.0
        y_mean = sum(scores) / n
        numerator = sum((i - x_mean) * (s - y_mean) for i, s in enumerate(scores))
        denominator = sum((i - x_mean) ** 2 for i in range(n))

        if denominator == 0:
            slope = 0.0
        else:
            slope = numerator / denominator

        intercept = y_mean - slope * x_mean

        # Project next `horizon` points
        projected = []
        for j in range(1, horizon + 1):
            x = n - 1 + j
            proj = slope * x + intercept
            projected.append(round(max(0, min(100, proj)), 1))

        # Confidence based on R² and data points
        ss_res = sum((s - (slope * i + intercept)) ** 2 for i, s in enumerate(scores))
        ss_tot = sum((s - y_mean) ** 2 for s in scores)
        r_squared = 1 - (ss_res / max(ss_tot, 0.001))

        if n >= 8 and r_squared > 0.7:
            confidence = "high"
        elif n >= 4 and r_squared > 0.4:
            confidence = "moderate"
        else:
            confidence = "low"

        return {
            "slope": round(slope, 3),
            "projected_scores": projected,
            "r_squared": round(r_squared, 3),
            "confidence": confidence,
            "data_points": n,
            "last_score": scores[-1] if scores else 0,
        }

    # ── Efficiency Metrics ────────────────────────────

    @staticmethod
    def get_efficiency_metrics(
        tracker: ExperimentTracker,
        cost_guard: CostGuard,
    ) -> dict[str, Any]:
        """Compute efficiency KPIs: quality-per-dollar, quality-per-iter, build rate."""
        stats = tracker.get_stats()
        cost_stats = cost_guard.get_stats()

        total_exps = max(stats.get("total_experiments", 1), 1)
        total_cost = max(cost_stats.get("total_cost_usd", 0.001), 0.0001)
        avg_score = stats.get("score_avg", 0)

        # Build success rate
        experiments = list(tracker._experiments.values())
        builds = [e for e in experiments if e.build_success]
        build_rate = len(builds) / max(len(experiments), 1) * 100

        # Best score achieved
        scores = [e.quality_score for e in experiments] if experiments else [0]

        return {
            "quality_per_dollar": round(avg_score / total_cost, 2),
            "quality_per_iteration": round(avg_score, 1),
            "build_success_rate": round(build_rate, 1),
            "total_iterations": total_exps,
            "total_cost_usd": round(total_cost, 4),
            "best_score": round(max(scores), 1),
            "worst_score": round(min(scores), 1),
            "avg_cost_per_iteration": round(total_cost / total_exps, 4),
        }

    # ── Full Analytics ────────────────────────────────

    @staticmethod
    def get_full_analytics(pipeline: Any) -> dict[str, Any]:
        """Combine all analytics into a single dashboard payload.

        ``pipeline`` is an instance of ``Pipeline`` (typed as Any
        to avoid circular imports).
        """
        try:
            latency = PipelineAnalytics.get_agent_latency_breakdown(
                pipeline.experiment_tracker
            )
        except Exception:
            latency = {}

        try:
            cost_breakdown = PipelineAnalytics.get_agent_cost_breakdown(
                pipeline.cost_guard
            )
        except Exception:
            cost_breakdown = {}

        try:
            projection = PipelineAnalytics.get_quality_projection(
                pipeline.quality_engine
            )
        except Exception:
            projection = {}

        try:
            efficiency = PipelineAnalytics.get_efficiency_metrics(
                pipeline.experiment_tracker,
                pipeline.cost_guard,
            )
        except Exception:
            efficiency = {}

        # Goal setter stats
        goals_stats: dict[str, Any] = {}
        if hasattr(pipeline, '_last_goals') and pipeline._last_goals:
            goals_stats = {
                "current_goals": pipeline._last_goals.get("goals", []),
                "focus_summary": pipeline._last_goals.get("focus_summary", ""),
                "goals_generated": pipeline._metrics.get("goal_sets_generated", 0),
                "goals_reused": pipeline._metrics.get("goal_sets_reused", 0),
            }

        return {
            "agent_latency": latency,
            "agent_cost_breakdown": cost_breakdown,
            "quality_projection": projection,
            "efficiency": efficiency,
            "goals": goals_stats,
        }
