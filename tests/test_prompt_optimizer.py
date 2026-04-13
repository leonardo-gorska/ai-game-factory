"""
Tests for PromptOptimizer — Adaptive Prompt Tuning (Roadmap v3 Item #3).
"""

import json
import pytest
from pathlib import Path
from unittest.mock import patch

from backend.llm.prompt_optimizer import (
    PromptOptimizer,
    PromptRecord,
    PromptSuggestion,
    compute_prompt_hash,
    DEFAULT_TEMPERATURE,
    MIN_TEMPERATURE,
    MAX_TEMPERATURE,
    EXPLORATION_RATIO,
    MIN_RECORDS_FOR_SUGGESTION,
)


# ── Helper ──────────────────────────────────────────────

@pytest.fixture
def optimizer(tmp_path: Path) -> PromptOptimizer:
    """Create a fresh PromptOptimizer with isolated storage."""
    with patch("backend.llm.prompt_optimizer._TUNING_FILE", tmp_path / "prompt_tuning.json"):
        opt = PromptOptimizer()
        yield opt


def _seed_optimizer(opt: PromptOptimizer, agent: str, n: int = 5, base_temp: float = 0.7) -> None:
    """Seed optimizer with N records for an agent."""
    for i in range(n):
        opt.record(agent, f"hash_{i}", base_temp, quality_delta=float(i), tokens_used=100 * (i + 1))


# ── PromptRecord ────────────────────────────────────────

class TestPromptRecord:
    def test_create_record(self):
        rec = PromptRecord(
            agent="developer",
            prompt_hash="abc123",
            temperature=0.7,
            quality_delta=2.5,
            tokens_used=1500,
        )
        assert rec.agent == "developer"
        assert rec.prompt_hash == "abc123"
        assert rec.temperature == 0.7
        assert rec.quality_delta == 2.5
        assert rec.tokens_used == 1500
        assert rec.timestamp != ""

    def test_to_dict_roundtrip(self):
        rec = PromptRecord(
            agent="designer",
            prompt_hash="xyz",
            temperature=0.5,
            quality_delta=-1.0,
            tokens_used=800,
        )
        d = rec.to_dict()
        restored = PromptRecord.from_dict(d)
        assert restored.agent == rec.agent
        assert restored.prompt_hash == rec.prompt_hash
        assert restored.temperature == rec.temperature
        assert restored.quality_delta == rec.quality_delta
        assert restored.tokens_used == rec.tokens_used


# ── PromptSuggestion ───────────────────────────────────

class TestPromptSuggestion:
    def test_default_values(self):
        s = PromptSuggestion()
        assert s.temperature == DEFAULT_TEMPERATURE
        assert s.variant_id == "default"
        assert s.is_exploration is False

    def test_to_dict(self):
        s = PromptSuggestion(temperature=0.9, variant_id="test", is_exploration=True)
        d = s.to_dict()
        assert d["temperature"] == 0.9
        assert d["variant_id"] == "test"
        assert d["is_exploration"] is True


# ── compute_prompt_hash ────────────────────────────────

class TestComputePromptHash:
    def test_returns_12_char_hex(self):
        h = compute_prompt_hash("Hello World")
        assert isinstance(h, str)
        assert len(h) == 12

    def test_same_input_same_hash(self):
        assert compute_prompt_hash("test") == compute_prompt_hash("test")

    def test_different_input_different_hash(self):
        assert compute_prompt_hash("a") != compute_prompt_hash("b")


# ── PromptOptimizer ────────────────────────────────────

class TestRecord:
    def test_record_creates_entry(self, optimizer: PromptOptimizer):
        rec = optimizer.record("developer", "hash1", 0.7, 3.0, 1000)
        assert isinstance(rec, PromptRecord)
        assert rec.agent == "developer"

    def test_multiple_records_per_agent(self, optimizer: PromptOptimizer):
        for i in range(5):
            optimizer.record("dev", f"h{i}", 0.7, float(i))
        stats = optimizer.get_stats("dev")
        assert stats["total_records"] == 5

    def test_cap_enforced(self, optimizer: PromptOptimizer):
        for i in range(PromptOptimizer.MAX_RECORDS_PER_AGENT + 50):
            optimizer.record("dev", f"h{i}", 0.7, 1.0)
        stats = optimizer.get_stats("dev")
        assert stats["total_records"] <= PromptOptimizer.MAX_RECORDS_PER_AGENT


class TestGetBestConfig:
    def test_empty_returns_defaults(self, optimizer: PromptOptimizer):
        best = optimizer.get_best_config("unknown_agent")
        assert best.temperature == DEFAULT_TEMPERATURE
        assert best.variant_id == "default"
        assert best.is_exploration is False

    def test_insufficient_data_returns_defaults(self, optimizer: PromptOptimizer):
        optimizer.record("dev", "h1", 0.7, 5.0)
        best = optimizer.get_best_config("dev")
        assert best.temperature == DEFAULT_TEMPERATURE

    def test_finds_best_temperature(self, optimizer: PromptOptimizer):
        # Temperature 0.5 → good results
        for _ in range(5):
            optimizer.record("dev", "h1", 0.5, quality_delta=8.0)
        # Temperature 0.7 → mediocre results
        for _ in range(5):
            optimizer.record("dev", "h2", 0.7, quality_delta=2.0)

        best = optimizer.get_best_config("dev")
        assert best.temperature == 0.5
        assert best.variant_id == "optimized"


class TestSuggestVariant:
    def test_returns_suggestion(self, optimizer: PromptOptimizer):
        _seed_optimizer(optimizer, "dev", n=5)
        suggestion = optimizer.suggest_variant("dev")
        assert isinstance(suggestion, PromptSuggestion)
        assert MIN_TEMPERATURE <= suggestion.temperature <= MAX_TEMPERATURE

    def test_ab_test_produces_explorations(self, optimizer: PromptOptimizer):
        _seed_optimizer(optimizer, "dev", n=10)

        exploration_count = 0
        n_trials = 200
        for _ in range(n_trials):
            s = optimizer.suggest_variant("dev")
            if s.is_exploration:
                exploration_count += 1

        # Expect roughly EXPLORATION_RATIO ± tolerance
        ratio = exploration_count / n_trials
        assert 0.05 < ratio < 0.45, f"Exploration ratio {ratio:.2f} is out of expected range"


class TestGetStats:
    def test_empty_stats(self, optimizer: PromptOptimizer):
        stats = optimizer.get_stats()
        assert stats["total_records"] == 0
        assert stats["agents"] == {}

    def test_per_agent_stats(self, optimizer: PromptOptimizer):
        _seed_optimizer(optimizer, "dev", n=5)
        _seed_optimizer(optimizer, "designer", n=3)

        stats = optimizer.get_stats()
        assert stats["total_records"] == 8
        assert "dev" in stats["agents"]
        assert "designer" in stats["agents"]
        assert stats["agents"]["dev"]["total_records"] == 5
        assert stats["agents"]["designer"]["total_records"] == 3

    def test_single_agent_stats(self, optimizer: PromptOptimizer):
        _seed_optimizer(optimizer, "dev", n=5)
        stats = optimizer.get_stats("dev")
        assert stats["total_records"] == 5
        assert "avg_quality_delta" in stats
        assert "best_temperature" in stats
        assert "unique_prompts" in stats


class TestPersistence:
    def test_save_and_load(self, tmp_path: Path):
        tuning_file = tmp_path / "prompt_tuning.json"

        with patch("backend.llm.prompt_optimizer._TUNING_FILE", tuning_file):
            opt1 = PromptOptimizer()
            _seed_optimizer(opt1, "dev", n=5)
            assert tuning_file.exists()

            # Load in a new instance
            opt2 = PromptOptimizer()
            stats = opt2.get_stats("dev")
            assert stats["total_records"] == 5
