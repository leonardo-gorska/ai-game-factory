"""
GORVAX GAME FACTORY — WebSocket Event Schema (INT-02)

Shared contract for WebSocket events between backend (Python) and
frontend (TypeScript). The TypeScript equivalent lives in
dashboard/src/lib/wsSchema.ts.

All events broadcast via ws_manager.broadcast() MUST conform to
the WSEvent structure below.
"""

from __future__ import annotations

from typing import Any, TypedDict


class WSEventData(TypedDict, total=False):
    """Payload carried inside a WebSocket event."""
    agent: str
    step: str
    iteration: int
    score: float
    message: str
    error: str
    command: str
    # Additional fields may be added; consumers should tolerate extras.


class WSEvent(TypedDict):
    """
    Top-level WebSocket event envelope.

    Every message sent over the WS connection MUST include:
      - type: discriminator string (e.g. "step_start", "iteration_complete")
      - data: structured payload (see WSEventData)
      - timestamp: ISO-8601 string (added server-side)

    Optional:
      - agent: shortcut for data.agent when present at top level
    """
    type: str
    data: WSEventData
    timestamp: str
    agent: str  # optional shortcut; may be empty string


# ─── Known event types ───────────────────────────────────────────
# These are the event types currently emitted by the pipeline.
# Keeping them as constants avoids typos and enables IDE auto-complete.

EVENT_STEP_START = "step_start"
EVENT_STEP_END = "step_end"
EVENT_ITERATION_COMPLETE = "iteration_complete"
EVENT_PIPELINE_STARTED = "pipeline_started"
EVENT_PIPELINE_STOPPED = "pipeline_stopped"
EVENT_PIPELINE_PAUSED = "pipeline_paused"
EVENT_PIPELINE_RESUMED = "pipeline_resumed"
EVENT_ERROR = "error"
EVENT_COMMAND_RECEIVED = "command_received"
