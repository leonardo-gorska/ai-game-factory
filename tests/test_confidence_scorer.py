"""
Tests for backend.core.confidence_scorer — Agent Confidence Scoring (Roadmap v3 Item #14)
"""

import pytest
from backend.core.confidence_scorer import ConfidenceScorer, ConfidenceRecord


# ─── Fixtures ─────────────────────────────────────────

@pytest.fixture
def scorer():
    return ConfidenceScorer(retry_threshold=40, max_retries=1)


# ─── Extraction Tests ─────────────────────────────────

class TestExtractConfidence:
    def test_basic_json(self):
        text = '{"output": "hello", "confidence": 85}'
        assert ConfidenceScorer.extract_confidence(text) == 85

    def test_high_confidence(self):
        text = '{"confidence": 100, "data": "x"}'
        assert ConfidenceScorer.extract_confidence(text) == 100

    def test_zero_confidence(self):
        text = '{"confidence": 0}'
        assert ConfidenceScorer.extract_confidence(text) == 0

    def test_clamp_over_100(self):
        text = '{"confidence": 150}'
        assert ConfidenceScorer.extract_confidence(text) == 100

    def test_no_confidence(self):
        text = '{"output": "no confidence here"}'
        assert ConfidenceScorer.extract_confidence(text) == -1

    def test_empty_string(self):
        assert ConfidenceScorer.extract_confidence("") == -1

    def test_multi_line(self):
        text = '''
        {
            "analysis": "detailed",
            "confidence": 72,
            "notes": "..."
        }
        '''
        assert ConfidenceScorer.extract_confidence(text) == 72


# ─── Retry Logic Tests ───────────────────────────────

class TestRetryLogic:
    def test_should_retry_low(self, scorer):
        assert scorer.should_retry("designer", 20) is True

    def test_should_not_retry_high(self, scorer):
        assert scorer.should_retry("designer", 85) is False

    def test_should_not_retry_negative(self, scorer):
        assert scorer.should_retry("designer", -1) is False

    def test_max_retries_respected(self, scorer):
        scorer._current_retries["designer"] = 1
        assert scorer.should_retry("designer", 20) is False

    def test_reset_iteration_retries(self, scorer):
        scorer._current_retries["designer"] = 1
        scorer.reset_iteration_retries()
        assert scorer.should_retry("designer", 20) is True


# ─── Retry Params Tests ──────────────────────────────

class TestRetryParams:
    def test_moderate_low(self, scorer):
        params = scorer.suggest_retry_params("designer", 35)
        assert "temperature" in params
        assert params["temperature"] < 0.7

    def test_very_low(self, scorer):
        params = scorer.suggest_retry_params("designer", 15)
        assert params.get("tier_override") == "high"
        assert params["temperature"] < 0.5

    def test_at_threshold(self, scorer):
        params = scorer.suggest_retry_params("designer", 40)
        assert params == {}


# ─── Recording Tests ──────────────────────────────────

class TestRecording:
    def test_basic_record(self, scorer):
        scorer.record("designer", 1, 80)
        assert len(scorer._history["designer"]) == 1

    def test_retry_record(self, scorer):
        scorer.record("designer", 1, 30)
        scorer.record("designer", 1, 70, retried=True, original_confidence=30)
        records = scorer._history["designer"]
        assert len(records) == 2
        assert records[1].retried is True
        assert records[1].improved is True

    def test_no_improvement(self, scorer):
        scorer.record("designer", 1, 30)
        scorer.record("designer", 1, 25, retried=True, original_confidence=30)
        assert scorer._history["designer"][1].improved is False


# ─── Stats Tests ──────────────────────────────────────

class TestStats:
    def test_empty_stats(self, scorer):
        stats = scorer.get_stats()
        assert stats["total_records"] == 0

    def test_stats_after_records(self, scorer):
        scorer.record("designer", 1, 80)
        scorer.record("developer", 1, 60)
        stats = scorer.get_stats()
        assert stats["total_records"] == 2
        assert stats["agents_tracked"] == 2
        assert stats["global_avg_confidence"] == 70.0

    def test_agent_stats(self, scorer):
        for i in range(5):
            scorer.record("designer", i + 1, 50 + i * 10)
        stats = scorer.get_agent_stats("designer")
        assert stats["total_records"] == 5
        assert stats["min_confidence"] == 50
        assert stats["max_confidence"] == 90

    def test_unknown_agent_stats(self, scorer):
        stats = scorer.get_agent_stats("nonexistent")
        assert stats["total_records"] == 0


# ─── Low Confidence Agents ───────────────────────────

class TestLowConfidenceAgents:
    def test_no_low(self, scorer):
        scorer.record("designer", 1, 80)
        assert scorer.get_low_confidence_agents() == []

    def test_low_agent(self, scorer):
        for i in range(5):
            scorer.record("bad_agent", i + 1, 20)
        low = scorer.get_low_confidence_agents()
        assert len(low) == 1
        assert low[0]["agent"] == "bad_agent"
