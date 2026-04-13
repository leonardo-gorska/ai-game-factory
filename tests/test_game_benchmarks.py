"""Tests for backend.core.game_benchmarks — Competitive Benchmark (Roadmap v2 Item 10)"""

import pytest
from backend.core.game_benchmarks import (
    BenchmarkComparator,
    BenchmarkReport,
    MetricGap,
    GENRE_BENCHMARKS,
    _INVERTED_METRICS,
)


# ── Genre Data Coverage ───────────────────────────────────

class TestGenreBenchmarks:
    """All genres from config.py should have benchmark data."""

    EXPECTED_GENRES = [
        "idle_rpg", "action", "puzzle", "tower_defense", "platformer",
        "racing", "roguelike", "survival", "strategy", "simulation",
    ]

    def test_all_config_genres_have_benchmarks(self):
        for genre in self.EXPECTED_GENRES:
            assert genre in GENRE_BENCHMARKS, f"Missing benchmark for genre '{genre}'"

    def test_all_genres_have_required_metrics(self):
        required = {"session_length_avg", "engagement_rate", "crash_rate_max",
                     "retention_d1", "retention_d7", "economy_inflation_max"}
        for genre, data in GENRE_BENCHMARKS.items():
            for metric in required:
                assert metric in data, f"Genre '{genre}' missing metric '{metric}'"

    def test_all_targets_are_positive(self):
        for genre, data in GENRE_BENCHMARKS.items():
            for metric, value in data.items():
                assert value > 0, f"Genre '{genre}' metric '{metric}' must be >0"


# ── BenchmarkComparator ──────────────────────────────────

class TestBenchmarkComparator:
    def setup_method(self):
        self.comparator = BenchmarkComparator()

    def test_compare_above_average(self):
        """Metrics exceeding targets should be in above_average."""
        metrics = {
            "session_length_avg": 20.0,    # idle_rpg target: 12.0
            "engagement_rate": 0.90,        # idle_rpg target: 0.68
        }
        report = self.comparator.compare(metrics, "idle_rpg")
        assert "session_length_avg" in report.above_average
        assert "engagement_rate" in report.above_average
        assert report.below_average == []

    def test_compare_below_average(self):
        """Metrics below targets should be in below_average."""
        metrics = {
            "session_length_avg": 5.0,     # idle_rpg target: 12.0
            "engagement_rate": 0.30,        # idle_rpg target: 0.68
        }
        report = self.comparator.compare(metrics, "idle_rpg")
        assert "session_length_avg" in report.below_average
        assert "engagement_rate" in report.below_average
        assert report.above_average == []

    def test_compare_inverted_metric_good(self):
        """For inverted metrics (crash_rate), lower is better."""
        metrics = {"crash_rate_max": 0.01}   # idle_rpg target: 0.02
        report = self.comparator.compare(metrics, "idle_rpg")
        assert "crash_rate_max" in report.above_average

    def test_compare_inverted_metric_bad(self):
        """For inverted metrics, exceeding the target is bad."""
        metrics = {"crash_rate_max": 0.10}   # idle_rpg target: 0.02
        report = self.comparator.compare(metrics, "idle_rpg")
        assert "crash_rate_max" in report.below_average

    def test_compare_unknown_genre(self):
        """Unknown genre should return empty report."""
        report = self.comparator.compare({"engagement_rate": 0.5}, "unknown_genre")
        assert report.genre == "unknown_genre"
        assert report.gaps == {}
        assert report.above_average == []
        assert report.below_average == []

    def test_compare_partial_metrics(self):
        """Only provided metrics should be compared; missing ones skipped."""
        metrics = {"engagement_rate": 0.90}   # Only one metric
        report = self.comparator.compare(metrics, "rpg")
        assert len(report.gaps) == 1
        assert "engagement_rate" in report.gaps

    def test_gap_pct_calculation(self):
        """Gap percentage should be calculated correctly."""
        metrics = {"session_length_avg": 12.0}  # rpg target: 15.0
        report = self.comparator.compare(metrics, "rpg")
        gap = report.gaps["session_length_avg"]
        assert gap.actual == 12.0
        assert gap.target == 15.0
        assert gap.gap_pct == pytest.approx(-20.0, abs=0.1)

    def test_gap_pct_inverted_calculation(self):
        """Inverted metric gap: below target is positive (good)."""
        metrics = {"crash_rate_max": 0.01}    # rpg target: 0.02
        report = self.comparator.compare(metrics, "rpg")
        gap = report.gaps["crash_rate_max"]
        assert gap.gap_pct > 0  # Positive = good for inverted


# ── BenchmarkReport ──────────────────────────────────────

class TestBenchmarkReport:
    def test_summary_empty_gaps(self):
        report = BenchmarkReport(genre="rpg")
        assert "No benchmark data" in report.summary

    def test_summary_with_above(self):
        report = BenchmarkReport(
            genre="rpg",
            gaps={"engagement_rate": MetricGap("engagement_rate", 0.90, 0.72, 25.0, False)},
            above_average=["engagement_rate"],
        )
        assert "Above average" in report.summary
        assert "engagement_rate" in report.summary

    def test_summary_with_below(self):
        gap = MetricGap("session_length_avg", 5.0, 15.0, -66.7, False)
        report = BenchmarkReport(
            genre="rpg",
            gaps={"session_length_avg": gap},
            below_average=["session_length_avg"],
        )
        assert "Below average" in report.summary
        assert "-67%" in report.summary or "-66%" in report.summary

    def test_to_dict(self):
        gap = MetricGap("engagement_rate", 0.90, 0.72, 25.0, False)
        report = BenchmarkReport(
            genre="rpg",
            gaps={"engagement_rate": gap},
            above_average=["engagement_rate"],
        )
        d = report.to_dict()
        assert d["genre"] == "rpg"
        assert "engagement_rate" in d["gaps"]
        assert d["gaps"]["engagement_rate"]["is_good"] is True
        assert d["above_average"] == ["engagement_rate"]
        assert isinstance(d["summary"], str)


# ── MetricGap ────────────────────────────────────────────

class TestMetricGap:
    def test_is_good_normal(self):
        gap = MetricGap("engagement_rate", 0.80, 0.72, 11.0, False)
        assert gap.is_good is True

    def test_is_bad_normal(self):
        gap = MetricGap("engagement_rate", 0.50, 0.72, -30.0, False)
        assert gap.is_good is False

    def test_is_good_inverted(self):
        gap = MetricGap("crash_rate_max", 0.01, 0.02, 50.0, True)
        assert gap.is_good is True

    def test_is_bad_inverted(self):
        gap = MetricGap("crash_rate_max", 0.05, 0.02, -150.0, True)
        assert gap.is_good is False
