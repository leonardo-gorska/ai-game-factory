"""
GORVAX GAME FACTORY — Agent Result Cache

In-memory cache for LLM agent results, keyed by agent name + input hash.
Avoids redundant LLM calls when inputs haven't changed across iterations.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class CachedResult:
    """A single cached agent result with TTL."""
    input_hash: str
    result: Any
    iteration_created: int
    ttl_iterations: int = 3


class AgentCache:
    """
    In-memory agent result cache with iteration-based TTL.

    Usage:
        cache = AgentCache()
        hit = cache.get("researcher", input_hash, current_iter)
        if hit is not None:
            return hit  # skip LLM call
        result = await agent.run(...)
        cache.put("researcher", input_hash, result, current_iter)
    """

    def __init__(self, default_ttl: int = 3) -> None:
        self._cache: dict[str, CachedResult] = {}
        self._default_ttl = default_ttl
        self._hits = 0
        self._misses = 0

    # ── Public API ────────────────────────────────────

    def get(
        self,
        agent_name: str,
        input_hash: str,
        current_iteration: int,
    ) -> Any | None:
        """Return cached result if still valid, else None."""
        key = f"{agent_name}:{input_hash}"
        entry = self._cache.get(key)

        if entry is None:
            self._misses += 1
            return None

        age = current_iteration - entry.iteration_created
        if age > entry.ttl_iterations:
            # Expired — evict
            del self._cache[key]
            self._misses += 1
            logger.debug(
                "Cache EXPIRED for %s (age=%d, ttl=%d)",
                agent_name, age, entry.ttl_iterations,
            )
            return None

        self._hits += 1
        logger.info(
            "⚡ Cache HIT for %s (age=%d/%d iterations)",
            agent_name, age, entry.ttl_iterations,
        )
        return entry.result

    def put(
        self,
        agent_name: str,
        input_hash: str,
        result: Any,
        iteration: int,
        ttl: int | None = None,
    ) -> None:
        """Store an agent result in the cache."""
        key = f"{agent_name}:{input_hash}"
        self._cache[key] = CachedResult(
            input_hash=input_hash,
            result=result,
            iteration_created=iteration,
            ttl_iterations=ttl if ttl is not None else self._default_ttl,
        )
        logger.debug("Cache PUT for %s (ttl=%d)", agent_name, ttl or self._default_ttl)

    def clear(self) -> None:
        """Flush all cached entries."""
        count = len(self._cache)
        self._cache.clear()
        if count:
            logger.info("Cache cleared (%d entries flushed)", count)

    def evict_expired(self, current_iteration: int) -> int:
        """Remove all expired entries. Returns count of evicted items."""
        expired_keys = [
            k for k, v in self._cache.items()
            if (current_iteration - v.iteration_created) > v.ttl_iterations
        ]
        for k in expired_keys:
            del self._cache[k]
        return len(expired_keys)

    # ── Stats ─────────────────────────────────────────

    @property
    def stats(self) -> dict[str, int]:
        """Return cache hit/miss statistics."""
        return {
            "hits": self._hits,
            "misses": self._misses,
            "entries": len(self._cache),
            "hit_rate_pct": round(
                self._hits / max(self._hits + self._misses, 1) * 100
            ),
        }

    # ── Hashing Helper ────────────────────────────────

    @staticmethod
    def hash_input(data: dict[str, Any]) -> str:
        """Compute a stable hash for agent input data.

        Serializes the dict to sorted JSON and returns an MD5 hex digest.
        Non-serializable values are converted to their string representation.
        """
        try:
            serialized = json.dumps(data, sort_keys=True, default=str)
        except (TypeError, ValueError):
            serialized = str(data)
        return hashlib.md5(serialized.encode()).hexdigest()
