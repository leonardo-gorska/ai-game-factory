"""Tests for backend.memory.knowledge_transfer"""

from unittest.mock import MagicMock, patch

from backend.memory.knowledge_transfer import (
    KnowledgeTransfer,
    QUALITY_THRESHOLD,
    TransferStats,
)


def _make_mock_db(is_available=True, query_results=None):
    """Create a mock ExperienceDB."""
    db = MagicMock()
    db.is_available = is_available
    db.store_decision = MagicMock(return_value="doc_id_123")
    db.query_decisions = MagicMock(return_value=query_results or [])
    return db


class TestKnowledgeTransferPromote:
    def test_promote_above_threshold(self):
        db = _make_mock_db()
        kt = KnowledgeTransfer(db)

        result = kt.promote(
            experience={"action": "add physics", "iteration": 5, "agent": "designer"},
            source_namespace="my_game",
            score_delta=5.0,
        )
        assert result is True
        assert kt.get_stats()["total_promoted"] == 1
        db.store_decision.assert_called_once()

    def test_promote_below_threshold_skipped(self):
        db = _make_mock_db()
        kt = KnowledgeTransfer(db)

        result = kt.promote(
            experience={"action": "tweak color", "iteration": 3},
            source_namespace="my_game",
            score_delta=0.1,
        )
        assert result is False
        assert kt.get_stats()["total_promoted"] == 0
        db.store_decision.assert_not_called()

    def test_promote_unavailable_db(self):
        db = _make_mock_db(is_available=False)
        kt = KnowledgeTransfer(db)

        result = kt.promote(
            experience={"action": "test", "iteration": 1},
            source_namespace="proj",
            score_delta=10.0,
        )
        assert result is False

    def test_promote_none_db(self):
        kt = KnowledgeTransfer(None)
        result = kt.promote(
            experience={"action": "test"},
            source_namespace="proj",
            score_delta=10.0,
        )
        assert result is False

    def test_promote_duplicate_skipped(self):
        db = _make_mock_db()
        kt = KnowledgeTransfer(db)
        exp = {"action": "add physics", "iteration": 5, "agent": "designer"}

        kt.promote(exp, "game_a", score_delta=5.0)
        result = kt.promote(exp, "game_a", score_delta=5.0)
        assert result is False
        assert kt.get_stats()["total_promoted"] == 1

    def test_promote_uses_experience_score_delta(self):
        db = _make_mock_db()
        kt = KnowledgeTransfer(db)

        result = kt.promote(
            experience={"action": "big win", "score_delta": 3.0, "iteration": 1},
            source_namespace="proj",
        )
        assert result is True

    def test_promote_adds_metadata(self):
        db = _make_mock_db()
        kt = KnowledgeTransfer(db)

        kt.promote(
            experience={"action": "physics", "iteration": 1, "agent": "dev"},
            source_namespace="game_a",
            score_delta=5.0,
            genre="platformer",
        )

        call_kwargs = db.store_decision.call_args
        extra = call_kwargs.kwargs.get("extra_metadata") or call_kwargs[1].get("extra_metadata", {})
        assert extra.get("source_namespace") == "game_a"
        assert extra.get("genre") == "platformer"


class TestKnowledgeTransferQuery:
    def test_query_global_hit(self):
        results = [{"action": "add particles", "score_delta": 5.0}]
        db = _make_mock_db(query_results=results)
        kt = KnowledgeTransfer(db)

        got = kt.query_global("visual effects system")
        assert len(got) == 1
        assert kt.get_stats()["global_hits"] == 1

    def test_query_global_miss(self):
        db = _make_mock_db(query_results=[])
        kt = KnowledgeTransfer(db)

        got = kt.query_global("something completely new")
        assert got == []
        assert kt.get_stats()["global_misses"] == 1

    def test_query_unavailable_returns_empty(self):
        db = _make_mock_db(is_available=False)
        kt = KnowledgeTransfer(db)

        got = kt.query_global("anything")
        assert got == []
        assert kt.get_stats()["global_misses"] == 1

    def test_query_with_genre_filter(self):
        results = [
            {"action": "add AI", "genre": "platformer"},
            {"action": "add cars", "genre": "racing"},
        ]
        db = _make_mock_db(query_results=results)
        kt = KnowledgeTransfer(db)

        got = kt.query_global("enemy AI", genre_filter="platformer")
        assert len(got) == 1
        assert got[0]["genre"] == "platformer"


class TestKnowledgeTransferStats:
    def test_initial_stats(self):
        kt = KnowledgeTransfer(None)
        stats = kt.get_stats()
        assert stats["total_promoted"] == 0
        assert stats["total_queries"] == 0
        assert stats["hit_rate"] == 0.0

    def test_stats_accumulate(self):
        db = _make_mock_db(query_results=[{"action": "x"}])
        kt = KnowledgeTransfer(db)

        kt.promote({"action": "a", "iteration": 1}, "p1", score_delta=5.0)
        kt.query_global("test")

        stats = kt.get_stats()
        assert stats["total_promoted"] == 1
        assert stats["total_queries"] == 1
        assert stats["global_hits"] == 1

    def test_reset_stats(self):
        db = _make_mock_db()
        kt = KnowledgeTransfer(db)
        kt.promote({"action": "x", "iteration": 1}, "p", score_delta=5.0)
        kt.reset_stats()

        stats = kt.get_stats()
        assert stats["total_promoted"] == 0


class TestTransferStats:
    def test_to_dict(self):
        s = TransferStats(total_promoted=5, total_queries=10, global_hits=7, global_misses=3)
        d = s.to_dict()
        assert d["total_promoted"] == 5
        assert d["hit_rate"] == 0.7

    def test_hit_rate_zero_queries(self):
        s = TransferStats()
        assert s.to_dict()["hit_rate"] == 0.0


class TestExperienceDBNamespace:
    """Test namespace support added to ExperienceDB."""

    def test_default_namespace(self):
        from backend.memory.experience_db import ExperienceDB
        db = ExperienceDB()
        assert db.get_namespace() == "default"

    def test_custom_namespace(self):
        from backend.memory.experience_db import ExperienceDB
        db = ExperienceDB(namespace="my_project")
        assert db.get_namespace() == "my_project"

    def test_default_collection_names_unchanged(self):
        from backend.memory.experience_db import ExperienceDB
        db = ExperienceDB(namespace="default")
        assert db._collection("decisions") == "decisions"
        assert db._collection("failures") == "failures"

    def test_custom_namespace_prefixes_collections(self):
        from backend.memory.experience_db import ExperienceDB
        db = ExperienceDB(namespace="game_a")
        assert db._collection("decisions") == "game_a_decisions"
        assert db._collection("failures") == "game_a_failures"
