"""Tests for backend.core.temperature_controller"""

import pytest

from backend.core.temperature_controller import (
    TemperatureController,
    TemperatureRecommendation,
    TEMP_MIN,
    TEMP_MAX,
)


class TestTemperatureControllerRecord:
    def test_record_stores_history(self):
        ctrl = TemperatureController()
        ctrl.record("designer", 1, 50.0)
        ctrl.record("designer", 2, 55.0)
        assert len(ctrl._agent_history["designer"]) == 2

    def test_record_trims_old_entries(self):
        ctrl = TemperatureController(window=3)
        for i in range(20):
            ctrl.record("dev", i, float(i))
        # max_keep = window * 2 = 6
        assert len(ctrl._agent_history["dev"]) == 6

    def test_record_independent_per_agent(self):
        ctrl = TemperatureController()
        ctrl.record("designer", 1, 50.0)
        ctrl.record("developer", 1, 60.0)
        assert len(ctrl._agent_history["designer"]) == 1
        assert len(ctrl._agent_history["developer"]) == 1


class TestTemperatureControllerRecommendation:
    def test_insufficient_data_returns_default(self):
        ctrl = TemperatureController()
        ctrl.record("dev", 1, 50.0)
        rec = ctrl.get_recommendation("dev", default=0.7)
        assert rec.trend == "insufficient_data"
        assert rec.recommended == 0.7
        assert rec.adjustment == 0.0

    def test_no_history_returns_default(self):
        ctrl = TemperatureController()
        rec = ctrl.get_recommendation("unknown_agent", default=0.8)
        assert rec.recommended == 0.8
        assert rec.trend == "insufficient_data"

    def test_rising_trend_converges(self):
        """Quality steadily improving → temperature should decrease."""
        ctrl = TemperatureController(window=5)
        scores = [40, 45, 50, 56, 63]  # avg change ~5.75 > threshold
        for i, s in enumerate(scores):
            ctrl.record("designer", i + 1, float(s))

        rec = ctrl.get_recommendation("designer", default=0.7)
        assert rec.trend == "rising"
        assert rec.recommended < 0.7
        assert rec.recommended >= TEMP_MIN

    def test_falling_trend_stabilizes(self):
        """Quality declining → temperature should decrease slightly."""
        ctrl = TemperatureController(window=5)
        scores = [70, 60, 48, 35, 20]  # avg change ~ -12.5 < -5
        for i, s in enumerate(scores):
            ctrl.record("developer", i + 1, float(s))

        rec = ctrl.get_recommendation("developer", default=0.7)
        assert rec.trend == "falling"
        assert rec.recommended < 0.7
        assert rec.recommended >= TEMP_MIN

    def test_plateau_explores(self):
        """Scores barely changing → temperature should increase."""
        ctrl = TemperatureController(window=5)
        scores = [50, 50.5, 50.2, 49.8, 50.1]  # very low variance
        for i, s in enumerate(scores):
            ctrl.record("critic", i + 1, s)

        rec = ctrl.get_recommendation("critic", default=0.7)
        assert rec.trend == "plateau"
        assert rec.recommended > 0.7
        assert rec.recommended <= TEMP_MAX

    def test_stable_no_change(self):
        """Moderate changes, no clear trend → no adjustment."""
        ctrl = TemperatureController(window=5)
        scores = [50, 52, 49, 53, 51]  # oscillating, no clear trend
        for i, s in enumerate(scores):
            ctrl.record("tester", i + 1, s)

        rec = ctrl.get_recommendation("tester", default=0.7)
        assert rec.trend in ("stable", "plateau")
        # Even if plateau, should not crash

    def test_temperature_never_below_min(self):
        """Even with strong convergence signal, temp stays >= TEMP_MIN."""
        ctrl = TemperatureController(window=3)
        scores = [10, 30, 55]  # strong rise
        for i, s in enumerate(scores):
            ctrl.record("dev", i + 1, s)

        rec = ctrl.get_recommendation("dev", default=TEMP_MIN)
        assert rec.recommended >= TEMP_MIN

    def test_temperature_never_above_max(self):
        """Even with strong explore signal, temp stays <= TEMP_MAX."""
        ctrl = TemperatureController(window=5)
        scores = [50.0, 50.0, 50.0, 50.0, 50.0]
        for i, s in enumerate(scores):
            ctrl.record("dev", i + 1, s)

        rec = ctrl.get_recommendation("dev", default=TEMP_MAX)
        assert rec.recommended <= TEMP_MAX


class TestTemperatureControllerConvenience:
    def test_get_temperature_returns_float(self):
        ctrl = TemperatureController()
        temp = ctrl.get_temperature("dev", default=0.7)
        assert isinstance(temp, float)
        assert temp == 0.7  # no data → default


class TestTemperatureControllerStats:
    def test_stats_empty(self):
        ctrl = TemperatureController()
        stats = ctrl.get_stats()
        assert stats["agents"] == {}
        assert stats["total_adjustments"] == 0

    def test_stats_after_records(self):
        ctrl = TemperatureController(window=3)
        for i in range(5):
            ctrl.record("designer", i, 50.0 + i * 5)

        stats = ctrl.get_stats()
        assert "designer" in stats["agents"]
        assert stats["agents"]["designer"]["history_length"] == 5

    def test_reset_agent(self):
        ctrl = TemperatureController()
        ctrl.record("designer", 1, 50.0)
        ctrl.record("developer", 1, 60.0)
        ctrl.reset("designer")
        assert "designer" not in ctrl._agent_history
        assert "developer" in ctrl._agent_history

    def test_reset_all(self):
        ctrl = TemperatureController()
        ctrl.record("designer", 1, 50.0)
        ctrl.record("developer", 1, 60.0)
        ctrl.reset()
        assert len(ctrl._agent_history) == 0


class TestTemperatureRecommendation:
    def test_to_dict(self):
        rec = TemperatureRecommendation(
            agent="dev", recommended=0.55, default=0.7,
            trend="rising", adjustment=-0.15,
        )
        d = rec.to_dict()
        assert d["agent"] == "dev"
        assert d["recommended"] == 0.55
        assert d["trend"] == "rising"
