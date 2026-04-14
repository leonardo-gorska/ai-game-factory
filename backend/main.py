"""
GORVAX GAME FACTORY — Main Entry Point
Starts the FastAPI server and (optionally) the AI pipeline.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

import uvicorn

from backend.api.server import create_app, get_pipeline
from backend.api.ws import ws_manager
from backend.config import get_config
from backend.storage.session_logger import get_session_logger, BufferHandler


def setup_logging(level: str = "INFO") -> None:
    """Configure structured logging."""
    # M9: force=True ensures no duplicate handlers even if called after
    # other modules have already configured root logging.
    # Use a StreamHandler with explicit UTF-8 to avoid Windows cp1252 crashes
    handler = logging.StreamHandler(
        open(sys.stdout.fileno(), mode="w", encoding="utf-8", closefd=False)
    )
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s | %(levelname)-8s | %(name)-30s | %(message)s",
            datefmt="%H:%M:%S",
        )
    )
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        handlers=[handler],
        force=True,
    )
    # Reduce noise from libraries
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("litellm").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="GORVAX GAME FACTORY — Autonomous AI Game Development"
    )
    parser.add_argument(
        "--auto-start",
        action="store_true",
        help="Automatically start the AI pipeline on launch",
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=None,
        help="Maximum number of iterations to run",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Server port (default: from .env or 8000)",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default=None,
        help="Log level (DEBUG, INFO, WARNING, ERROR)",
    )

    args = parser.parse_args()
    config = get_config()

    log_level = args.log_level or config.server.log_level
    setup_logging(log_level)

    logger = logging.getLogger("main")

    port = args.port or config.server.backend_port

    logger.info("=" * 60)
    logger.info("🏭 GORVAX GAME FACTORY")
    logger.info("=" * 60)
    logger.info("Server: http://localhost:%d", port)
    logger.info("API Docs: http://localhost:%d/docs", port)
    logger.info("WebSocket: ws://localhost:%d/ws", port)
    logger.info("Providers: %s", config.llm.available_providers())
    logger.info("=" * 60)

    if not config.llm.available_providers():
        logger.warning(
            "⚠️  No LLM providers configured! "
            "Copy .env.example to .env and add your API keys."
        )

    app = create_app()

    # Register session logger: captures all log output into ring buffer + WS
    sess_logger = get_session_logger()
    buf_handler = BufferHandler(sess_logger)
    buf_handler.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    logging.getLogger().addHandler(buf_handler)
    # Wire WS broadcast for real-time log streaming
    sess_logger.on_log(ws_manager.broadcast)

    # Auto-start pipeline if requested
    if args.auto_start:
        # PIP-01: pass auto-start config via app.state for lifespan handler
        max_iter = args.max_iterations or config.pipeline.max_iterations
        app.state.auto_start_max_iterations = max_iter
        logger.info("Auto-start enabled (max %d iterations)", max_iter)

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        log_level=log_level.lower(),
    )


if __name__ == "__main__":
    main()
