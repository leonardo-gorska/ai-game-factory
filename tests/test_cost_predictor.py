"""
Tests for CostPredictor — pre-call cost estimation and budget warnings.
"""

import pytest

from backend.llm.cost_predictor import CostPredictor, CostPrediction


@pytest.fixture
def predictor() -> CostPredictor:
    return CostPredictor()


# ── Token estimation ─────────────────────────────

class TestEstimateTokens:
    def test_basic(self, predictor: CostPredictor):
        messages = [{"role": "user", "content": "a" * 400}]
        inp, out = predictor.estimate_tokens(messages, max_tokens=1000)
        assert inp == 100  # 400 chars / 4
        assert out == 500  # 1000 / 2

    def test_multiple_messages(self, predictor: CostPredictor):
        messages = [
            {"role": "system", "content": "x" * 200},
            {"role": "user", "content": "y" * 200},
        ]
        inp, out = predictor.estimate_tokens(messages, max_tokens=2000)
        assert inp == 100  # (200+200) / 4
        assert out == 1000

    def test_empty_messages(self, predictor: CostPredictor):
        inp, out = predictor.estimate_tokens([], max_tokens=100)
        assert inp == 1  # minimum
        assert out == 50


# ── Cost computation ─────────────────────────────

class TestEstimateCost:
    def test_known_provider(self, predictor: CostPredictor):
        # gemini: $0.001/1M input + $0.001/1M output
        cost = predictor.estimate_cost("gemini", 1_000_000, 1_000_000)
        assert cost == pytest.approx(0.002, abs=1e-6)

    def test_unknown_provider_uses_fallback(self, predictor: CostPredictor):
        # fallback: $0.10/1M each
        cost = predictor.estimate_cost("some_new_provider", 1_000_000, 1_000_000)
        assert cost == pytest.approx(0.20, abs=1e-6)

    def test_zero_tokens(self, predictor: CostPredictor):
        cost = predictor.estimate_cost("gemini", 0, 0)
        assert cost == 0.0


# ── Full check ───────────────────────────────────

class TestCheck:
    def test_under_budget_no_warning(self, predictor: CostPredictor):
        messages = [{"role": "user", "content": "hello"}]
        pred = predictor.check("gemini", messages, max_tokens=100, budget_remaining=1.0)
        assert isinstance(pred, CostPrediction)
        assert pred.over_budget is False
        assert pred.warning is None
        assert pred.estimated_cost_usd < 1.0

    def test_over_budget_warns(self, predictor: CostPredictor):
        # Use a long message + unknown (expensive) provider with tiny budget
        messages = [{"role": "user", "content": "x" * 4_000_000}]
        pred = predictor.check(
            "some_new_provider", messages, max_tokens=4096,
            budget_remaining=0.0001,
        )
        assert pred.over_budget is True
        assert pred.warning is not None
        assert "exceeds" in pred.warning

    def test_prediction_fields(self, predictor: CostPredictor):
        messages = [{"role": "user", "content": "test prompt"}]
        pred = predictor.check("groq", messages, max_tokens=500, budget_remaining=5.0)
        assert pred.estimated_input_tokens > 0
        assert pred.estimated_output_tokens > 0
        assert pred.estimated_cost_usd >= 0
        assert pred.budget_remaining_usd == 5.0
