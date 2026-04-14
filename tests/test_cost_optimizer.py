"""Unit tests for CostOptimizer (Roadmap v3 Item #11)."""

from __future__ import annotations

import pytest
from backend.llm.cost_optimizer import (
    CostOptimizer,
    CallRecord,
    AgentProviderROI,
    MIN_CALLS_FOR_BONUS,
    MAX_ROUTING_BONUS,
)


# ── Fixtures ──────────────────────────────────────────


@pytest.fixture
def optimizer() -> CostOptimizer:
    return CostOptimizer()


@pytest.fixture
def seeded_optimizer() -> CostOptimizer:
    """Optimizer with enough data to trigger ROI-based routing."""
    opt = CostOptimizer()
    for i in range(10):
        opt.record_call("developer", "sambanova", 0.001, 5.0, 2.0, 1500)
    for i in range(10):
        opt.record_call("developer", "gemini", 0.01, 3.0, 1.5, 1200)
    for i in range(10):
        opt.record_call("tester", "sambanova", 0.001, 2.0, 1.0, 800)
    return opt


# ── CallRecord & AgentProviderROI ─────────────────────


class TestCallRecord:
    def test_fields(self):
        r = CallRecord(
            agent="dev", provider="sam",
            cost_usd=0.01, quality_delta=5.0,
            latency=2.0, tokens=1500,
        )
        assert r.agent == "dev"
        assert r.provider == "sam"
        assert r.cost_usd == 0.01
        assert r.quality_delta == 5.0
        assert r.timestamp > 0

    def test_default_timestamp(self):
        r = CallRecord("a", "b", 0.0, 0.0, 0.0, 0)
        assert r.timestamp > 0


class TestAgentProviderROI:
    def test_empty_roi(self):
        roi = AgentProviderROI()
        assert roi.avg_cost == 0.0
        assert roi.avg_quality == 0.0
        assert roi.avg_latency == 0.0

    def test_computed_roi_with_cost(self):
        roi = AgentProviderROI(
            total_calls=10,
            total_cost_usd=0.01,
            total_quality=50.0,
            total_tokens=15000,
        )
        # ROI = 50.0 / 0.01 = 5000.0
        assert roi.roi == 5000.0

    def test_computed_roi_free_tier(self):
        roi = AgentProviderROI(
            total_calls=10,
            total_cost_usd=0.0,  # free tier
            total_quality=50.0,
            total_tokens=100_000,
        )
        # Token proxy = 100_000 / 100_000 = 1.0
        # ROI = 50.0 / 1.0 = 50.0
        assert roi.roi == 50.0

    def test_avg_properties(self):
        roi = AgentProviderROI(
            total_calls=5,
            total_cost_usd=0.05,
            total_quality=25.0,
            total_latency=10.0,
        )
        assert roi.avg_cost == pytest.approx(0.01)
        assert roi.avg_quality == pytest.approx(5.0)
        assert roi.avg_latency == pytest.approx(2.0)


# ── CostOptimizer Recording ──────────────────────────


class TestRecording:
    def test_record_call_updates_cache(self, optimizer: CostOptimizer):
        optimizer.record_call("dev", "sam", 0.001, 5.0, 2.0, 1500)
        stats = optimizer.get_stats()
        assert stats["total_records"] == 1
        assert stats["total_calls"] == 1

    def test_multiple_records(self, optimizer: CostOptimizer):
        for _ in range(5):
            optimizer.record_call("dev", "sam", 0.001, 5.0, 2.0, 1500)
        stats = optimizer.get_stats()
        assert stats["total_records"] == 5
        assert stats["total_calls"] == 5

    def test_multiple_agents(self, optimizer: CostOptimizer):
        optimizer.record_call("dev", "sam", 0.001, 5.0, 2.0, 1500)
        optimizer.record_call("tester", "gemini", 0.01, 3.0, 1.5, 1200)
        stats = optimizer.get_stats()
        assert stats["unique_agents"] == 2
        assert stats["unique_providers"] == 2
        assert stats["pairs_tracked"] == 2


# ── ROI Queries ───────────────────────────────────────


class TestROIQueries:
    def test_roi_insufficient_data(self, optimizer: CostOptimizer):
        optimizer.record_call("dev", "sam", 0.001, 5.0, 2.0, 1500)
        assert optimizer.get_roi("dev", "sam") == 0.0  # < MIN_CALLS

    def test_roi_sufficient_data(self, seeded_optimizer: CostOptimizer):
        roi = seeded_optimizer.get_roi("developer", "sambanova")
        assert roi > 0

    def test_get_best_provider(self, seeded_optimizer: CostOptimizer):
        best = seeded_optimizer.get_best_provider("developer")
        assert best is not None
        # sambanova: 50.0 quality / 0.01 cost = 5000 ROI
        # gemini: 30.0 quality / 0.10 cost = 300 ROI
        assert best == "sambanova"

    def test_get_best_provider_no_data(self, optimizer: CostOptimizer):
        assert optimizer.get_best_provider("nonexistent") is None


# ── Routing Bonus ─────────────────────────────────────


class TestRoutingBonus:
    def test_bonus_zero_insufficient_data(self, optimizer: CostOptimizer):
        optimizer.record_call("dev", "sam", 0.001, 5.0, 2.0, 1500)
        bonus = optimizer.get_routing_bonus("dev", "sam")
        assert bonus == 0.0

    def test_bonus_best_gets_max(self, seeded_optimizer: CostOptimizer):
        bonus = seeded_optimizer.get_routing_bonus("developer", "sambanova")
        assert bonus == MAX_ROUTING_BONUS

    def test_bonus_worse_gets_less(self, seeded_optimizer: CostOptimizer):
        bonus_best = seeded_optimizer.get_routing_bonus("developer", "sambanova")
        bonus_worse = seeded_optimizer.get_routing_bonus("developer", "gemini")
        assert bonus_worse < bonus_best
        assert bonus_worse > 0.0

    def test_bonus_unknown_pair(self, seeded_optimizer: CostOptimizer):
        bonus = seeded_optimizer.get_routing_bonus("developer", "nonexistent")
        assert bonus == 0.0


# ── Agent Stats ───────────────────────────────────────


class TestAgentStats:
    def test_agent_stats(self, seeded_optimizer: CostOptimizer):
        stats = seeded_optimizer.get_agent_stats("developer")
        assert "sambanova" in stats
        assert "gemini" in stats
        assert stats["sambanova"]["calls"] == 10
        assert stats["gemini"]["calls"] == 10

    def test_agent_stats_empty(self, optimizer: CostOptimizer):
        stats = optimizer.get_agent_stats("nonexistent")
        assert stats == {}


# ── Pruning ───────────────────────────────────────────


class TestPruning:
    def test_prune_keeps_data_consistent(self, optimizer: CostOptimizer):
        # Force pruning by exceeding limit
        for i in range(100):
            optimizer.record_call("dev", "sam", 0.001, 1.0, 1.0, 100)
        optimizer._prune_oldest()
        stats = optimizer.get_stats()
        assert stats["total_records"] == 50  # Half was pruned
        assert stats["total_calls"] == 50


# ── Global Stats ──────────────────────────────────────


class TestGlobalStats:
    def test_stats_structure(self, seeded_optimizer: CostOptimizer):
        stats = seeded_optimizer.get_stats()
        assert "total_records" in stats
        assert "total_calls" in stats
        assert "total_cost_usd" in stats
        assert "unique_agents" in stats
        assert "unique_providers" in stats
        assert "pairs_tracked" in stats

    def test_empty_stats(self, optimizer: CostOptimizer):
        stats = optimizer.get_stats()
        assert stats["total_records"] == 0
        assert stats["total_calls"] == 0
