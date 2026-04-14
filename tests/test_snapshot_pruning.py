"""
Tests for Snapshot Auto-pruning (#10).

Validates that _cleanup_old_snapshots uses score-based logic to keep
only the best snapshots, falling back to oldest-first when no scores
are available.
"""

import json
import shutil
from pathlib import Path
from unittest.mock import patch

import pytest

from backend.orchestrator.pipeline import Pipeline


@pytest.fixture
def pipeline():
    """Create a Pipeline instance for testing."""
    return Pipeline()


@pytest.fixture
def snapshot_dir(tmp_path):
    """Create a temporary snapshot directory and patch _SNAPSHOT_DIR."""
    snap_dir = tmp_path / ".snapshots"
    snap_dir.mkdir()
    return snap_dir


def _create_snapshot(snap_dir: Path, iteration: int, score: int | None = None) -> Path:
    """Helper: create a fake snapshot directory with optional score metadata."""
    d = snap_dir / f"iter_{iteration}"
    d.mkdir(parents=True, exist_ok=True)
    # Write a dummy file so the snapshot is not empty
    (d / "dummy.js").write_text("// placeholder", encoding="utf-8")
    # Write score metadata
    meta = {"iteration": iteration, "score": score}
    (d / "_score.json").write_text(json.dumps(meta), encoding="utf-8")
    return d


class TestSnapshotAutoPruning:
    """Tests for score-based snapshot pruning."""

    def test_no_pruning_under_limit(self, pipeline, snapshot_dir):
        """Snapshots <= _MAX_SNAPSHOTS should not be removed."""
        with patch.object(type(pipeline), "_SNAPSHOT_DIR", snapshot_dir):
            for i in range(1, 6):  # 5 snapshots = limit
                _create_snapshot(snapshot_dir, i, score=50 + i)
            pipeline._cleanup_old_snapshots()
            assert len(list(snapshot_dir.iterdir())) == 5
            assert pipeline._metrics["snapshots_pruned"] == 0

    def test_prune_lowest_score(self, pipeline, snapshot_dir):
        """When over limit, the lowest-scoring snapshot should be removed."""
        with patch.object(type(pipeline), "_SNAPSHOT_DIR", snapshot_dir):
            # 6 snapshots: scores 30, 50, 60, 70, 80, 90
            scores = [30, 50, 60, 70, 80, 90]
            for i, score in enumerate(scores, 1):
                _create_snapshot(snapshot_dir, i, score=score)

            pipeline._cleanup_old_snapshots()

            remaining = sorted(snapshot_dir.iterdir())
            assert len(remaining) == 5
            # iter_1 (score=30) should have been removed
            remaining_names = {d.name for d in remaining}
            assert "iter_1" not in remaining_names
            assert pipeline._metrics["snapshots_pruned"] == 1

    def test_prune_fallback_oldest(self, pipeline, snapshot_dir):
        """When all scores are equal, the oldest snapshot should be removed."""
        with patch.object(type(pipeline), "_SNAPSHOT_DIR", snapshot_dir):
            for i in range(1, 7):  # 6 snapshots, all score=50
                _create_snapshot(snapshot_dir, i, score=50)

            pipeline._cleanup_old_snapshots()

            remaining = sorted(snapshot_dir.iterdir())
            assert len(remaining) == 5
            # iter_1 (oldest) should have been removed
            remaining_names = {d.name for d in remaining}
            assert "iter_1" not in remaining_names
            assert pipeline._metrics["snapshots_pruned"] == 1

    def test_no_scores_fallback_oldest(self, pipeline, snapshot_dir):
        """Without scores, should fall back to removing the oldest."""
        with patch.object(type(pipeline), "_SNAPSHOT_DIR", snapshot_dir):
            for i in range(1, 7):
                _create_snapshot(snapshot_dir, i, score=None)

            pipeline._cleanup_old_snapshots()

            remaining = sorted(snapshot_dir.iterdir())
            assert len(remaining) == 5
            remaining_names = {d.name for d in remaining}
            assert "iter_1" not in remaining_names

    def test_never_remove_latest(self, pipeline, snapshot_dir):
        """The most recent snapshot must never be removed, even if lowest score."""
        with patch.object(type(pipeline), "_SNAPSHOT_DIR", snapshot_dir):
            # Latest (iter_6) has the lowest score
            scores = [80, 80, 80, 80, 80, 10]
            for i, score in enumerate(scores, 1):
                _create_snapshot(snapshot_dir, i, score=score)

            pipeline._cleanup_old_snapshots()

            remaining = sorted(snapshot_dir.iterdir())
            assert len(remaining) == 5
            remaining_names = {d.name for d in remaining}
            # iter_6 should survive (it's the latest)
            assert "iter_6" in remaining_names
            assert pipeline._metrics["snapshots_pruned"] == 1

    def test_metric_incremented_multiple(self, pipeline, snapshot_dir):
        """Pruning multiple snapshots should increment the metric accordingly."""
        with patch.object(type(pipeline), "_SNAPSHOT_DIR", snapshot_dir):
            # 8 snapshots → need to prune 3
            for i in range(1, 9):
                _create_snapshot(snapshot_dir, i, score=i * 10)

            pipeline._cleanup_old_snapshots()

            assert len(list(snapshot_dir.iterdir())) == 5
            assert pipeline._metrics["snapshots_pruned"] == 3

    def test_save_snapshot_writes_metadata(self, pipeline, snapshot_dir, tmp_path):
        """_save_snapshot should create _score.json with score=None."""
        src_dir = tmp_path / "game" / "src"
        src_dir.mkdir(parents=True)
        (src_dir / "main.js").write_text("// test", encoding="utf-8")

        with patch.object(type(pipeline), "_SNAPSHOT_DIR", snapshot_dir), \
             patch("backend.orchestrator.pipeline.GAME_DIR", tmp_path / "game"):
            pipeline._save_snapshot(5)

            snap = snapshot_dir / "iter_5"
            assert snap.exists()
            meta = json.loads((snap / "_score.json").read_text(encoding="utf-8"))
            assert meta["iteration"] == 5
            assert meta["score"] is None

    def test_update_snapshot_score(self, pipeline, snapshot_dir):
        """_update_snapshot_score should write the score into metadata."""
        with patch.object(type(pipeline), "_SNAPSHOT_DIR", snapshot_dir):
            _create_snapshot(snapshot_dir, 3, score=None)
            pipeline._update_snapshot_score(3, 75)

            meta_file = snapshot_dir / "iter_3" / "_score.json"
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
            assert meta["score"] == 75

    def test_get_snapshot_score(self, pipeline, snapshot_dir):
        """_get_snapshot_score should read scores correctly."""
        with patch.object(type(pipeline), "_SNAPSHOT_DIR", snapshot_dir):
            d = _create_snapshot(snapshot_dir, 1, score=42)
            assert pipeline._get_snapshot_score(d) == 42

            d2 = _create_snapshot(snapshot_dir, 2, score=None)
            assert pipeline._get_snapshot_score(d2) is None

    def test_has_snapshots_pruned_metric(self, pipeline):
        """Pipeline metrics should include snapshots_pruned counter."""
        assert "snapshots_pruned" in pipeline._metrics
        assert pipeline._metrics["snapshots_pruned"] == 0

    def test_max_snapshots_is_five(self, pipeline):
        """_MAX_SNAPSHOTS should be 5 per the requirement."""
        assert pipeline._MAX_SNAPSHOTS == 5
