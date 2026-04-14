"""
Tests for Pipeline — initialization and _fail_iteration behavior.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.orchestrator.pipeline import Pipeline


# ── Initialization ────────────────────────────────

class TestPipelineInit:
    def test_pipeline_creates(self):
        """Pipeline should instantiate without errors."""
        pipeline = Pipeline()
        assert pipeline is not None

    def test_pipeline_has_core_components(self):
        """Pipeline should have all core components after init."""
        pipeline = Pipeline()
        assert hasattr(pipeline, "llm_router")
        assert hasattr(pipeline, "quality_engine")
        assert hasattr(pipeline, "cost_guard")
        assert hasattr(pipeline, "state")
        assert hasattr(pipeline, "database")
        assert hasattr(pipeline, "builder")
        assert hasattr(pipeline, "watchdog")

    def test_pipeline_state_not_running(self):
        """Pipeline should not be running on init."""
        pipeline = Pipeline()
        assert not pipeline.state.is_running

    def test_pipeline_has_novelty_engine(self):
        """Pipeline should have novelty_engine and exploration_controller."""
        pipeline = Pipeline()
        assert hasattr(pipeline, "novelty_engine")
        assert hasattr(pipeline, "exploration_controller")

    def test_pipeline_has_prompt_engine(self):
        """Pipeline should have a prompt_engine."""
        pipeline = Pipeline()
        assert hasattr(pipeline, "prompt_engine")


# ── _fail_iteration ───────────────────────────────

class TestFailIteration:
    @pytest.mark.asyncio
    async def test_fail_iteration_is_async(self):
        """_fail_iteration should be a coroutine (async def)."""
        pipeline = Pipeline()
        assert asyncio.iscoroutinefunction(pipeline._fail_iteration)

    @pytest.mark.asyncio
    async def test_fail_iteration_calls_database(self):
        """_fail_iteration should await database.update_iteration."""
        pipeline = Pipeline()
        pipeline.database.update_iteration = AsyncMock()
        mock_state = MagicMock()
        pipeline.state.fail_iteration = MagicMock()

        await pipeline._fail_iteration(mock_state, 1, "test error")

        pipeline.database.update_iteration.assert_awaited_once_with(
            1, status="failed", error="test error"
        )

    @pytest.mark.asyncio
    async def test_fail_iteration_handles_db_error(self, caplog):
        """_fail_iteration should log error if db update fails, not raise."""
        pipeline = Pipeline()
        pipeline.database.update_iteration = AsyncMock(
            side_effect=RuntimeError("DB down")
        )
        pipeline.state.fail_iteration = MagicMock()
        mock_state = MagicMock()

        # Should NOT raise
        await pipeline._fail_iteration(mock_state, 1, "test error")

    @pytest.mark.asyncio
    async def test_fail_iteration_updates_state(self):
        """_fail_iteration should call state.fail_iteration."""
        pipeline = Pipeline()
        pipeline.database.update_iteration = AsyncMock()
        pipeline.state.fail_iteration = MagicMock()
        mock_state = MagicMock()

        await pipeline._fail_iteration(mock_state, 1, "test error")

        pipeline.state.fail_iteration.assert_called_once_with(
            mock_state, "test error"
        )


# ── Start / Stop ──────────────────────────────────

class TestStartStop:
    @pytest.mark.asyncio
    async def test_stop_when_not_running(self):
        """Stopping a pipeline that isn't running should be safe."""
        pipeline = Pipeline()
        await pipeline.stop()
        assert not pipeline.state.is_running

    @pytest.mark.asyncio
    async def test_pause_when_not_running(self):
        """Pausing a non-running pipeline should be safe."""
        pipeline = Pipeline()
        await pipeline.pause()


# ── Adaptive Retry Strategy ───────────────────────

class TestAdaptiveRetry:
    def test_retry_strategies_importable(self):
        """RETRY_STRATEGIES should be importable from pipeline."""
        from backend.orchestrator.pipeline import RETRY_STRATEGIES
        assert isinstance(RETRY_STRATEGIES, list)
        assert len(RETRY_STRATEGIES) >= 2

    def test_retry_strategies_shape(self):
        """Each strategy should have temperature and model_tier keys."""
        from backend.orchestrator.pipeline import RETRY_STRATEGIES
        for strategy in RETRY_STRATEGIES:
            assert "temperature" in strategy
            assert "model_tier" in strategy
            assert isinstance(strategy["temperature"], float)
            assert strategy["model_tier"] in ("default", "premium")

    def test_retry_strategies_escalation(self):
        """The last strategy should use premium tier for escalation."""
        from backend.orchestrator.pipeline import RETRY_STRATEGIES
        assert RETRY_STRATEGIES[-1]["model_tier"] == "premium"

    def test_pipeline_has_retries_adaptive_metric(self):
        """Pipeline metrics should include retries_adaptive counter."""
        pipeline = Pipeline()
        assert "retries_adaptive" in pipeline._metrics
        assert pipeline._metrics["retries_adaptive"] == 0


# ── Fixer Render Fixes Metric ────────────────────

class TestFixerRenderFixes:
    def test_pipeline_has_render_fixes_metric(self):
        """Pipeline metrics should include fixer_render_fixes counter."""
        pipeline = Pipeline()
        assert "fixer_render_fixes" in pipeline._metrics
        assert pipeline._metrics["fixer_render_fixes"] == 0
