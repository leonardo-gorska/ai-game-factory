"""
GORVAX GAME FACTORY — WebSocket Handlers
Real-time event streaming to the dashboard.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

from backend.api.auth import validate_ws_token

import time as _time

import asyncio

logger = logging.getLogger(__name__)

# WebSocket rate limiting
_WS_RATE_LIMIT_WINDOW = 60.0  # seconds
_WS_RATE_LIMIT_MAX = 30        # max messages per window

# Heartbeat (#15)
_HEARTBEAT_INTERVAL = 30  # seconds


class ConnectionManager:
    """Manages active WebSocket connections for real-time updates."""

    def __init__(self) -> None:
        self._connections: list[WebSocket] = []

    async def connect(self, ws: WebSocket) -> None:
        """Accept and register a new WebSocket connection."""
        await ws.accept()
        self._connections.append(ws)
        logger.info("WebSocket connected (total: %d)", len(self._connections))

    def disconnect(self, ws: WebSocket) -> None:
        """Remove a WebSocket connection."""
        if ws in self._connections:
            self._connections.remove(ws)
        logger.info("WebSocket disconnected (total: %d)", len(self._connections))

    async def broadcast(self, event: dict[str, Any]) -> None:
        """Send an event to all connected clients."""
        if not self._connections:
            return

        message = json.dumps(event, default=str)
        disconnected: list[WebSocket] = []

        for ws in self._connections:
            try:
                await ws.send_text(message)
            except Exception:
                disconnected.append(ws)

        for ws in disconnected:
            self.disconnect(ws)

    @property
    def connection_count(self) -> int:
        return len(self._connections)


# Singleton manager
ws_manager = ConnectionManager()


async def pipeline_event_handler(event: dict[str, Any]) -> None:
    """
    Callback function registered with the Pipeline.
    Forwards all pipeline events to WebSocket clients.
    """
    await ws_manager.broadcast(event)


async def _heartbeat(ws: WebSocket) -> None:
    """Send periodic ping frames to keep the connection alive (#15)."""
    try:
        while True:
            await asyncio.sleep(_HEARTBEAT_INTERVAL)
            await ws.send_text(json.dumps({
                "type": "ping",
                "ts": _time.time(),
            }))
    except Exception:
        pass  # connection closed or cancelled — exit silently


async def websocket_endpoint(ws: WebSocket) -> None:
    """
    WebSocket endpoint handler.
    Validates token query parameter before accepting the connection.
    Keeps the connection alive and handles incoming messages.
    Sends periodic pings to detect dead connections (#15).
    """
    # Validate authentication token from query string
    if not await validate_ws_token(ws):
        await ws.accept()
        await ws.close(code=4001, reason="Unauthorized: invalid or missing token")
        logger.warning("WebSocket connection rejected: invalid token")
        return

    await ws_manager.connect(ws)

    # Per-connection rate limit tracking
    msg_timestamps: list[float] = []

    # Start heartbeat task (#15)
    heartbeat_task = asyncio.create_task(_heartbeat(ws))

    try:
        while True:
            # Listen for messages from the client (commands)
            data = await ws.receive_text()

            # Rate limit check
            now = _time.monotonic()
            msg_timestamps = [t for t in msg_timestamps if now - t < _WS_RATE_LIMIT_WINDOW]
            if len(msg_timestamps) >= _WS_RATE_LIMIT_MAX:
                await ws.close(code=4003, reason="Rate limit exceeded")
                logger.warning("WebSocket rate limit exceeded, disconnecting client")
                break
            msg_timestamps.append(now)

            message = json.loads(data)

            # Ignore pong responses from clients (#15)
            if message.get("type") == "pong":
                continue

            # Handle client commands
            command = message.get("command")
            if command:
                await ws_manager.broadcast({
                    "type": "command_received",
                    "data": {"command": command},
                })

    except WebSocketDisconnect:
        ws_manager.disconnect(ws)
    except Exception as exc:
        logger.warning("WebSocket error: %s", exc)
        ws_manager.disconnect(ws)
    finally:
        heartbeat_task.cancel()

