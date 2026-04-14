"""
GORVAX GAME FACTORY — Database
SQLite persistence layer for iterations, metrics, and agent data.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiosqlite

from backend.config import STORAGE_DIR

logger = logging.getLogger(__name__)

DB_PATH = STORAGE_DIR / "factory.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS iterations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    iteration_number INTEGER NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'pending',
    score INTEGER DEFAULT 0,
    gdd_snapshot TEXT,
    code_changes TEXT,
    test_report TEXT,
    critic_feedback TEXT,
    metrics TEXT,
    error TEXT,
    started_at TEXT,
    completed_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS agent_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    iteration_number INTEGER NOT NULL,
    agent_name TEXT NOT NULL,
    action TEXT NOT NULL,
    input_summary TEXT,
    output_summary TEXT,
    tokens_used INTEGER DEFAULT 0,
    latency_ms REAL DEFAULT 0,
    provider TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS game_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    iteration_number INTEGER NOT NULL,
    version_tag TEXT,
    score INTEGER DEFAULT 0,
    is_milestone INTEGER DEFAULT 0,
    snapshot_path TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_iterations_number ON iterations(iteration_number);
CREATE INDEX IF NOT EXISTS idx_agent_logs_iteration ON agent_logs(iteration_number);
CREATE INDEX IF NOT EXISTS idx_game_versions_score ON game_versions(score DESC);
"""


class Database:
    """Async SQLite database for persistent storage."""

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path or DB_PATH
        self._db: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        """Initialize the database connection and create schema."""
        self._db = await aiosqlite.connect(str(self._db_path))
        self._db.row_factory = aiosqlite.Row
        # BE-13: Enable WAL mode for better concurrent read performance
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.execute("PRAGMA busy_timeout=5000")
        await self._db.executescript(SCHEMA)
        await self._db.commit()
        # Migration: add error column if it doesn't exist yet
        try:
            await self._db.execute("ALTER TABLE iterations ADD COLUMN error TEXT")
            await self._db.commit()
        except Exception:
            pass  # Column already exists
        logger.info("Database connected (persistent, WAL mode): %s", self._db_path)

    async def close(self) -> None:
        """Close the database connection."""
        if self._db:
            await self._db.close()
            self._db = None

    async def reset_all_data(self) -> None:
        """Delete all rows from every table. Used when resetting a project."""
        db = await self._ensure_connected()
        await db.execute("DELETE FROM game_versions")
        await db.execute("DELETE FROM agent_logs")
        await db.execute("DELETE FROM iterations")
        await db.commit()
        logger.info("All project data cleared from database")

    async def _ensure_connected(self) -> aiosqlite.Connection:
        if self._db is None:
            await self.connect()
        assert self._db is not None
        return self._db

    # ── Iterations ─────────────────────────────────────

    async def create_iteration(self, iteration_number: int) -> int:
        """Create a new iteration record. Returns the row ID."""
        db = await self._ensure_connected()
        now = datetime.now(timezone.utc).isoformat()
        cursor = await db.execute(
            "INSERT INTO iterations (iteration_number, status, started_at) VALUES (?, 'running', ?)",
            (iteration_number, now),
        )
        await db.commit()
        return cursor.lastrowid or 0

    async def update_iteration(
        self,
        iteration_number: int,
        *,
        status: str | None = None,
        score: int | None = None,
        gdd_snapshot: str | None = None,
        code_changes: str | None = None,
        test_report: str | None = None,
        critic_feedback: str | None = None,
        metrics: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        """Update an iteration record with new data."""
        db = await self._ensure_connected()
        updates: list[str] = []
        values: list[Any] = []

        if status is not None:
            updates.append("status = ?")
            values.append(status)
            if status in ("completed", "failed"):
                updates.append("completed_at = ?")
                values.append(datetime.now(timezone.utc).isoformat())
        if error is not None:
            updates.append("error = ?")
            values.append(error)
        if score is not None:
            updates.append("score = ?")
            values.append(score)
        if gdd_snapshot is not None:
            updates.append("gdd_snapshot = ?")
            values.append(gdd_snapshot)
        if code_changes is not None:
            updates.append("code_changes = ?")
            values.append(code_changes)
        if test_report is not None:
            updates.append("test_report = ?")
            values.append(test_report)
        if critic_feedback is not None:
            updates.append("critic_feedback = ?")
            values.append(critic_feedback)
        if metrics is not None:
            updates.append("metrics = ?")
            values.append(json.dumps(metrics))

        if updates:
            values.append(iteration_number)
            query = f"UPDATE iterations SET {', '.join(updates)} WHERE iteration_number = ?"
            await db.execute(query, values)
            await db.commit()

    async def get_iteration(self, iteration_number: int) -> dict[str, Any] | None:
        """Get a single iteration by number."""
        db = await self._ensure_connected()
        cursor = await db.execute(
            "SELECT * FROM iterations WHERE iteration_number = ?",
            (iteration_number,),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def get_recent_iterations(
        self, limit: int = 20, after_cursor: int | None = None,
    ) -> dict[str, Any]:
        """Get the most recent iterations with cursor-based pagination (#16)."""
        db = await self._ensure_connected()
        query = "SELECT * FROM iterations"
        params: list[Any] = []
        if after_cursor is not None:
            query += " WHERE iteration_number < ?"
            params.append(after_cursor)
        query += " ORDER BY iteration_number DESC LIMIT ?"
        params.append(limit + 1)  # fetch one extra to detect has_more
        cursor = await db.execute(query, params)
        rows = await cursor.fetchall()
        items = [dict(r) for r in rows]
        has_more = len(items) > limit
        if has_more:
            items = items[:limit]
        next_cursor = items[-1]["iteration_number"] if has_more and items else None
        return {"items": items, "next_cursor": next_cursor, "has_more": has_more}

    async def get_latest_iteration_number(self) -> int:
        """Get the highest iteration number, or 0 if none."""
        db = await self._ensure_connected()
        cursor = await db.execute(
            "SELECT MAX(iteration_number) as max_num FROM iterations"
        )
        row = await cursor.fetchone()
        return (row["max_num"] or 0) if row else 0

    # ── Agent Logs ─────────────────────────────────────

    async def log_agent_action(
        self,
        iteration_number: int,
        agent_name: str,
        action: str,
        input_summary: str = "",
        output_summary: str = "",
        tokens_used: int = 0,
        latency_ms: float = 0.0,
        provider: str = "",
    ) -> None:
        """Log an agent action for activity feed."""
        db = await self._ensure_connected()
        await db.execute(
            """INSERT INTO agent_logs
               (iteration_number, agent_name, action, input_summary,
                output_summary, tokens_used, latency_ms, provider)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (iteration_number, agent_name, action, input_summary,
             output_summary, tokens_used, latency_ms, provider),
        )
        await db.commit()

    async def get_recent_logs(
        self, limit: int = 50, after_cursor: int | None = None,
    ) -> dict[str, Any]:
        """Get recent agent logs with cursor-based pagination (#16)."""
        db = await self._ensure_connected()
        query = "SELECT * FROM agent_logs"
        params: list[Any] = []
        if after_cursor is not None:
            query += " WHERE id < ?"
            params.append(after_cursor)
        query += " ORDER BY id DESC LIMIT ?"
        params.append(limit + 1)
        cursor = await db.execute(query, params)
        rows = await cursor.fetchall()
        items = [dict(r) for r in rows]
        has_more = len(items) > limit
        if has_more:
            items = items[:limit]
        next_cursor = items[-1]["id"] if has_more and items else None
        return {"items": items, "next_cursor": next_cursor, "has_more": has_more}

    # ── Game Versions ──────────────────────────────────

    async def save_game_version(
        self,
        iteration_number: int,
        score: int,
        snapshot_path: str,
        is_milestone: bool = False,
        version_tag: str = "",
    ) -> None:
        """Save a game version record."""
        db = await self._ensure_connected()
        await db.execute(
            """INSERT INTO game_versions
               (iteration_number, score, snapshot_path, is_milestone, version_tag)
               VALUES (?, ?, ?, ?, ?)""",
            (iteration_number, score, snapshot_path, int(is_milestone), version_tag),
        )
        await db.commit()

    async def get_milestones(self, limit: int = 20) -> list[dict[str, Any]]:
        """Get milestone versions (high-score snapshots)."""
        db = await self._ensure_connected()
        cursor = await db.execute(
            """SELECT * FROM game_versions
               WHERE is_milestone = 1
               ORDER BY iteration_number DESC LIMIT ?""",
            (limit,),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def get_best_version(self) -> dict[str, Any] | None:
        """Get the highest-scoring game version."""
        db = await self._ensure_connected()
        cursor = await db.execute(
            "SELECT * FROM game_versions ORDER BY score DESC LIMIT 1"
        )
        row = await cursor.fetchone()
        return dict(row) if row else None
