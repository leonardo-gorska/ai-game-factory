"""
GORVAX GAME FACTORY — Async TTL Cache
In-memory cache with TTL-based expiration for API endpoint responses.
No external dependencies (no Redis required).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from functools import wraps
from typing import Any, Callable

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    """Single cache entry with TTL."""
    value: Any
    expires_at: float
    created_at: float = field(default_factory=time.monotonic)

    @property
    def is_expired(self) -> bool:
        return time.monotonic() > self.expires_at


class AsyncCache:
    """
    In-memory async TTL cache with LRU eviction.
    
    Features:
    - TTL-based expiration per key
    - LRU eviction when max_size is reached
    - Automatic cleanup of expired entries
    - Thread-safe via asyncio locks
    - Cache invalidation by prefix
    """

    def __init__(self, max_size: int = 500, cleanup_interval: float = 60.0):
        self._store: OrderedDict[str, CacheEntry] = OrderedDict()
        self._max_size = max_size
        self._lock = asyncio.Lock()
        self._cleanup_task: asyncio.Task[None] | None = None
        self._cleanup_interval = cleanup_interval
        self._hits = 0
        self._misses = 0

    async def start(self) -> None:
        """Start the background cleanup task."""
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())
            logger.info("🗄️  Cache started (max_size=%d)", self._max_size)

    async def stop(self) -> None:
        """Stop the background cleanup task."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None

    async def get(self, key: str) -> Any | None:
        """Get a value from cache. Returns None if expired or missing."""
        async with self._lock:
            entry = self._store.get(key)
            if entry is None:
                self._misses += 1
                return None
            if entry.is_expired:
                del self._store[key]
                self._misses += 1
                return None
            # Move to end (LRU)
            self._store.move_to_end(key)
            self._hits += 1
            return entry.value

    async def set(self, key: str, value: Any, ttl: float) -> None:
        """Set a value in cache with TTL (seconds)."""
        async with self._lock:
            if key in self._store:
                del self._store[key]
            elif len(self._store) >= self._max_size:
                # Evict oldest (LRU)
                self._store.popitem(last=False)
            self._store[key] = CacheEntry(
                value=value,
                expires_at=time.monotonic() + ttl,
            )

    async def invalidate(self, key: str) -> bool:
        """Remove a specific key from cache."""
        async with self._lock:
            if key in self._store:
                del self._store[key]
                return True
            return False

    async def invalidate_prefix(self, prefix: str) -> int:
        """Remove all keys matching a prefix. Returns count removed."""
        async with self._lock:
            to_remove = [k for k in self._store if k.startswith(prefix)]
            for k in to_remove:
                del self._store[k]
            if to_remove:
                logger.debug("Cache invalidated %d keys with prefix '%s'", len(to_remove), prefix)
            return len(to_remove)

    async def clear(self) -> None:
        """Clear all cache entries."""
        async with self._lock:
            self._store.clear()
            logger.info("Cache cleared")

    def get_stats(self) -> dict[str, Any]:
        """Return cache statistics."""
        total = self._hits + self._misses
        return {
            "size": len(self._store),
            "max_size": self._max_size,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": round(self._hits / total * 100, 1) if total > 0 else 0.0,
            "total_requests": total,
        }

    async def _cleanup_loop(self) -> None:
        """Periodically remove expired entries."""
        while True:
            await asyncio.sleep(self._cleanup_interval)
            async with self._lock:
                now = time.monotonic()
                expired = [k for k, v in self._store.items() if now > v.expires_at]
                for k in expired:
                    del self._store[k]
                if expired:
                    logger.debug("Cache cleanup: removed %d expired entries", len(expired))


# ── Singleton ──────────────────────────────────────────

_cache: AsyncCache | None = None


def get_cache() -> AsyncCache:
    """Get or create the global cache singleton."""
    global _cache
    if _cache is None:
        _cache = AsyncCache()
    return _cache


# ── Decorator ──────────────────────────────────────────

def cache_response(ttl: float = 10.0, prefix: str = ""):
    """
    Decorator for FastAPI endpoint functions.
    Caches the JSON response for `ttl` seconds.
    
    Usage:
        @app.get("/api/quality")
        @cache_response(ttl=10.0)
        async def get_quality():
            ...
    """
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            cache = get_cache()
            # Build cache key from function name + args
            key_parts = [prefix or func.__name__]
            if kwargs:
                key_parts.append(
                    hashlib.blake2b(
                        json.dumps(kwargs, sort_keys=True, default=str).encode(),
                        digest_size=6,
                    ).hexdigest()
                )
            cache_key = ":".join(key_parts)

            # Check cache
            cached = await cache.get(cache_key)
            if cached is not None:
                return cached

            # Execute and cache
            result = await func(*args, **kwargs)
            await cache.set(cache_key, result, ttl)
            return result

        return wrapper
    return decorator
