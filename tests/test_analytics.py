"""
Tests for backend.api.analytics — Real-Time Dashboard Analytics (Roadmap v3 Item #16)
"""

import pytest
from unittest.mock import MagicMock
from dataclasses import dataclass, field
from typing import Any

from backend.api.analytics import PipelineAnalytics


# ─── Mock Helpers ─────────────────────────────────────

@dataclass
class MockSnapshot:
    iteration: int = 1
    quality_score: float = 50.0
    cost_usd: float = 0.01
    build_success: bool = True
    exploration_mode: bool = False
    tags: list = field(default_factory=list)
    extra: dict = field(default_factory=dict)


def _mock_tracker(snapshots: list[MockSnapshot] | None = None):
    tracker = MagicMock()
    snaps = snapshots or []
    tracker._experiments = {s.iteration: s for s in snaps}
    scores = [s.quality_score for s in snaps]
    costs = [s.cost_usd for s in snaps]
    tracker.get_stats.return_value = {
        "total_experiments": len(snaps),
        "score_avg": sum(scores) / max(len(scores), 1) if scores else 0,
        "total_cost_usd": sum(costs),
        "avg_cost_per_iter": sum(costs) / max(len(costs), 1) if costs else 0,
    }
    return tracker


@dataclass
class MockCostEntry:
    agent: str = "designer"
    provider: str = "gemini"
    estimated_cost_usd: float = 0.001


def _mock_cost_guard(entries=None, by_agent=None, total_cost=0.01):
    cg = MagicMock()
    cg._entries = entries or []
    cg.get_stats.return_value = {
        "total_cost_usd": total_cost,
        "total_calls": len(entries) if entries else 0,
        "by_agent": by_agent or {},
    }
    return cg


def _mock_quality_engine(history=None):
    qe = MagicMock()
    qe.get_history.return_value = history or []
    return qe


# ─── Agent Latency ────────────────────────────────────

class TestAgentLatency:
    def test_empty_tracker(self):
        tracker = _mock_tracker([])
        result = PipelineAnalytics.get_agent_latency_breakdown(tracker)
        assert result == {}

    def test_with_latencies(self):
        snaps = [
            MockSnapshot(iteration=1, extra={"agent_latencies": {"designer": 2.5, "developer": 1.0}}),
            MockSnapshot(iteration=2, extra={"agent_latencies": {"designer": 3.0, "developer": 1.5}}),
            MockSnapshot(iteration=3, extra={"agent_latencies": {"designer": 2.0, "developer": 2.0}}),
        ]
        result = PipelineAnalytics.get_agent_latency_breakdown(_mock_tracker(snaps))
        assert "designer" in result
        assert "developer" in result
        assert result["designer"]["count"] == 3
        assert result["developer"]["mean"] == round((1.0 + 1.5 + 2.0) / 3, 3)

    def test_single_entry(self):
        snaps = [MockSnapshot(iteration=1, extra={"agent_latencies": {"tester": 5.0}})]
        result = PipelineAnalytics.get_agent_latency_breakdown(_mock_tracker(snaps))
        assert result["tester"]["p50"] == 5.0
        assert result["tester"]["p95"] == 5.0


# ─── Agent Cost Breakdown ────────────────────────────

class TestAgentCostBreakdown:
    def test_empty(self):
        cg = _mock_cost_guard()
        result = PipelineAnalytics.get_agent_cost_breakdown(cg)
        assert result == {}

    def test_with_agents(self):
        entries = [
            MockCostEntry(agent="designer"),
            MockCostEntry(agent="designer"),
            MockCostEntry(agent="developer"),
        ]
        cg = _mock_cost_guard(
            entries=entries,
            by_agent={"designer": 0.004, "developer": 0.002},
            total_cost=0.006,
        )
        result = PipelineAnalytics.get_agent_cost_breakdown(cg)
        assert "designer" in result
        assert result["designer"]["calls"] == 2
        assert result["developer"]["calls"] == 1
        assert result["designer"]["pct_of_total"] > 0


# ─── Quality Projection ──────────────────────────────

class TestQualityProjection:
    def test_insufficient_data(self):
        qe = _mock_quality_engine([{"composite": 50}])
        result = PipelineAnalytics.get_quality_projection(qe)
        assert result["confidence"] == "insufficient_data"
        assert result["projected_scores"] == []

    def test_linear_upward(self):
        history = [{"composite": 40 + i * 5} for i in range(10)]
        qe = _mock_quality_engine(history)
        result = PipelineAnalytics.get_quality_projection(qe, window=10, horizon=3)
        assert result["slope"] > 0
        assert len(result["projected_scores"]) == 3
        assert result["projected_scores"][0] > history[-1]["composite"]

    def test_flat_scores(self):
        history = [{"composite": 60} for _ in range(5)]
        qe = _mock_quality_engine(history)
        result = PipelineAnalytics.get_quality_projection(qe, window=5, horizon=3)
        assert result["slope"] == 0.0
        # Projected scores should all be ~60
        for score in result["projected_scores"]:
            assert abs(score - 60.0) < 0.1

    def test_clamped_to_100(self):
        history = [{"composite": 90 + i * 5} for i in range(5)]
        qe = _mock_quality_engine(history)
        result = PipelineAnalytics.get_quality_projection(qe, horizon=10)
        for score in result["projected_scores"]:
            assert 0 <= score <= 100


# ─── Efficiency Metrics ──────────────────────────────

class TestEfficiencyMetrics:
    def test_basic(self):
        snaps = [
            MockSnapshot(iteration=1, quality_score=60, cost_usd=0.01, build_success=True),
            MockSnapshot(iteration=2, quality_score=70, cost_usd=0.02, build_success=True),
            MockSnapshot(iteration=3, quality_score=50, cost_usd=0.01, build_success=False),
        ]
        tracker = _mock_tracker(snaps)
        cg = _mock_cost_guard(total_cost=0.04)
        result = PipelineAnalytics.get_efficiency_metrics(tracker, cg)
        assert result["total_iterations"] == 3
        assert result["build_success_rate"] == pytest.approx(66.7, abs=0.1)
        assert result["best_score"] == 70.0

    def test_empty(self):
        tracker = _mock_tracker([])
        cg = _mock_cost_guard(total_cost=0.001)
        result = PipelineAnalytics.get_efficiency_metrics(tracker, cg)
        assert result["total_iterations"] >= 1


# ─── Full Analytics ──────────────────────────────────

class TestFullAnalytics:
    def test_all_keys_present(self):
        pipeline = MagicMock()
        pipeline.experiment_tracker = _mock_tracker([])
        pipeline.cost_guard = _mock_cost_guard()
        pipeline.quality_engine = _mock_quality_engine()
        pipeline._last_goals = {}
        pipeline._metrics = {}

        result = PipelineAnalytics.get_full_analytics(pipeline)
        assert "agent_latency" in result
        assert "agent_cost_breakdown" in result
        assert "quality_projection" in result
        assert "efficiency" in result
        assert "goals" in result

    def test_with_goals(self):
        pipeline = MagicMock()
        pipeline.experiment_tracker = _mock_tracker([])
        pipeline.cost_guard = _mock_cost_guard()
        pipeline.quality_engine = _mock_quality_engine()
        pipeline._last_goals = {
            "goals": [{"id": "g1", "area": "stability"}],
            "focus_summary": "Fix bugs",
        }
        pipeline._metrics = {"goal_sets_generated": 3, "goal_sets_reused": 7}

        result = PipelineAnalytics.get_full_analytics(pipeline)
        assert result["goals"]["focus_summary"] == "Fix bugs"
        assert result["goals"]["goals_generated"] == 3

    def test_resilient_to_errors(self):
        pipeline = MagicMock()
        pipeline.experiment_tracker = None  # Will cause attribute errors
        pipeline.cost_guard = None
        pipeline.quality_engine = None
        pipeline._last_goals = {}
        pipeline._metrics = {}

        result = PipelineAnalytics.get_full_analytics(pipeline)
        # Should not raise, returns empty dicts for failed sections
        assert isinstance(result, dict)
