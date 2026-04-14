"""
GORVAX GAME FACTORY — Session Logger
Captures Python log output into:
  1. Ring buffer (for WS streaming + API)
  2. File: data/logs/current_session.log  (overwritten each start)
  3. Archived: data/logs/session_YYYY-MM-DD_HHhMM.log  (on stop)
"""

from __future__ import annotations

import logging
import os
import shutil
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Awaitable

from backend.config import ROOT_DIR

LOGS_DIR = ROOT_DIR / "data" / "logs"
CURRENT_LOG = LOGS_DIR / "current_session.log"
MAX_BUFFER = 2000  # keep last N lines in memory


@dataclass
class LogEntry:
    id: int
    timestamp: float
    level: str
    logger_name: str
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "level": self.level,
            "logger": self.logger_name,
            "message": self.message,
        }


class SessionLogger:
    """Central session-aware log manager."""

    def __init__(self) -> None:
        self._buffer: list[LogEntry] = []
        self._next_id = 1
        self._session_active = False
        self._session_start: datetime | None = None
        self._file_handler: logging.FileHandler | None = None
        self._ws_callbacks: list[Callable[[dict[str, Any]], Awaitable[None]]] = []

        # Ensure logs dir
        LOGS_DIR.mkdir(parents=True, exist_ok=True)

    # ── WS emission ──────────────────────────────────

    def on_log(self, callback: Callable[[dict[str, Any]], Awaitable[None]]) -> None:
        """Register an async callback for real-time log emission."""
        self._ws_callbacks.append(callback)

    # ── Session lifecycle ─────────────────────────────

    def start_session(self) -> None:
        """Begin a new log session — opens file, resets buffer."""
        self._session_active = True
        self._session_start = datetime.now(timezone.utc)
        self._buffer.clear()
        self._next_id = 1

        # (Re)create file handler
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        if self._file_handler:
            root = logging.getLogger()
            root.removeHandler(self._file_handler)
            self._file_handler.close()

        self._file_handler = logging.FileHandler(
            str(CURRENT_LOG), mode="w", encoding="utf-8",
        )
        self._file_handler.setFormatter(logging.Formatter(
            fmt="%(asctime)s | %(levelname)-8s | %(name)-30s | %(message)s",
            datefmt="%H:%M:%S",
        ))
        logging.getLogger().addHandler(self._file_handler)

    def end_session(self) -> None:
        """Archive current session log to a dated file."""
        self._session_active = False

        # Remove file handler
        if self._file_handler:
            root = logging.getLogger()
            root.removeHandler(self._file_handler)
            self._file_handler.close()
            self._file_handler = None

        # Archive: copy current_session.log → session_YYYY-MM-DD_HHhMM.log
        if CURRENT_LOG.exists() and CURRENT_LOG.stat().st_size > 0:
            ts = self._session_start or datetime.now(timezone.utc)
            local_ts = ts.astimezone()
            archive_name = f"session_{local_ts.strftime('%Y-%m-%d_%Hh%M')}.log"
            archive_path = LOGS_DIR / archive_name

            # Avoid overwriting if same minute
            counter = 1
            while archive_path.exists():
                archive_name = f"session_{local_ts.strftime('%Y-%m-%d_%Hh%M')}_{counter}.log"
                archive_path = LOGS_DIR / archive_name
                counter += 1

            shutil.copy2(str(CURRENT_LOG), str(archive_path))

    # ── Buffer API ────────────────────────────────────

    def add_entry(self, record: logging.LogRecord) -> LogEntry:
        """Add a log record to the ring buffer."""
        entry = LogEntry(
            id=self._next_id,
            timestamp=record.created,
            level=record.levelname,
            logger_name=record.name,
            message=record.getMessage(),
        )
        self._next_id += 1
        self._buffer.append(entry)

        # Trim buffer
        if len(self._buffer) > MAX_BUFFER:
            self._buffer = self._buffer[-MAX_BUFFER:]

        return entry

    def get_recent(self, limit: int = 200, after_id: int = 0) -> list[dict[str, Any]]:
        """Return recent log entries, optionally after a given ID."""
        if after_id > 0:
            entries = [e for e in self._buffer if e.id > after_id]
        else:
            entries = self._buffer[-limit:]
        return [e.to_dict() for e in entries[-limit:]]

    def list_sessions(self) -> list[dict[str, Any]]:
        """List archived session log files."""
        sessions = []
        if not LOGS_DIR.exists():
            return sessions
        for f in sorted(LOGS_DIR.glob("session_*.log"), reverse=True):
            stat = f.stat()
            sessions.append({
                "filename": f.name,
                "size_bytes": stat.st_size,
                "modified": stat.st_mtime,
            })
        return sessions

    def get_session_path(self, filename: str) -> Path | None:
        """Get full path for a session file (with safety check)."""
        # Prevent path traversal
        if "/" in filename or "\\" in filename or ".." in filename:
            return None
        path = LOGS_DIR / filename
        if path.exists() and path.suffix == ".log":
            return path
        return None


class BufferHandler(logging.Handler):
    """Custom logging handler that feeds the SessionLogger buffer
    and emits entries to WebSocket callbacks."""

    def __init__(self, session_logger: SessionLogger) -> None:
        super().__init__()
        self._session_logger = session_logger

    def emit(self, record: logging.LogRecord) -> None:
        try:
            entry = self._session_logger.add_entry(record)
            # Fire-and-forget WS emission
            for cb in self._session_logger._ws_callbacks:
                try:
                    import asyncio
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        loop.create_task(cb({
                            "type": "log_entry",
                            "data": entry.to_dict(),
                        }))
                except RuntimeError:
                    pass  # no event loop — skip WS emission
        except Exception:
            self.handleError(record)


# ── Singleton ─────────────────────────────────────

_instance: SessionLogger | None = None


def get_session_logger() -> SessionLogger:
    global _instance
    if _instance is None:
        _instance = SessionLogger()
    return _instance
