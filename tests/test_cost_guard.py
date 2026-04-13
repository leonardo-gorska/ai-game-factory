"""
Tests for CostGuard — budget enforcement and tracking.
"""

import pytest

from backend.core.cost_guard import CostGuard, CostBudget, CostEntry


@pytest.fixture
def guard() -> CostGuard:
    return CostGuard(budget=CostBudget(
        max_total_usd=1.00,
        max_per_hour_usd=0.50,
        max_per_iteration_usd=0.10,
    ))


# ── Recording Costs ──────────────────────────────

class TestRecord:
    def test_record_returns_cost_entry(self, guard: CostGuard):
        entry = guard.record("designer", "openai", 1000, 500, iteration=1)
        assert isinstance(entry, CostEntry)
        assert entry.agent == "designer"
        assert entry.provider == "openai"

    def test_record_increments_total(self, guard: CostGuard):
        guard.record("designer", "openai", 1000, 500, iteration=1)
        stats = guard.get_stats()
        assert stats["total_cost_usd"] > 0
        assert stats["total_calls"] == 1

    def test_multiple_records_accumulate(self, guard: CostGuard):
        guard.record("designer", "openai", 1000, 500, iteration=1)
        guard.record("developer", "openai", 2000, 1000, iteration=1)
        stats = guard.get_stats()
        assert stats["total_calls"] == 2
        assert stats["total_tokens"] == 4500  # 1000+500+2000+1000

    def test_by_agent_breakdown(self, guard: CostGuard):
        guard.record("designer", "openai", 1000, 500, iteration=1)
        guard.record("developer", "openai", 1000, 500, iteration=2)
        stats = guard.get_stats()
        assert "designer" in stats["by_agent"]
        assert "developer" in stats["by_agent"]


# ── Budget Checking ──────────────────────────────

class TestBudgetCheck:
    def test_ok_when_under_budget(self, guard: CostGuard):
        guard.record("designer", "openai", 100, 50, iteration=1)
        can_continue, reason = guard.check_budget()
        assert can_continue is True
        assert reason == "ok"

    def test_stops_when_over_total_budget(self):
        guard = CostGuard(budget=CostBudget(max_total_usd=0.001))
        # Record enough to exceed $0.001
        for i in range(10):
            guard.record("designer", "openai", 10000, 5000, iteration=i)
        can_continue, reason = guard.check_budget()
        assert can_continue is False
        assert "exhausted" in reason.lower() or "budget" in reason.lower()


# ── Stats ────────────────────────────────────────

class TestStats:
    def test_stats_structure(self, guard: CostGuard):
        stats = guard.get_stats()
        required = [
            "total_cost_usd", "total_calls", "total_tokens",
            "budget_remaining_usd", "budget_usage_pct",
            "by_agent", "by_provider", "by_iteration",
        ]
        for key in required:
            assert key in stats, f"Missing key: {key}"

    def test_budget_remaining(self, guard: CostGuard):
        stats = guard.get_stats()
        assert stats["budget_remaining_usd"] == pytest.approx(1.00, abs=0.01)

    def test_by_iteration(self, guard: CostGuard):
        guard.record("designer", "openai", 1000, 500, iteration=1)
        guard.record("designer", "openai", 1000, 500, iteration=2)
        stats = guard.get_stats()
        assert len(stats["by_iteration"]) == 2
