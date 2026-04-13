"""
GORVAX GAME FACTORY — Game Versioner
Manages version snapshots of the game across iterations.
"""

from __future__ import annotations

import json
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.config import GAME_DIR, ITERATIONS_DIR

logger = logging.getLogger(__name__)


class GameVersioner:
    """
    Version control for game iterations.
    Saves and restores snapshots of the game source code.
    """

    def __init__(
        self,
        game_dir: Path | None = None,
        iterations_dir: Path | None = None,
    ) -> None:
        self._game_dir = game_dir or GAME_DIR
        self._iterations_dir = iterations_dir or ITERATIONS_DIR
        self._iterations_dir.mkdir(parents=True, exist_ok=True)

    def save_snapshot(
        self,
        iteration: int,
        score: int = 0,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """
        Save a snapshot of the current game source.
        Returns the snapshot directory path.
        """
        snapshot_dir = self._iterations_dir / f"iter_{iteration:05d}"
        snapshot_dir.mkdir(parents=True, exist_ok=True)

        # Copy game source files
        game_src = self._game_dir / "src"
        snapshot_src = snapshot_dir / "src"

        if game_src.exists():
            if snapshot_src.exists():
                shutil.rmtree(snapshot_src)
            shutil.copytree(game_src, snapshot_src)

        # Save metadata
        meta = {
            "iteration": iteration,
            "score": score,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "files": [],
            **(metadata or {}),
        }

        if game_src.exists():
            meta["files"] = [
                str(f.relative_to(game_src))
                for f in game_src.rglob("*.js")
            ]

        meta_path = snapshot_dir / "metadata.json"
        meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

        logger.info(
            "📸 Saved snapshot: iter %d (score: %d, files: %d)",
            iteration,
            score,
            len(meta["files"]),
        )

        return str(snapshot_dir)

    def restore_snapshot(self, iteration: int) -> bool:
        """
        Restore a previous snapshot to the game directory.
        Returns True if successful.
        """
        snapshot_dir = self._iterations_dir / f"iter_{iteration:05d}"
        snapshot_src = snapshot_dir / "src"

        if not snapshot_src.exists():
            logger.error("Snapshot not found: iter %d", iteration)
            return False

        game_src = self._game_dir / "src"

        # Backup current src
        if game_src.exists():
            backup = self._game_dir / "src_backup"
            if backup.exists():
                shutil.rmtree(backup)
            shutil.copytree(game_src, backup)
            shutil.rmtree(game_src)

        # Restore snapshot
        shutil.copytree(snapshot_src, game_src)

        logger.info("🔄 Restored snapshot: iter %d", iteration)
        return True

    def get_snapshot_metadata(self, iteration: int) -> dict[str, Any] | None:
        """Get metadata for a specific snapshot."""
        meta_path = self._iterations_dir / f"iter_{iteration:05d}" / "metadata.json"
        if not meta_path.exists():
            return None
        return json.loads(meta_path.read_text(encoding="utf-8"))

    def list_snapshots(self) -> list[dict[str, Any]]:
        """List all available snapshots with metadata."""
        snapshots: list[dict[str, Any]] = []

        for d in sorted(self._iterations_dir.iterdir()):
            if d.is_dir() and d.name.startswith("iter_"):
                meta = self.get_snapshot_metadata(int(d.name.split("_")[1]))
                if meta:
                    snapshots.append(meta)

        return snapshots

    def get_best_snapshot(self) -> dict[str, Any] | None:
        """Get the snapshot with the highest score."""
        snapshots = self.list_snapshots()
        if not snapshots:
            return None
        return max(snapshots, key=lambda s: s.get("score", 0))

    def cleanup_old_snapshots(self, keep_count: int = 50, max_disk_mb: float = 500.0) -> int:
        """Remove old snapshots, keeping the N most recent + milestones. Enforce disk cap."""
        snapshots = self.list_snapshots()
        if len(snapshots) <= keep_count:
            # Even under count, check disk cap
            total_bytes = sum(
                sum(f.stat().st_size for f in (self._iterations_dir / f"iter_{s['iteration']:05d}").rglob("*") if f.is_file())
                for s in snapshots
                if (self._iterations_dir / f"iter_{s['iteration']:05d}").exists()
            )
            if total_bytes <= max_disk_mb * 1024 * 1024:
                return 0

        # Sort by iteration number
        snapshots.sort(key=lambda s: s.get("iteration", 0))

        # Keep last N + any high-score ones
        to_keep = set()
        for s in snapshots[-keep_count:]:
            to_keep.add(s["iteration"])

        # Also keep top 10 scoring snapshots (milestones)
        by_score = sorted(snapshots, key=lambda s: s.get("score", 0), reverse=True)
        for s in by_score[:10]:
            to_keep.add(s["iteration"])

        # Delete the rest, starting from oldest
        removed = 0
        for s in snapshots:
            if s["iteration"] not in to_keep:
                dir_path = self._iterations_dir / f"iter_{s['iteration']:05d}"
                if dir_path.exists():
                    shutil.rmtree(dir_path)
                    removed += 1

        logger.info("Cleaned up %d old snapshots", removed)
        return removed
