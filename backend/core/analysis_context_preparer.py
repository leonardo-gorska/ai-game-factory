"""
Feedback Loop Assíncrono — Analysis Context Preparer

Prepares analysis context (simulation, routing, stale-agent checks)
in parallel with the build step so that analysis agents can start faster.

Roadmap v2 — Item 7.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from backend.orchestrator.pipeline import Pipeline

logger = logging.getLogger(__name__)


@dataclass
class AnalysisContext:
    """Pre-computed context produced in parallel with the build step."""

    # Simulation results (heaviest build-independent work)
    sim_aggregate: Any = None
    sim_metrics: dict[str, Any] = field(default_factory=dict)

    # Pre-computed file diffs for stale-agent detection & routing
    changed_files: dict[str, str] = field(default_factory=dict)

    # Agent Router decision
    routing_decision: Any = None

    # Stale-agent skip decisions
    skip_performance: bool = False
    skip_exploit: bool = False
    skip_economy: bool = False

    # Economy baseline snapshot for trend tracking
    economy_baseline: dict[str, Any] = field(default_factory=dict)

    # Performance thresholds
    performance_thresholds: dict[str, float] = field(default_factory=dict)

    # Timing
    prep_duration_ms: float = 0.0


class AnalysisContextPreparer:
    """Prepares analysis context that doesn't depend on build output.

    This work runs concurrently with ``_build_with_retries`` to reduce
    the total per-iteration latency by ~15-20%.
    """

    def __init__(self, pipeline: Pipeline) -> None:
        self._pipeline = pipeline

    async def prepare(
        self,
        iteration: int,
        gdd_update: dict[str, Any],
        previous_files: dict[str, str],
    ) -> AnalysisContext:
        """Prepare all build-independent analysis context.

        Args:
            iteration: Current pipeline iteration number.
            gdd_update: Latest GDD update from the Designer.
            previous_files: File snapshot from the previous iteration.

        Returns:
            AnalysisContext with pre-computed results.
        """
        t0 = time.perf_counter()
        ctx = AnalysisContext()

        try:
            # ── 1. Simulator (heaviest independent step) ──
            ctx.sim_aggregate, ctx.sim_metrics = self._run_simulation(iteration)

            # ── 2. Compute changed files for stale-agent detection ──
            ctx.changed_files = self._compute_changed_files(previous_files)

            # ── 3. Agent Router decision ──
            ctx.routing_decision = self._pipeline.agent_router.select_agents(
                changed_files=ctx.changed_files,
                gdd_changes=gdd_update,
                iteration=iteration,
            )

            # ── 4. Stale-agent skip decisions ──
            ctx.skip_performance, ctx.skip_exploit, ctx.skip_economy = (
                self._compute_skip_decisions(iteration, ctx.changed_files)
            )

            # ── 5. Economy baseline snapshot ──
            ctx.economy_baseline = dict(self._pipeline._previous_economy_report)

            # ── 6. Performance thresholds ──
            ctx.performance_thresholds = {
                "last_perf_score": self._pipeline._last_perf_score,
            }

        except Exception as exc:
            logger.error(
                "⚠️ Analysis prep failed (continuing with defaults): %s",
                exc, exc_info=True,
            )

        ctx.prep_duration_ms = (time.perf_counter() - t0) * 1000
        logger.info(
            "⚡ Analysis context prepared in %.0fms (iter #%d)",
            ctx.prep_duration_ms, iteration,
        )
        return ctx

    # ── Private helpers ───────────────────────────────

    def _run_simulation(
        self, iteration: int,
    ) -> tuple[Any, dict[str, Any]]:
        """Run the simulator — doesn't need build output."""
        sim_aggregate = self._pipeline.simulator.run_simulation(
            num_runs=50,
            durations_hours=[1.0, 6.0, 24.0, 48.0, 168.0, 720.0],
            seed=iteration,
        )
        sim_metrics = sim_aggregate.to_quality_metrics()
        return sim_aggregate, sim_metrics

    def _compute_changed_files(
        self, previous_files: dict[str, str],
    ) -> dict[str, str]:
        """Diff current files against the previous snapshot."""
        current = self._pipeline.diff_analyzer.get_current_files()
        changed: dict[str, str] = {}
        for fname, content in current.items():
            if previous_files.get(fname) != content:
                changed[fname] = content
        for fname in previous_files:
            if fname not in current:
                changed[fname] = ""
        return changed

    def _compute_skip_decisions(
        self,
        iteration: int,
        changed_files: dict[str, str],
    ) -> tuple[bool, bool, bool]:
        """Pre-compute stale-agent skip flags."""
        from backend.core.stale_agent_skipper import StaleAgentSkipper

        skip_perf = StaleAgentSkipper.should_skip(
            "performance", iteration,
            prev_perf_score=self._pipeline._last_perf_score,
            curr_perf_score=self._pipeline._last_perf_score,  # no new score yet
        )
        skip_exploit = StaleAgentSkipper.should_skip(
            "exploit_detector", iteration, changed_files=changed_files,
        )
        skip_economy = StaleAgentSkipper.should_skip(
            "economy_guardian", iteration, changed_files=changed_files,
        )
        return skip_perf, skip_exploit, skip_economy
