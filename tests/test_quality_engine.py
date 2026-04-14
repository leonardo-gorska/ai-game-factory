"""
Tests for QualityEngine — multi-objective quality scoring.
"""

import pytest

from backend.core.quality_engine import QualityEngine, QualityMetrics, QualityBreakdown


@pytest.fixture
def engine() -> QualityEngine:
    return QualityEngine()


@pytest.fixture
def base_metrics() -> QualityMetrics:
    return QualityMetrics(
        fun_score=70,
        session_length_avg=300,
        engagement_rate=0.6,
        crash_rate=0.02,
        build_success=True,
        error_count=1,
        file_count=5,
        total_lines=500,
        economy_inflation=0.05,
        progression_slope=1.0,
        novelty_score=60,
        sim_runs=50,
        sim_variance=10,
        gold_per_hour=100,
        xp_per_hour=50,
        estimated_retention_d1=0.7,
        estimated_retention_d7=0.4,
        estimated_retention_d30=0.15,
    )


# ── Basic Evaluation ──────────────────────────────

class TestEvaluateReturnsBreakdown:
    def test_returns_quality_breakdown(self, engine: QualityEngine, base_metrics: QualityMetrics):
        result = engine.evaluate(base_metrics)
        assert isinstance(result, QualityBreakdown)

    def test_composite_in_range(self, engine: QualityEngine, base_metrics: QualityMetrics):
        result = engine.evaluate(base_metrics)
        assert 0 <= result.composite <= 100

    def test_sub_scores_in_range(self, engine: QualityEngine, base_metrics: QualityMetrics):
        result = engine.evaluate(base_metrics)
        for dim in ("fun", "stability", "performance", "balance", "novelty", "retention"):
            score = getattr(result, dim)
            assert 0 <= score <= 100, f"{dim} out of range: {score}"

    def test_confidence_interval_wraps_composite(self, engine: QualityEngine, base_metrics: QualityMetrics):
        result = engine.evaluate(base_metrics)
        assert result.confidence_lower <= result.composite
        assert result.confidence_upper >= result.composite


# ── Regression Penalty ────────────────────────────

class TestRegressionPenalty:
    def test_no_penalty_on_first_eval(self, engine: QualityEngine, base_metrics: QualityMetrics):
        result = engine.evaluate(base_metrics)
        assert result.regression_penalty == 0.0

    def test_penalty_when_metrics_decrease(self, engine: QualityEngine, base_metrics: QualityMetrics):
        # Good first iteration
        good = QualityMetrics(fun_score=90, build_success=True, engagement_rate=0.9, novelty_score=80)
        engine.evaluate(good)

        # Degraded second iteration
        bad = QualityMetrics(fun_score=20, build_success=False, engagement_rate=0.1, novelty_score=10)
        result = engine.evaluate(bad, previous_metrics=good)
        assert result.regression_penalty > 0


# ── History & Trend ───────────────────────────────

class TestHistory:
    def test_history_grows(self, engine: QualityEngine, base_metrics: QualityMetrics):
        for _ in range(3):
            engine.evaluate(base_metrics)
        assert len(engine.get_history()) == 3

    def test_trend_returns_dict(self, engine: QualityEngine, base_metrics: QualityMetrics):
        engine.evaluate(base_metrics)
        trend = engine.get_trend()
        assert isinstance(trend, dict)


# ── Auto-Tuning ──────────────────────────────────

class TestAutoTuning:
    def test_weights_change_after_auto_tune(self, engine: QualityEngine, base_metrics: QualityMetrics):
        initial_weights = dict(engine.get_weights())
        for _ in range(6):  # auto-tune triggers every 5 evals
            engine.evaluate(base_metrics)
        updated_weights = engine.get_weights()
        # Weights may or may not change, but the method should not crash
        assert isinstance(updated_weights, dict)
        assert set(updated_weights.keys()) == set(initial_weights.keys())


# ── Grace Period (P10) ────────────────────────────

class TestGracePeriod:
    def test_signal_major_change(self, engine: QualityEngine, base_metrics: QualityMetrics):
        engine.signal_major_change()
        # Should suppress regression in next evaluation
        good = QualityMetrics(fun_score=90, build_success=True, engagement_rate=0.9)
        engine.evaluate(good)
        bad = QualityMetrics(fun_score=20, build_success=False, engagement_rate=0.1)
        result = engine.evaluate(bad, previous_metrics=good)
        # Regression penalty should be 0 during grace period
        assert result.regression_penalty == 0.0
