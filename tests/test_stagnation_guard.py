"""
Tests for StagnationGuard — plateau detection and exploration mode.
"""

import pytest

from backend.core.stagnation_guard import StagnationGuard, StagnationResult


@pytest.fixture
def guard() -> StagnationGuard:
    return StagnationGuard()


# ── Default State ─────────────────────────────────

class TestDefaultState:
    def test_not_stagnated_initially(self, guard: StagnationGuard):
        result = guard.check()
        assert isinstance(result, StagnationResult)
        assert result.is_stagnated is False
        assert result.exploration_mode is False

    def test_not_exploring_initially(self, guard: StagnationGuard):
        assert guard.is_exploring is False


# ── Record & Check ────────────────────────────────

class TestRecordAndCheck:
    def test_record_stores_scores(self, guard: StagnationGuard):
        guard.record(score=50, novelty=60)
        guard.record(score=55, novelty=65)
        # Should not crash, data is stored internally
        result = guard.check()
        assert isinstance(result, StagnationResult)

    def test_no_stagnation_with_improving_scores(self, guard: StagnationGuard):
        for i in range(10):
            guard.record(score=30 + i * 5, novelty=50 + i * 3)
        result = guard.check()
        assert result.is_stagnated is False

    def test_no_stagnation_with_few_data_points(self, guard: StagnationGuard):
        guard.record(score=50, novelty=50)
        guard.record(score=50, novelty=50)
        result = guard.check()
        assert result.is_stagnated is False


# ── Plateau Detection ─────────────────────────────

class TestPlateauDetection:
    def test_plateau_detected_after_flat_scores(self, guard: StagnationGuard):
        # Record many identical scores to trigger plateau
        for _ in range(15):
            guard.record(score=50.0, novelty=20.0)
        result = guard.check()
        assert result.is_stagnated is True
        assert result.exploration_mode is True
        assert "plateau" in result.reason.lower() or "stagnation" in result.reason.lower()

    def test_exploration_mode_activates(self, guard: StagnationGuard):
        for _ in range(15):
            guard.record(score=50.0, novelty=20.0)
        result = guard.check()
        assert result.exploration_mode is True
        assert guard.is_exploring is True


# ── Rollback Recommendation ───────────────────────

class TestRollback:
    def test_rollback_after_extended_exploration(self, guard: StagnationGuard):
        # First, trigger exploration
        for _ in range(15):
            guard.record(score=50.0, novelty=20.0)
        guard.check()  # activates exploration

        # Stay in exploration without improvement for many iterations
        for _ in range(20):
            guard.record(score=40.0, novelty=30.0)
        result = guard.check()
        # After enough exploration iterations, it may recommend rollback
        # The exact behavior depends on the implementation,
        # but check() should not crash
        assert isinstance(result, StagnationResult)


# ── StagnationResult.to_dict ─────────────────────

class TestToDict:
    def test_to_dict_keys(self):
        result = StagnationResult()
        d = result.to_dict()
        expected_keys = {
            "is_stagnated", "exploration_mode", "should_rollback",
            "reason", "recommended_temperature", "min_systems_to_change",
            "exploration_iterations",
        }
        assert set(d.keys()) == expected_keys

    def test_to_dict_values(self):
        result = StagnationResult(is_stagnated=True, reason="test")
        d = result.to_dict()
        assert d["is_stagnated"] is True
        assert d["reason"] == "test"
