"""
Tests for backend.orchestrator.parallel_scheduler
"""

import asyncio
from unittest.mock import AsyncMock

import pytest

from backend.orchestrator.parallel_scheduler import (
    ParallelScheduler,
    StepNode,
)


# ── StepNode ──────────────────────────────────────────────

class TestStepNode:
    def test_creates_with_defaults(self):
        node = StepNode(name="test")
        assert node.name == "test"
        assert node.dependencies == set()
        assert node.coro_factory is None

    def test_creates_with_dependencies(self):
        node = StepNode(name="build", dependencies={"dev", "design"})
        assert node.dependencies == {"dev", "design"}


# ── Wave Computation ──────────────────────────────────────

class TestComputeWaves:
    def test_empty_scheduler(self):
        scheduler = ParallelScheduler()
        waves = scheduler.compute_waves()
        assert waves == []

    def test_single_step(self):
        scheduler = ParallelScheduler()
        scheduler.add_step("only")
        waves = scheduler.compute_waves()
        assert len(waves) == 1
        assert len(waves[0]) == 1
        assert waves[0][0].name == "only"

    def test_parallel_independent(self):
        """Steps A and B with no deps should be in the same wave."""
        scheduler = ParallelScheduler()
        scheduler.add_step("A")
        scheduler.add_step("B")
        waves = scheduler.compute_waves()
        assert len(waves) == 1
        names = {s.name for s in waves[0]}
        assert names == {"A", "B"}

    def test_linear_chain(self):
        """A → B → C should produce 3 waves."""
        scheduler = ParallelScheduler()
        scheduler.add_step("A")
        scheduler.add_step("B", {"A"})
        scheduler.add_step("C", {"B"})
        waves = scheduler.compute_waves()
        assert len(waves) == 3
        assert waves[0][0].name == "A"
        assert waves[1][0].name == "B"
        assert waves[2][0].name == "C"

    def test_diamond_dag(self):
        """A → B, A → C, B → D, C → D should produce 3 waves."""
        scheduler = ParallelScheduler()
        scheduler.add_step("A")
        scheduler.add_step("B", {"A"})
        scheduler.add_step("C", {"A"})
        scheduler.add_step("D", {"B", "C"})
        waves = scheduler.compute_waves()
        assert len(waves) == 3
        # Wave 0: A
        assert waves[0][0].name == "A"
        # Wave 1: B and C in parallel
        wave1_names = {s.name for s in waves[1]}
        assert wave1_names == {"B", "C"}
        # Wave 2: D
        assert waves[2][0].name == "D"

    def test_cycle_detection(self):
        """A → B → A should raise ValueError."""
        scheduler = ParallelScheduler()
        scheduler.add_step("A", {"B"})
        scheduler.add_step("B", {"A"})
        with pytest.raises(ValueError, match="Cycle"):
            scheduler.compute_waves()

    def test_missing_dependency_raises(self):
        """Reference to unregistered step should raise ValueError."""
        scheduler = ParallelScheduler()
        scheduler.add_step("A", {"nonexistent"})
        with pytest.raises(ValueError, match="unregistered"):
            scheduler.compute_waves()

    def test_complex_dag(self):
        """Test a more complex DAG similar to the real pipeline."""
        scheduler = ParallelScheduler()
        scheduler.add_step("researcher")
        scheduler.add_step("designer", {"researcher"})
        scheduler.add_step("developer", {"designer"})
        scheduler.add_step("build", {"developer"})
        scheduler.add_step("performance", {"build"})
        scheduler.add_step("simulator", {"build"})
        scheduler.add_step("exploit", {"build"})
        scheduler.add_step("quality", {"performance", "simulator", "exploit"})
        scheduler.add_step("critic", {"quality"})

        waves = scheduler.compute_waves()
        # researcher → designer → developer → build → (perf, sim, exploit) → quality → critic
        assert len(waves) == 7

        # Wave 5: performance + simulator + exploit (parallel)
        wave5_names = {s.name for s in waves[4]}
        assert wave5_names == {"performance", "simulator", "exploit"}


# ── Execution ─────────────────────────────────────────────

class TestExecute:
    @pytest.mark.asyncio
    async def test_execute_returns_results(self):
        """Results should be aggregated from all steps."""
        scheduler = ParallelScheduler()

        async def step_a():
            return {"value": "a"}

        async def step_b():
            return {"value": "b"}

        scheduler.add_step("A", coro_factory=step_a)
        scheduler.add_step("B", coro_factory=step_b)

        results = await scheduler.execute()
        assert results["A"] == {"value": "a"}
        assert results["B"] == {"value": "b"}

    @pytest.mark.asyncio
    async def test_execute_respects_order(self):
        """Steps should execute in DAG order."""
        execution_order = []

        async def make_step(name):
            execution_order.append(name)
            return {"done": name}

        scheduler = ParallelScheduler()
        scheduler.add_step("A", coro_factory=lambda: make_step("A"))
        scheduler.add_step("B", {"A"}, coro_factory=lambda: make_step("B"))
        scheduler.add_step("C", {"B"}, coro_factory=lambda: make_step("C"))

        await scheduler.execute()
        assert execution_order == ["A", "B", "C"]

    @pytest.mark.asyncio
    async def test_execute_handles_exceptions(self):
        """Step exceptions should be captured, not crash the scheduler."""
        scheduler = ParallelScheduler()

        async def failing_step():
            raise RuntimeError("boom")

        async def ok_step():
            return {"ok": True}

        scheduler.add_step("fail", coro_factory=failing_step)
        scheduler.add_step("ok", coro_factory=ok_step)

        results = await scheduler.execute()
        assert "_error" in results["fail"]
        assert results["ok"] == {"ok": True}

    @pytest.mark.asyncio
    async def test_execute_empty_scheduler(self):
        """Empty scheduler should return empty dict."""
        scheduler = ParallelScheduler()
        results = await scheduler.execute()
        assert results == {}

    @pytest.mark.asyncio
    async def test_execute_step_without_factory(self):
        """Step without coro_factory should be skipped with empty result."""
        scheduler = ParallelScheduler()
        scheduler.add_step("no_factory")
        results = await scheduler.execute()
        assert results["no_factory"] == {}

    @pytest.mark.asyncio
    async def test_on_wave_start_callback(self):
        """on_wave_start callback should be called for each wave."""
        scheduler = ParallelScheduler()

        async def step_a():
            return {}

        scheduler.add_step("A", coro_factory=step_a)
        scheduler.add_step("B", {"A"}, coro_factory=step_a)

        wave_log = []

        async def on_wave(idx, names):
            wave_log.append((idx, names))

        await scheduler.execute(on_wave_start=on_wave)
        assert len(wave_log) == 2
        assert wave_log[0][0] == 0
        assert wave_log[1][0] == 1


# ── Utilities ─────────────────────────────────────────────

class TestDagInfo:
    def test_dag_info_basic(self):
        scheduler = ParallelScheduler()
        scheduler.add_step("A")
        scheduler.add_step("B", {"A"})
        info = scheduler.get_dag_info()
        assert info["total_steps"] == 2
        assert info["total_waves"] == 2

    def test_dag_info_with_cycle(self):
        scheduler = ParallelScheduler()
        scheduler.add_step("A", {"B"})
        scheduler.add_step("B", {"A"})
        info = scheduler.get_dag_info()
        assert "error" in info


# ── Remove Step ───────────────────────────────────────────

class TestRemoveStep:
    def test_remove_existing(self):
        scheduler = ParallelScheduler()
        scheduler.add_step("A")
        scheduler.add_step("B", {"A"})
        scheduler.remove_step("A")
        assert "A" not in scheduler.step_names
        # B should have its dependency removed too
        waves = scheduler.compute_waves()
        assert len(waves) == 1

    def test_remove_nonexistent(self):
        scheduler = ParallelScheduler()
        scheduler.remove_step("nonexistent")  # should not raise
