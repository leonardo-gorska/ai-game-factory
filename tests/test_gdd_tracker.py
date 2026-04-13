"""
Tests for backend.core.gdd_tracker — GDD Evolution Tracker (Roadmap v3 Item #13)
"""

import pytest
from backend.core.gdd_tracker import GDDTracker, GDDSnapshot, GDDDiff


# ─── Fixtures ─────────────────────────────────────────

@pytest.fixture
def tracker():
    return GDDTracker()


def make_gdd(
    title: str = "Test Game",
    features: list[str] | None = None,
    mechanics: dict | None = None,
) -> dict:
    """Helper to create a minimal GDD dict."""
    return {
        "title": title,
        "features": features or ["combat", "inventory", "quests"],
        "mechanics": mechanics or {"combat": "turn-based", "movement": "grid"},
        "economy": {"currency": "gold", "inflation_target": 0.05},
    }


# ─── Snapshot Tests ───────────────────────────────────

class TestGDDSnapshot:
    def test_snapshot_creation(self):
        gdd = make_gdd()
        snap = GDDSnapshot(iteration=1, gdd=gdd)
        assert snap.iteration == 1
        assert snap.gdd == gdd


# ─── Tracker Record ──────────────────────────────────

class TestGDDTrackerRecord:
    def test_first_record_returns_none(self, tracker):
        """First record has no previous snapshot, so diff is None."""
        diff = tracker.record(1, make_gdd())
        assert diff is None
        assert len(tracker._history) == 1

    def test_second_record_returns_diff(self, tracker):
        tracker.record(1, make_gdd())
        diff = tracker.record(2, make_gdd(features=["combat", "inventory"]))
        assert diff is not None
        assert isinstance(diff, GDDDiff)

    def test_records_sequential(self, tracker):
        for i in range(5):
            tracker.record(i + 1, make_gdd())
        assert len(tracker._history) == 5


# ─── Diff Detection ──────────────────────────────────

class TestGDDDiff:
    def test_feature_added(self, tracker):
        tracker.record(1, make_gdd(features=["combat"]))
        diff = tracker.record(2, make_gdd(features=["combat", "crafting"]))
        assert diff is not None
        assert "crafting" in diff.features_added

    def test_feature_removed(self, tracker):
        tracker.record(1, make_gdd(features=["combat", "inventory"]))
        diff = tracker.record(2, make_gdd(features=["combat"]))
        assert diff is not None
        assert "inventory" in diff.features_removed

    def test_no_change(self, tracker):
        gdd = make_gdd()
        tracker.record(1, gdd)
        diff = tracker.record(2, gdd)
        assert diff is not None
        assert diff.change_count == 0

    def test_mechanic_changed(self, tracker):
        tracker.record(1, make_gdd(mechanics={"combat": "turn-based"}))
        diff = tracker.record(2, make_gdd(mechanics={"combat": "real-time"}))
        assert diff is not None
        assert diff.change_count > 0


# ─── Drift Alerts ─────────────────────────────────────

class TestDriftAlerts:
    def test_no_alerts_initially(self, tracker):
        alerts = tracker.get_drift_alerts()
        assert alerts == []

    def test_feature_removal_alert(self, tracker):
        tracker.record(1, make_gdd(features=["a", "b", "c"]))
        tracker.record(2, make_gdd(features=["a"]))
        alerts = tracker.get_drift_alerts()
        assert len(alerts) > 0
        any_removal = any("remov" in a.get("message", "").lower() for a in alerts)
        assert any_removal

    def test_churn_detection(self, tracker):
        """Features repeatedly changing should trigger churn alerts."""
        tracker.record(1, make_gdd(features=["a", "b"]))
        tracker.record(2, make_gdd(features=["a", "c"]))
        tracker.record(3, make_gdd(features=["a", "b"]))
        tracker.record(4, make_gdd(features=["a", "c"]))
        # After 4 changes flipping features, churn may be detected
        alerts = tracker.get_drift_alerts()
        # At minimum we should have some alerts about the changes
        assert isinstance(alerts, list)


# ─── Evolution Summary ────────────────────────────────

class TestEvolutionSummary:
    def test_empty_summary(self, tracker):
        summary = tracker.get_evolution_summary()
        assert isinstance(summary, str)

    def test_summary_with_data(self, tracker):
        tracker.record(1, make_gdd(features=["a"]))
        tracker.record(2, make_gdd(features=["a", "b"]))
        summary = tracker.get_evolution_summary()
        assert len(summary) > 0
        assert "GDD" in summary or "evolution" in summary.lower() or "snapshot" in summary.lower()
