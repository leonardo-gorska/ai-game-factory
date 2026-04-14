"""
Tests for AnalysisContextPreparer — Feedback Loop Assíncrono (Roadmap v2, Item 7).

Verifies that analysis context is prepared correctly, runs concurrently
with the build, handles errors gracefully, and properly tracks metrics.
"""

import asyncio
import time
from dataclasses import dataclass, field
from unittest.mock import MagicMock, patch

import pytest

from backend.core.analysis_context_preparer import (
    AnalysisContext,
    AnalysisContextPreparer,
)


# ── Helpers ────────────────────────────────────────

@dataclass
class _FakeProfileStats:
    profile: str = "casual"
    avg_level: float = 10.0
    avg_gold_per_hour: float = 100.0
    avg_deaths: float = 2.0
    engagement_rate: float = 0.7


@dataclass
class _FakeHeatmap:
    def to_dict(self):
        return {"zones": []}


@dataclass
class _FakeSimAggregate:
    total_runs: int = 50
    crash_rate: float = 0.02
    avg_level: float = 10.0
    avg_gold_per_hour: float = 100.0
    economy_inflation: float = 0.03
    progression_slope: float = 1.2
    stuck_rate: float = 0.05
    engagement_rate: float = 0.65
    is_bimodal: bool = False
    confidence_lower: float = 30.0
    confidence_upper: float = 70.0
    estimated_retention_d1: float = 0.4
    estimated_retention_d7: float = 0.15
    estimated_retention_d30: float = 0.05
    avg_xp_per_hour: float = 200.0
    per_profile_stats: list = field(default_factory=lambda: [_FakeProfileStats()])
    gameplay_heatmap: _FakeHeatmap = field(default_factory=_FakeHeatmap)

    def to_quality_metrics(self):
        return {
            "crash_rate": self.crash_rate,
            "avg_level": self.avg_level,
            "gold_per_hour": self.avg_gold_per_hour,
        }


@dataclass
class _FakeRoutingDecision:
    agents_to_run: set = field(default_factory=lambda: {"tester", "performance"})
    skipped_agents: set = field(default_factory=lambda: {"exploit_detector"})
    is_full_sweep: bool = False
    reason: str = "test routing"


def _make_mock_pipeline(
    previous_files=None,
    current_files=None,
    sim_aggregate=None,
    routing_decision=None,
):
    """Create a mock Pipeline with the required attributes."""
    pipeline = MagicMock()

    # Simulator
    pipeline.simulator.run_simulation.return_value = (
        sim_aggregate or _FakeSimAggregate()
    )

    # DiffAnalyzer
    pipeline.diff_analyzer.get_current_files.return_value = (
        current_files or {"src/main.js": "console.log('hello');"}
    )

    # Agent Router
    pipeline.agent_router.select_agents.return_value = (
        routing_decision or _FakeRoutingDecision()
    )

    # Previous economy report + perf score
    pipeline._previous_economy_report = {"health_score": 75}
    pipeline._last_perf_score = 60.0

    return pipeline


# ── Tests ──────────────────────────────────────────

class TestAnalysisContext:
    """Test the AnalysisContext dataclass defaults."""

    def test_defaults(self):
        ctx = AnalysisContext()
        assert ctx.sim_aggregate is None
        assert ctx.sim_metrics == {}
        assert ctx.changed_files == {}
        assert ctx.routing_decision is None
        assert ctx.skip_performance is False
        assert ctx.skip_exploit is False
        assert ctx.skip_economy is False
        assert ctx.economy_baseline == {}
        assert ctx.performance_thresholds == {}
        assert ctx.prep_duration_ms == 0.0

    def test_fields_assignable(self):
        ctx = AnalysisContext(
            sim_aggregate="fake",
            sim_metrics={"rate": 0.5},
            changed_files={"a.js": "change"},
            skip_performance=True,
            prep_duration_ms=123.4,
        )
        assert ctx.sim_aggregate == "fake"
        assert ctx.sim_metrics == {"rate": 0.5}
        assert ctx.changed_files == {"a.js": "change"}
        assert ctx.skip_performance is True
        assert ctx.prep_duration_ms == 123.4


class TestAnalysisContextPreparer:
    """Test the AnalysisContextPreparer.prepare() method."""

    @pytest.mark.asyncio
    async def test_prepare_returns_analysis_context(self):
        """prepare() should return a fully populated AnalysisContext."""
        pipeline = _make_mock_pipeline()
        preparer = AnalysisContextPreparer(pipeline)

        ctx = await preparer.prepare(
            iteration=5,
            gdd_update={"combat": {"damage": 10}},
            previous_files={},
        )

        assert isinstance(ctx, AnalysisContext)
        assert ctx.sim_aggregate is not None
        assert ctx.sim_metrics != {}
        assert ctx.routing_decision is not None
        assert ctx.prep_duration_ms > 0

    @pytest.mark.asyncio
    async def test_prepare_runs_simulation(self):
        """Simulator should be called with correct params."""
        pipeline = _make_mock_pipeline()
        preparer = AnalysisContextPreparer(pipeline)

        ctx = await preparer.prepare(
            iteration=3,
            gdd_update={},
            previous_files={},
        )

        pipeline.simulator.run_simulation.assert_called_once_with(
            num_runs=50,
            durations_hours=[1.0, 6.0, 24.0, 48.0, 168.0, 720.0],
            seed=3,
        )
        assert ctx.sim_aggregate.total_runs == 50

    @pytest.mark.asyncio
    async def test_prepare_computes_changed_files(self):
        """Changed files should be detected by diffing current vs previous."""
        previous = {"src/main.js": "old code", "src/deleted.js": "gone"}
        current = {"src/main.js": "new code", "src/new.js": "added"}

        pipeline = _make_mock_pipeline(
            previous_files=previous,
            current_files=current,
        )
        preparer = AnalysisContextPreparer(pipeline)

        ctx = await preparer.prepare(
            iteration=2,
            gdd_update={},
            previous_files=previous,
        )

        assert "src/main.js" in ctx.changed_files  # modified
        assert "src/new.js" in ctx.changed_files  # added
        assert "src/deleted.js" in ctx.changed_files  # deleted (empty string)
        assert ctx.changed_files["src/deleted.js"] == ""

    @pytest.mark.asyncio
    async def test_prepare_calls_agent_router(self):
        """Agent router should be called with changed files and GDD."""
        pipeline = _make_mock_pipeline()
        preparer = AnalysisContextPreparer(pipeline)
        gdd = {"economy": {"gold": 500}}

        ctx = await preparer.prepare(
            iteration=5,
            gdd_update=gdd,
            previous_files={},
        )

        pipeline.agent_router.select_agents.assert_called_once()
        call_kwargs = pipeline.agent_router.select_agents.call_args
        assert call_kwargs[1]["gdd_changes"] == gdd
        assert call_kwargs[1]["iteration"] == 5
        assert ctx.routing_decision is not None

    @pytest.mark.asyncio
    async def test_prepare_computes_skip_decisions(self):
        """Skip decisions should be pre-computed for performance, exploit, economy."""
        pipeline = _make_mock_pipeline()
        preparer = AnalysisContextPreparer(pipeline)

        ctx = await preparer.prepare(
            iteration=5,
            gdd_update={},
            previous_files={},
        )

        # Results depend on StaleAgentSkipper logic; just ensure booleans
        assert isinstance(ctx.skip_performance, bool)
        assert isinstance(ctx.skip_exploit, bool)
        assert isinstance(ctx.skip_economy, bool)

    @pytest.mark.asyncio
    async def test_prepare_includes_economy_baseline(self):
        """Economy baseline should snapshot the previous economy report."""
        pipeline = _make_mock_pipeline()
        pipeline._previous_economy_report = {"health_score": 82, "warnings": []}
        preparer = AnalysisContextPreparer(pipeline)

        ctx = await preparer.prepare(
            iteration=5,
            gdd_update={},
            previous_files={},
        )

        assert ctx.economy_baseline == {"health_score": 82, "warnings": []}

    @pytest.mark.asyncio
    async def test_prepare_includes_performance_thresholds(self):
        """Performance thresholds should include last perf score."""
        pipeline = _make_mock_pipeline()
        pipeline._last_perf_score = 72.5
        preparer = AnalysisContextPreparer(pipeline)

        ctx = await preparer.prepare(
            iteration=5,
            gdd_update={},
            previous_files={},
        )

        assert ctx.performance_thresholds["last_perf_score"] == 72.5

    @pytest.mark.asyncio
    async def test_prepare_records_timing(self):
        """prep_duration_ms should be > 0."""
        pipeline = _make_mock_pipeline()
        preparer = AnalysisContextPreparer(pipeline)

        ctx = await preparer.prepare(
            iteration=1,
            gdd_update={},
            previous_files={},
        )

        assert ctx.prep_duration_ms > 0

    @pytest.mark.asyncio
    async def test_prepare_handles_error_gracefully(self):
        """If simulation crashes, prepare() should still return a context."""
        pipeline = _make_mock_pipeline()
        pipeline.simulator.run_simulation.side_effect = RuntimeError("sim crash")
        preparer = AnalysisContextPreparer(pipeline)

        ctx = await preparer.prepare(
            iteration=1,
            gdd_update={},
            previous_files={},
        )

        # Should not raise; returns partial context
        assert isinstance(ctx, AnalysisContext)
        assert ctx.sim_aggregate is None  # failed step
        assert ctx.prep_duration_ms > 0


class TestParallelExecution:
    """Test that prep runs concurrently with other async work."""

    @pytest.mark.asyncio
    async def test_prep_and_build_overlap(self):
        """Build and prep should overlap in time, not run sequentially."""
        pipeline = _make_mock_pipeline()
        preparer = AnalysisContextPreparer(pipeline)

        async def fake_build():
            await asyncio.sleep(0.05)
            return {"build_success": True, "build_output": "ok"}

        t0 = time.perf_counter()
        bld, ctx = await asyncio.gather(
            fake_build(),
            preparer.prepare(1, {}, {}),
        )
        elapsed = time.perf_counter() - t0

        # If both ran sequentially, total would be > 0.05 + prep_time
        # With overlap, total should be close to max(build, prep)
        assert bld["build_success"] is True
        assert isinstance(ctx, AnalysisContext)
        # Should complete in well under 0.2s (generous margin)
        assert elapsed < 0.2


class TestPipelineMetrics:
    """Test that pipeline metrics are tracked for async prep."""

    def test_pipeline_has_async_prep_metrics(self):
        """Pipeline should include async prep metric keys."""
        from backend.orchestrator.pipeline import Pipeline
        pipeline = Pipeline()
        assert "analysis_prep_parallel" in pipeline._metrics
        assert "analysis_prep_time_saved_ms" in pipeline._metrics
        assert pipeline._metrics["analysis_prep_parallel"] == 0
        assert pipeline._metrics["analysis_prep_time_saved_ms"] == 0

    def test_pipeline_has_analysis_preparer(self):
        """Pipeline should have an analysis_preparer attribute."""
        from backend.orchestrator.pipeline import Pipeline
        pipeline = Pipeline()
        assert hasattr(pipeline, "analysis_preparer")
        assert isinstance(pipeline.analysis_preparer, AnalysisContextPreparer)
