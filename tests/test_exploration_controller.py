"""
Tests for backend.core.exploration_controller — ExplorationController

Covers: decision-making, outcome recording, UCB1 scores, epsilon decay,
forced exploration, initial exploration, stats reporting.
"""

import math

import pytest

from backend.core.exploration_controller import (
    ArmStats,
    ExplorationController,
    ExplorationDecision,
)


# ── ArmStats ────────────────────────────────────────


class TestArmStats:
    def test_avg_reward_zero_pulls(self):
        arm = ArmStats(name="test")
        assert arm.avg_reward == 0.0

    def test_avg_reward_after_pulls(self):
        arm = ArmStats(name="test", pulls=4, total_reward=2.0)
        assert arm.avg_reward == pytest.approx(0.5)


# ── ExplorationDecision ─────────────────────────────


class TestExplorationDecision:
    def test_to_dict_has_required_keys(self):
        d = ExplorationDecision(
            mode="explore",
            temperature=0.7,
            strategy="balanced",
            confidence=0.5,
            reasoning="test",
        )
        result = d.to_dict()
        assert set(result.keys()) == {
            "mode", "temperature", "strategy",
            "confidence", "reasoning", "ucb_scores",
        }


# ── Decide ──────────────────────────────────────────


class TestDecide:
    def test_returns_exploration_decision(self):
        ctrl = ExplorationController(seed=42)
        dec = ctrl.decide()
        assert isinstance(dec, ExplorationDecision)

    def test_initial_exploration_during_warmup(self):
        ctrl = ExplorationController(seed=42)
        dec = ctrl.decide()
        assert dec.mode == "explore"
        assert "Initial exploration" in dec.reasoning

    def test_forced_exploration_when_stagnated(self):
        ctrl = ExplorationController(seed=42)
        dec = ctrl.decide(is_stagnated=True, current_score=20.0)
        assert dec.mode == "explore"
        assert "Stagnation" in dec.reasoning

    def test_strategy_is_valid(self):
        ctrl = ExplorationController(seed=42)
        dec = ctrl.decide()
        assert dec.strategy in ctrl.strategies

    def test_temperature_in_range(self):
        ctrl = ExplorationController(seed=42)
        dec = ctrl.decide()
        assert 0.0 <= dec.temperature <= 1.0

    def test_confidence_in_range(self):
        ctrl = ExplorationController(seed=42)
        dec = ctrl.decide()
        assert 0.0 <= dec.confidence <= 1.0


# ── Record Outcome ──────────────────────────────────


class TestRecordOutcome:
    def test_updates_arm_stats(self):
        ctrl = ExplorationController(seed=42)
        ctrl.record_outcome("balanced", 0.7)
        arm = ctrl.arms["balanced"]
        assert arm.pulls == 1
        assert arm.total_reward == pytest.approx(0.7)
        assert arm.best_reward == pytest.approx(0.7)

    def test_total_pulls_increments(self):
        ctrl = ExplorationController(seed=42)
        ctrl.record_outcome("balanced", 0.5)
        ctrl.record_outcome("aggressive", 0.3)
        assert ctrl.total_pulls == 2

    def test_epsilon_decays(self):
        ctrl = ExplorationController(seed=42, epsilon_start=0.3)
        initial_eps = ctrl.epsilon
        ctrl.record_outcome("balanced", 0.5)
        assert ctrl.epsilon < initial_eps

    def test_unknown_strategy_ignored(self):
        ctrl = ExplorationController(seed=42)
        ctrl.record_outcome("nonexistent_strategy", 0.5)
        assert ctrl.total_pulls == 0

    def test_best_reward_tracks_max(self):
        ctrl = ExplorationController(seed=42)
        ctrl.record_outcome("balanced", 0.3)
        ctrl.record_outcome("balanced", 0.9)
        ctrl.record_outcome("balanced", 0.5)
        assert ctrl.arms["balanced"].best_reward == pytest.approx(0.9)

    def test_history_grows(self):
        ctrl = ExplorationController(seed=42)
        ctrl.record_outcome("balanced", 0.5)
        ctrl.record_outcome("balanced", 0.6)
        assert len(ctrl.history) == 2


# ── UCB1 Scores ─────────────────────────────────────


class TestUCBScores:
    def test_unpulled_arms_have_inf_score(self):
        ctrl = ExplorationController(seed=42)
        ctrl.record_outcome("balanced", 0.5)
        scores = ctrl._compute_ucb_scores()
        for name in ctrl.arms:
            if name != "balanced":
                assert scores[name] == float("inf")

    def test_all_arms_have_scores(self):
        ctrl = ExplorationController(seed=42)
        scores = ctrl._compute_ucb_scores()
        assert set(scores.keys()) == set(ctrl.arms.keys())


# ── UCB Decision after warmup ───────────────────────


class TestUCBDecision:
    def _warmup(self, ctrl: ExplorationController) -> None:
        """Pull each arm twice so initial exploration phase ends."""
        for strategy in ctrl.strategies:
            ctrl.record_outcome(strategy, 0.5)
            ctrl.record_outcome(strategy, 0.5)

    def test_ucb_decision_after_warmup(self):
        ctrl = ExplorationController(seed=42, epsilon_start=0.0)
        self._warmup(ctrl)
        dec = ctrl.decide(current_score=50.0, score_trend=1.0)
        assert dec.mode in ("explore", "exploit", "hybrid")

    def test_exploit_mode_with_positive_trend(self):
        ctrl = ExplorationController(seed=42, epsilon_start=0.0)
        self._warmup(ctrl)
        # Give one arm a better reward so UCB picks it
        ctrl.record_outcome("balanced", 0.9)
        dec = ctrl.decide(current_score=60.0, score_trend=5.0)
        assert dec.mode == "exploit"

    def test_hybrid_mode_with_negative_trend(self):
        ctrl = ExplorationController(seed=42, epsilon_start=0.0)
        self._warmup(ctrl)
        dec = ctrl.decide(current_score=50.0, score_trend=-10.0)
        assert dec.mode == "hybrid"


# ── Stats ───────────────────────────────────────────


class TestGetStats:
    def test_returns_expected_keys(self):
        ctrl = ExplorationController(seed=42)
        stats = ctrl.get_stats()
        assert "epsilon" in stats
        assert "total_pulls" in stats
        assert "arms" in stats
        assert "best_strategy" in stats

    def test_best_strategy_none_initially(self):
        ctrl = ExplorationController(seed=42)
        stats = ctrl.get_stats()
        assert stats["best_strategy"] is None

    def test_best_strategy_after_outcomes(self):
        ctrl = ExplorationController(seed=42)
        ctrl.record_outcome("conservative", 0.3)
        ctrl.record_outcome("aggressive", 0.9)
        stats = ctrl.get_stats()
        assert stats["best_strategy"] == "aggressive"
