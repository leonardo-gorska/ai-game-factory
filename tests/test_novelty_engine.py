"""
Tests for backend.core.novelty_engine — NoveltyEngine

Covers: GDD feature extraction, Jaccard distance, novelty scoring,
centroid sliding window, stats reporting.
"""

import pytest
from pathlib import Path
from unittest.mock import patch

from backend.core.novelty_engine import NoveltyEngine


# ── Feature Extraction ──────────────────────────────


class TestExtractGDDFeatures:
    def test_extracts_top_level_keys(self):
        gdd = {"combat": {}, "economy": {}}
        features = NoveltyEngine.extract_gdd_features(gdd)
        assert "combat" in features
        assert "economy" in features

    def test_extracts_nested_keys(self):
        gdd = {"combat": {"attack": "sword", "defense": "shield"}}
        features = NoveltyEngine.extract_gdd_features(gdd)
        assert "combat.attack" in features
        assert "combat.defense" in features

    def test_extracts_list_strings(self):
        gdd = {"features": ["auto combat", "idle rewards"]}
        features = NoveltyEngine.extract_gdd_features(gdd)
        assert "auto_combat" in features
        assert "idle_rewards" in features

    def test_ignores_long_strings(self):
        gdd = {"description": "a" * 100}
        features = NoveltyEngine.extract_gdd_features(gdd)
        # Strings >= 50 chars should be ignored
        assert ("a" * 100) not in features

    def test_empty_gdd_returns_empty_set(self):
        features = NoveltyEngine.extract_gdd_features({})
        assert features == set()


# ── Jaccard Distance ────────────────────────────────


class TestJaccardDistance:
    def test_identical_sets_zero_distance(self):
        s = {"a", "b", "c"}
        assert NoveltyEngine._jaccard_distance(s, s) == pytest.approx(0.0)

    def test_disjoint_sets_max_distance(self):
        a = {"x", "y"}
        b = {"p", "q"}
        assert NoveltyEngine._jaccard_distance(a, b) == pytest.approx(1.0)

    def test_partial_overlap(self):
        a = {"a", "b", "c"}
        b = {"b", "c", "d"}
        # intersection = {b,c} = 2, union = {a,b,c,d} = 4
        assert NoveltyEngine._jaccard_distance(a, b) == pytest.approx(0.5)

    def test_empty_sets_zero_distance(self):
        assert NoveltyEngine._jaccard_distance(set(), set()) == pytest.approx(0.0)

    def test_one_empty_set_max_distance(self):
        assert NoveltyEngine._jaccard_distance({"a"}, set()) == pytest.approx(1.0)


# ── Compute Novelty ─────────────────────────────────


class TestComputeNovelty:
    def _make_engine(self) -> NoveltyEngine:
        # Use a fake game_dir that doesn't exist; code fingerprint will be empty
        return NoveltyEngine(game_dir=Path("/tmp/_fake_novelty_test_dir"))

    def test_first_iteration_returns_neutral(self):
        engine = self._make_engine()
        score = engine.compute_novelty({"combat": {}})
        assert score == pytest.approx(50.0)

    def test_identical_gdd_low_novelty(self):
        engine = self._make_engine()
        gdd = {"combat": {"attack": "sword"}, "economy": {"gold": 100}}
        engine.record_iteration(gdd, code_fingerprint=set())
        score = engine.compute_novelty(gdd, code_fingerprint=set())
        assert score < 15  # Should be near zero (identical)

    def test_different_gdd_higher_novelty(self):
        engine = self._make_engine()
        gdd1 = {"combat": {"attack": "sword"}}
        gdd2 = {"crafting": {"recipe": "potion"}, "quests": {"daily": True}}
        engine.record_iteration(gdd1, code_fingerprint=set())
        score = engine.compute_novelty(gdd2, code_fingerprint=set())
        assert score > 30  # Should be significantly higher

    def test_novelty_score_in_range(self):
        engine = self._make_engine()
        engine.record_iteration({"a": 1}, code_fingerprint=set())
        score = engine.compute_novelty({"z": 99}, code_fingerprint=set())
        assert 0.0 <= score <= 100.0

    def test_code_fingerprint_affects_novelty(self):
        engine = self._make_engine()
        gdd = {"combat": {}}
        engine.record_iteration(gdd, code_fingerprint={"class:Combat", "func:attack"})
        score_same = engine.compute_novelty(
            gdd, code_fingerprint={"class:Combat", "func:attack"}
        )
        score_diff = engine.compute_novelty(
            gdd, code_fingerprint={"class:Crafting", "func:brew"}
        )
        assert score_diff > score_same


# ── Record Iteration ────────────────────────────────


class TestRecordIteration:
    def _make_engine(self) -> NoveltyEngine:
        return NoveltyEngine(game_dir=Path("/tmp/_fake_novelty_test_dir"))

    def test_history_grows(self):
        engine = self._make_engine()
        engine.record_iteration({"a": 1}, code_fingerprint=set())
        engine.record_iteration({"b": 2}, code_fingerprint=set())
        assert len(engine._gdd_history) == 2

    def test_centroid_updated(self):
        engine = self._make_engine()
        engine.record_iteration({"combat": {}}, code_fingerprint=set())
        assert "combat" in engine._gdd_centroid

    def test_centroid_sliding_window(self):
        engine = self._make_engine()
        # Record more than CENTROID_WINDOW iterations
        for i in range(60):
            engine.record_iteration({f"feat_{i}": {}}, code_fingerprint=set())
        # First features should still be in centroid (window=50 covers 10..59)
        assert "feat_0" not in engine._gdd_centroid
        assert "feat_59" in engine._gdd_centroid


# ── Stats ───────────────────────────────────────────


class TestGetStats:
    def test_initial_stats(self):
        engine = NoveltyEngine(game_dir=Path("/tmp/_fake_novelty_test_dir"))
        stats = engine.get_stats()
        assert stats["iterations_recorded"] == 0
        assert stats["gdd_centroid_size"] == 0

    def test_stats_after_recording(self):
        engine = NoveltyEngine(game_dir=Path("/tmp/_fake_novelty_test_dir"))
        engine.record_iteration({"x": 1, "y": 2}, code_fingerprint=set())
        stats = engine.get_stats()
        assert stats["iterations_recorded"] == 1
        assert stats["recent_gdd_features"] > 0
