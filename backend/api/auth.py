"""
GORVAX GAME FACTORY — API Key Authentication Middleware
Validates X-API-Key header on all REST endpoints.
Auto-generates a key on first run if GORVAX_API_KEY is not set.
"""

from __future__ import annotations

import hashlib
import logging
import os
import secrets
from pathlib import Path
from typing import Any

from fastapi import Request, Response, WebSocket
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

logger = logging.getLogger(__name__)

# Paths exempt from API key validation (WS has its own auth)
# Single source of truth — imported by server.py too
EXEMPT_PATHS = ("/docs", "/openapi.json", "/redoc", "/ws", "/game")

# Env file location (project root)
_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


def _hash_key(key: str) -> str:
    """A4: SHA-256 hash for constant-time comparison."""
    return hashlib.sha256(key.encode()).hexdigest()


def _load_or_generate_api_key() -> str:
    """
    Return the GORVAX_API_KEY from environment or .env file.
    If not set, generate one, persist it to .env, and return it.
    A4: Returns SHA-256 hash — plaintext is never held in memory.
    """
    # First try os.environ (set by dotenv or OS)
    key = os.environ.get("GORVAX_API_KEY", "").strip()

    # Fallback: read .env directly (auth.py may be imported before dotenv.load_dotenv)
    if not key and _ENV_FILE.exists():
        for line in _ENV_FILE.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith("GORVAX_API_KEY="):
                val = stripped.split("=", 1)[1].strip()
                if val:
                    key = val
        if key:
            os.environ["GORVAX_API_KEY"] = key

    if key:
        return _hash_key(key)

    # Auto-generate a 32-char hex key
    key = secrets.token_hex(16)
    os.environ["GORVAX_API_KEY"] = key

    # Append to .env file so it persists across restarts
    try:
        with open(_ENV_FILE, "a", encoding="utf-8") as f:
            f.write(f"\n# --- Authentication ---\nGORVAX_API_KEY={key}\n")
        logger.info("Generated new GORVAX_API_KEY and saved to .env")
        logger.warning(
            "⚠️  SEC-02: API key saved in PLAINTEXT to %s. "
            "For production, set GORVAX_API_KEY as an OS-level "
            "environment variable instead.",
            _ENV_FILE,
        )
    except OSError as exc:
        logger.warning("Could not write API key to .env: %s", exc)

    # A4: Display once, then store only the hash
    logger.info("🔑 Your new API key (shown ONLY ONCE): %s", key)
    return _hash_key(key)


# Module-level singleton — resolved once at import (stores HASH)
API_KEY_HASH: str = _load_or_generate_api_key()


def validate_api_key(provided: str | None) -> bool:
    """A4: Check if the hash of the provided key matches the stored hash."""
    if not API_KEY_HASH:
        return True  # No key configured = open access (dev fallback)
    if not provided:
        return False
    return secrets.compare_digest(_hash_key(provided), API_KEY_HASH)


class APIKeyMiddleware(BaseHTTPMiddleware):
    """
    Starlette middleware that enforces X-API-Key header
    on all HTTP requests except exempt paths.
    """

    def __init__(self, app: Any) -> None:
        super().__init__(app)

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        path = request.url.path

        # Skip auth for exempt paths
        if any(path.startswith(p) for p in EXEMPT_PATHS):
            return await call_next(request)

        # Validate X-API-Key header
        provided_key = request.headers.get("x-api-key")
        if not validate_api_key(provided_key):
            logger.warning(
                "Unauthorized request: %s %s from %s",
                request.method,
                path,
                request.client.host if request.client else "unknown",
            )
            return JSONResponse(
                status_code=401,
                content={
                    "error": "Unauthorized",
                    "detail": "Missing or invalid X-API-Key header",
                },
            )

        return await call_next(request)


async def validate_ws_token(ws: WebSocket) -> bool:
    """
    Validate token query parameter for WebSocket connections.
    Returns True if valid, False otherwise.
    """
    token = ws.query_params.get("token")
    return validate_api_key(token)
