"""
GORVAX GAME FACTORY — Pipeline State
Manages the global state of the AI pipeline including
current iteration, GDD, scores, and agent outputs.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class IterationState:
    """State for a single iteration."""
    number: int
    status: str = "pending"  # pending, running, completed, failed
    gdd_update: dict[str, Any] = field(default_factory=dict)
    code_changes: dict[str, Any] = field(default_factory=dict)
    test_report: dict[str, Any] = field(default_factory=dict)
    critic_feedback: dict[str, Any] = field(default_factory=dict)
    score: int = 0
    build_success: bool = False
    build_output: str = ""
    started_at: str = ""
    completed_at: str = ""
    errors: list[str] = field(default_factory=list)


class PipelineState:
    """
    Global state manager for the AI pipeline.
    Tracks the current iteration, history, and game state.
    """

    def __init__(self) -> None:
        self.current_iteration: int = 0
        self.current_state: IterationState | None = None
        self.history: list[IterationState] = []
        self.current_gdd: dict[str, Any] = {}
        self.best_score: int = 0
        self.best_iteration: int = 0
        self.total_iterations: int = 0
        self.is_running: bool = False
        self.is_paused: bool = False
        self.started_at: str = ""

    def start_iteration(self) -> IterationState:
        """Start a new iteration."""
        self.current_iteration += 1
        self.total_iterations += 1

        state = IterationState(
            number=self.current_iteration,
            status="running",
            started_at=datetime.now(timezone.utc).isoformat(),
        )
        self.current_state = state

        if not self.started_at:
            self.started_at = datetime.now(timezone.utc).isoformat()

        logger.info("=== Starting Iteration #%d ===", self.current_iteration)
        return state

    def complete_iteration(self, state: IterationState) -> None:
        """Mark an iteration as completed."""
        state.status = "completed"
        state.completed_at = datetime.now(timezone.utc).isoformat()

        # Update best score
        if state.score > self.best_score:
            self.best_score = state.score
            self.best_iteration = state.number
            logger.info(
                "🏆 New best score: %d (iteration #%d)",
                self.best_score,
                self.best_iteration,
            )

        # Add to history (keep last 100)
        self.history.append(state)
        if len(self.history) > 100:
            self.history = self.history[-100:]

    def fail_iteration(self, state: IterationState, error: str) -> None:
        """Mark an iteration as failed."""
        state.status = "failed"
        state.errors.append(error)
        state.completed_at = datetime.now(timezone.utc).isoformat()
        self.history.append(state)

    def get_recent_history(self, count: int = 5) -> list[dict[str, Any]]:
        """Get recent iteration summaries for context."""
        return [
            {
                "iteration_number": s.number,
                "status": s.status,
                "score": s.score,
                "build_success": s.build_success,
            }
            for s in self.history[-count:]
        ]

    def get_score_trend(self) -> str:
        """Analyze the score trend over recent iterations."""
        if len(self.history) < 3:
            return "insufficient_data"

        recent_scores = [s.score for s in self.history[-5:] if s.score > 0]
        if len(recent_scores) < 2:
            return "insufficient_data"

        avg_recent = sum(recent_scores[-3:]) / len(recent_scores[-3:])
        avg_older = sum(recent_scores[:-3]) / max(len(recent_scores[:-3]), 1)

        if avg_recent > avg_older + 5:
            return "improving"
        elif avg_recent < avg_older - 5:
            return "declining"
        return "stable"

    def to_dict(self) -> dict[str, Any]:
        """Serialize the full state for dashboard."""
        return {
            "current_iteration": self.current_iteration,
            "is_running": self.is_running,
            "is_paused": self.is_paused,
            "best_score": self.best_score,
            "best_iteration": self.best_iteration,
            "total_iterations": self.total_iterations,
            "started_at": self.started_at,
            "score_trend": self.get_score_trend(),
            "recent_scores": [
                {"iteration": s.number, "score": s.score}
                for s in self.history[-20:]
            ],
            "current_agent": (
                self.current_state.status if self.current_state else "idle"
            ),
        }
