"""
GORVAX GAME FACTORY — Rate Limiting Middleware
Sliding window rate limiter for FastAPI endpoints.
No external dependencies (in-memory).
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Any

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RateLimitConfig:
    """Rate limiting configuration."""
    # Read endpoints (GET)
    read_limit: int = 120          # requests per window
    read_window: float = 60.0      # window in seconds

    # Write endpoints (POST/PUT/DELETE)
    write_limit: int = 20          # requests per window
    write_window: float = 60.0     # window in seconds

    # Global limit (all endpoints combined)
    global_limit: int = 300
    global_window: float = 60.0

    # Cleanup interval for stale entries
    cleanup_interval: float = 120.0

    # Exempt paths (no rate limiting)
    exempt_paths: tuple[str, ...] = ("/ws", "/docs", "/openapi.json", "/redoc")


class SlidingWindowCounter:
    """
    Sliding window counter for rate limiting.
    Tracks request timestamps per client and prunes expired ones.
    """

    def __init__(self) -> None:
        self._windows: dict[str, deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()

    async def is_allowed(self, key: str, limit: int, window: float) -> tuple[bool, dict[str, Any]]:
        """
        Check if a request is allowed under the rate limit.
        Returns (allowed, info_dict) where info_dict has remaining, reset_at, etc.
        """
        now = time.monotonic()
        cutoff = now - window

        async with self._lock:
            timestamps = self._windows[key]

            # Prune expired timestamps
            while timestamps and timestamps[0] < cutoff:
                timestamps.popleft()

            current_count = len(timestamps)
            allowed = current_count < limit

            if allowed:
                timestamps.append(now)

            remaining = max(0, limit - current_count - (1 if allowed else 0))
            reset_at = timestamps[0] + window if timestamps else now + window

            return allowed, {
                "limit": limit,
                "remaining": remaining,
                "reset": round(reset_at - now, 1),
                "current": current_count + (1 if allowed else 0),
            }

    async def cleanup(self) -> int:
        """Remove stale entries. Returns number of keys cleaned."""
        now = time.monotonic()
        cleaned = 0
        async with self._lock:
            stale_keys = [
                key for key, ts in self._windows.items()
                if not ts or ts[-1] < now - 300  # 5 min stale
            ]
            for key in stale_keys:
                del self._windows[key]
                cleaned += 1
        return cleaned


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    FastAPI middleware for rate limiting.
    Uses sliding window counters per client IP.
    """

    _instance: RateLimitMiddleware | None = None  # Class-level reference for stats

    def __init__(self, app: Any, config: RateLimitConfig | None = None) -> None:
        super().__init__(app)
        self.config = config or RateLimitConfig()
        self._counter = SlidingWindowCounter()
        self._cleanup_task: asyncio.Task[None] | None = None
        self._total_blocked = 0
        self._total_allowed = 0
        RateLimitMiddleware._instance = self  # Auto-register

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # Start cleanup on first request
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())

        path = request.url.path

        # Exempt WebSocket and docs
        if any(path.startswith(p) for p in self.config.exempt_paths):
            return await call_next(request)

        # Get client identifier
        client_ip = self._get_client_ip(request)

        # Determine limits based on method
        is_write = request.method in ("POST", "PUT", "DELETE", "PATCH")
        limit = self.config.write_limit if is_write else self.config.read_limit
        window = self.config.write_window if is_write else self.config.read_window
        bucket = f"{client_ip}:{'write' if is_write else 'read'}"

        # Check endpoint-specific limit
        allowed, info = await self._counter.is_allowed(bucket, limit, window)

        if not allowed:
            self._total_blocked += 1
            logger.warning(
                "Rate limit exceeded: %s %s from %s (%d/%d)",
                request.method, path, client_ip, info["current"], info["limit"]
            )
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Too Many Requests",
                    "detail": f"Rate limit exceeded. Try again in {info['reset']}s",
                    "retry_after": info["reset"],
                },
                headers={
                    "Retry-After": str(int(info["reset"])),
                    "X-RateLimit-Limit": str(info["limit"]),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(int(info["reset"])),
                },
            )

        # Check global limit
        global_allowed, global_info = await self._counter.is_allowed(
            f"{client_ip}:global",
            self.config.global_limit,
            self.config.global_window,
        )

        if not global_allowed:
            self._total_blocked += 1
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Too Many Requests",
                    "detail": f"Global rate limit exceeded. Try again in {global_info['reset']}s",
                },
                headers={"Retry-After": str(int(global_info["reset"]))},
            )

        self._total_allowed += 1

        # Execute request and add rate limit headers
        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(info["limit"])
        response.headers["X-RateLimit-Remaining"] = str(info["remaining"])
        response.headers["X-RateLimit-Reset"] = str(int(info["reset"]))
        return response

    def get_stats(self) -> dict[str, Any]:
        """Return rate limiter statistics."""
        total = self._total_allowed + self._total_blocked
        return {
            "total_requests": total,
            "allowed": self._total_allowed,
            "blocked": self._total_blocked,
            "block_rate": round(
                self._total_blocked / total * 100, 2
            ) if total > 0 else 0.0,
            "config": {
                "read_limit": f"{self.config.read_limit}/{self.config.read_window}s",
                "write_limit": f"{self.config.write_limit}/{self.config.write_window}s",
                "global_limit": f"{self.config.global_limit}/{self.config.global_window}s",
            },
        }

    @staticmethod
    def _get_client_ip(request: Request) -> str:
        """Extract client IP from request, handling proxies."""
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    async def _cleanup_loop(self) -> None:
        """Periodically clean up stale rate limit entries."""
        while True:
            await asyncio.sleep(self.config.cleanup_interval)
            cleaned = await self._counter.cleanup()
            if cleaned:
                logger.debug("Rate limiter cleanup: removed %d stale entries", cleaned)
