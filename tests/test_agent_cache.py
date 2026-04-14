"""Tests for backend.core.agent_cache — Agent Result Caching."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.core.agent_cache import AgentCache, CachedResult


class TestAgentCache:
    """Unit tests for the AgentCache class."""

    def test_cache_miss_returns_none(self) -> None:
        cache = AgentCache()
        assert cache.get("researcher", "abc123", 1) is None

    def test_put_then_get_returns_result(self) -> None:
        cache = AgentCache()
        fake_result = SimpleNamespace(metadata={"research_report": {}})
        cache.put("researcher", "hash1", fake_result, iteration=1)

        hit = cache.get("researcher", "hash1", 1)
        assert hit is fake_result

    def test_get_same_iteration_is_hit(self) -> None:
        cache = AgentCache(default_ttl=3)
        cache.put("designer", "h1", {"gdd": True}, iteration=5)
        assert cache.get("designer", "h1", 5) == {"gdd": True}

    def test_get_within_ttl_is_hit(self) -> None:
        cache = AgentCache(default_ttl=3)
        cache.put("researcher", "h1", "result-A", iteration=1)
        assert cache.get("researcher", "h1", 2) == "result-A"
        assert cache.get("researcher", "h1", 4) == "result-A"  # age=3, still valid

    def test_get_past_ttl_is_miss(self) -> None:
        cache = AgentCache(default_ttl=3)
        cache.put("researcher", "h1", "result-A", iteration=1)
        assert cache.get("researcher", "h1", 5) is None  # age=4, expired

    def test_different_agent_different_key(self) -> None:
        cache = AgentCache()
        cache.put("researcher", "h1", "res-A", iteration=1)
        cache.put("designer", "h1", "des-A", iteration=1)
        assert cache.get("researcher", "h1", 1) == "res-A"
        assert cache.get("designer", "h1", 1) == "des-A"

    def test_different_hash_different_key(self) -> None:
        cache = AgentCache()
        cache.put("researcher", "hash1", "result-1", iteration=1)
        cache.put("researcher", "hash2", "result-2", iteration=1)
        assert cache.get("researcher", "hash1", 1) == "result-1"
        assert cache.get("researcher", "hash2", 1) == "result-2"

    def test_custom_ttl_per_entry(self) -> None:
        cache = AgentCache(default_ttl=3)
        cache.put("researcher", "h1", "short", iteration=1, ttl=1)
        assert cache.get("researcher", "h1", 2) == "short"  # age=1, valid
        assert cache.get("researcher", "h1", 3) is None     # age=2, expired (ttl=1)

    def test_clear_flushes_all(self) -> None:
        cache = AgentCache()
        cache.put("researcher", "h1", "A", iteration=1)
        cache.put("designer", "h2", "B", iteration=1)
        cache.clear()
        assert cache.get("researcher", "h1", 1) is None
        assert cache.get("designer", "h2", 1) is None

    def test_evict_expired(self) -> None:
        cache = AgentCache(default_ttl=2)
        cache.put("researcher", "h1", "old", iteration=1)
        cache.put("designer", "h2", "new", iteration=5)
        evicted = cache.evict_expired(current_iteration=6)
        assert evicted == 1  # researcher expired, designer still valid
        assert cache.get("researcher", "h1", 6) is None
        assert cache.get("designer", "h2", 6) == "new"

    def test_stats_tracking(self) -> None:
        cache = AgentCache()
        cache.put("researcher", "h1", "A", iteration=1)
        cache.get("researcher", "h1", 1)  # hit
        cache.get("researcher", "h1", 1)  # hit
        cache.get("researcher", "missing", 1)  # miss

        stats = cache.stats
        assert stats["hits"] == 2
        assert stats["misses"] == 1
        assert stats["entries"] == 1
        assert stats["hit_rate_pct"] == 67

    def test_hash_input_deterministic(self) -> None:
        data = {"current_gdd": {"name": "Test"}, "exploration_mode": False}
        h1 = AgentCache.hash_input(data)
        h2 = AgentCache.hash_input(data)
        assert h1 == h2

    def test_hash_input_different_data(self) -> None:
        h1 = AgentCache.hash_input({"a": 1})
        h2 = AgentCache.hash_input({"a": 2})
        assert h1 != h2

    def test_hash_input_order_independent(self) -> None:
        h1 = AgentCache.hash_input({"a": 1, "b": 2})
        h2 = AgentCache.hash_input({"b": 2, "a": 1})
        assert h1 == h2
