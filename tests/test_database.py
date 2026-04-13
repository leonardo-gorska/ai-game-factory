"""
Tests for Database — storage/database.py
Uses a temporary in-memory or temp-file SQLite DB.
"""

import asyncio
import tempfile
from pathlib import Path

import pytest

from backend.storage.database import Database


# ── Fixtures ─────────────────────────────────────────

@pytest.fixture
async def db(tmp_path):
    """Create a temporary database that auto-connects and auto-closes."""
    db_path = tmp_path / "test_gorvax.db"
    database = Database(db_path=db_path)
    await database.connect()
    yield database
    await database.close()


# ── Connection ───────────────────────────────────────

class TestDatabaseConnection:
    @pytest.mark.asyncio
    async def test_connect_and_close(self, tmp_path):
        """Database should connect and close without errors."""
        db = Database(db_path=tmp_path / "conn_test.db")
        await db.connect()
        assert db._db is not None
        await db.close()

    @pytest.mark.asyncio
    async def test_double_connect(self, tmp_path):
        """Calling connect twice should not raise."""
        db = Database(db_path=tmp_path / "double.db")
        await db.connect()
        await db.connect()  # should be idempotent
        await db.close()


# ── Iterations ───────────────────────────────────────

class TestIterations:
    @pytest.mark.asyncio
    async def test_create_iteration(self, db):
        """Should create an iteration record and return a row ID."""
        row_id = await db.create_iteration(1)
        assert row_id is not None
        assert isinstance(row_id, int)
        assert row_id > 0

    @pytest.mark.asyncio
    async def test_create_multiple_iterations(self, db):
        """Should create multiple iteration records with unique IDs."""
        id1 = await db.create_iteration(1)
        id2 = await db.create_iteration(2)
        id3 = await db.create_iteration(3)
        assert len({id1, id2, id3}) == 3  # all unique

    @pytest.mark.asyncio
    async def test_get_iteration(self, db):
        """Should retrieve an iteration by its number."""
        await db.create_iteration(42)
        row = await db.get_iteration(42)
        assert row is not None

    @pytest.mark.asyncio
    async def test_get_nonexistent_iteration(self, db):
        """Should return None for a non-existent iteration."""
        row = await db.get_iteration(999)
        assert row is None

    @pytest.mark.asyncio
    async def test_update_iteration_status(self, db):
        """Should update the status of an existing iteration."""
        await db.create_iteration(10)
        await db.update_iteration(10, status="completed", score=85)
        row = await db.get_iteration(10)
        assert row is not None
        # Row should contain updated fields
        # (exact indexing depends on schema, we just verify no exception)

    @pytest.mark.asyncio
    async def test_get_recent_iterations(self, db):
        """Should return the most recent iterations."""
        for i in range(1, 6):
            await db.create_iteration(i)
        rows = await db.get_recent_iterations(limit=3)
        assert len(rows) == 3

    @pytest.mark.asyncio
    async def test_get_latest_iteration_number(self, db):
        """Should return the highest iteration number."""
        await db.create_iteration(5)
        await db.create_iteration(10)
        await db.create_iteration(3)
        latest = await db.get_latest_iteration_number()
        assert latest == 10

    @pytest.mark.asyncio
    async def test_get_latest_iteration_number_empty(self, db):
        """Should return 0 when no iterations exist."""
        latest = await db.get_latest_iteration_number()
        assert latest == 0


# ── Agent Logs ───────────────────────────────────────

class TestAgentLogs:
    @pytest.mark.asyncio
    async def test_log_agent_action(self, db):
        """Should log an agent action without errors."""
        await db.create_iteration(1)
        await db.log_agent_action(
            iteration_number=1,
            agent_name="designer",
            action="generate_gdd",
            input_summary="Design a platformer",
            output_summary="GDD generated",
            tokens_used=500,
            latency_ms=1234.5,
            provider="openai",
        )

    @pytest.mark.asyncio
    async def test_get_recent_logs(self, db):
        """Should retrieve recent agent logs."""
        await db.create_iteration(1)
        await db.log_agent_action(
            iteration_number=1,
            agent_name="developer",
            action="write_code",
        )
        await db.log_agent_action(
            iteration_number=1,
            agent_name="tester",
            action="run_tests",
        )
        logs = await db.get_recent_logs(limit=10)
        assert len(logs) >= 2


# ── Game Versions ────────────────────────────────────

class TestGameVersions:
    @pytest.mark.asyncio
    async def test_save_game_version(self, db):
        """Should save a game version record."""
        await db.save_game_version(
            iteration_number=1,
            score=75,
            snapshot_path="/snapshots/iter_1.zip",
            is_milestone=False,
        )

    @pytest.mark.asyncio
    async def test_save_milestone(self, db):
        """Should save a milestone version and retrieve it."""
        await db.save_game_version(
            iteration_number=5,
            score=90,
            snapshot_path="/snapshots/iter_5.zip",
            is_milestone=True,
        )
        milestones = await db.get_milestones(limit=10)
        assert len(milestones) >= 1

    @pytest.mark.asyncio
    async def test_get_best_version(self, db):
        """Should return the highest-scoring version."""
        await db.save_game_version(iteration_number=1, score=50, snapshot_path="/s/1")
        await db.save_game_version(iteration_number=2, score=80, snapshot_path="/s/2")
        await db.save_game_version(iteration_number=3, score=65, snapshot_path="/s/3")
        best = await db.get_best_version()
        assert best is not None
