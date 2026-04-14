"""
GORVAX GAME FACTORY — Multi-Pipeline Manager (v3 Roadmap Item 17)

Manages multiple game pipelines simultaneously with shared resources.
Each game gets its own isolated Pipeline instance, while the
MultiPipeline coordinates concurrency, resource allocation, and
cross-pollination of insights between games.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from backend.config import AppConfig, ProjectConfig, get_config
from backend.core.resource_scheduler import ResourceScheduler

logger = logging.getLogger(__name__)

EventCallback = Callable[[dict[str, Any]], Awaitable[None]]


@dataclass
class GameSlot:
    """A slot for a game in the multi-pipeline manager."""
    game_id: str
    project_config: ProjectConfig
    pipeline: Any = None  # Pipeline (lazy import to avoid circular)
    status: str = "idle"  # idle | running | paused | stopped | error
    priority: int = 5     # 0 = highest, 10 = lowest
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    error: str | None = None
    max_iterations: int = 100
    _task: asyncio.Task | None = field(default=None, repr=False)

    def to_dict(self) -> dict[str, Any]:
        """Serialize slot for API response."""
        pipeline_state = None
        if self.pipeline:
            try:
                pipeline_state = self.pipeline.state.to_dict()
            except Exception:
                pipeline_state = None

        return {
            "game_id": self.game_id,
            "game_name": self.project_config.game_name,
            "project": self.project_config.to_dict(),
            "status": self.status,
            "priority": self.priority,
            "created_at": self.created_at,
            "error": self.error,
            "max_iterations": self.max_iterations,
            "pipeline_state": pipeline_state,
        }


class MultiPipeline:
    """Manages N game pipelines simultaneously.

    Usage::

        mp = MultiPipeline(max_concurrent=3)
        mp.add_game("rpg1", ProjectConfig(game_name="My RPG"), priority=1)
        mp.add_game("puzzle1", ProjectConfig(game_name="Puzzle Fun"), priority=5)
        await mp.start_game("rpg1", max_iterations=50)
        summary = mp.get_summary()
    """

    def __init__(
        self,
        max_concurrent: int = 3,
        total_budget_usd: float = 10.0,
        config: AppConfig | None = None,
    ) -> None:
        self._config = config or get_config()
        self._max_concurrent = max(1, max_concurrent)
        self._games: dict[str, GameSlot] = {}
        self._resource_scheduler = ResourceScheduler(total_budget_usd=total_budget_usd)
        self._event_callbacks: list[EventCallback] = []

    # ── Properties ────────────────────────────────────────

    @property
    def max_concurrent(self) -> int:
        return self._max_concurrent

    @property
    def resource_scheduler(self) -> ResourceScheduler:
        return self._resource_scheduler

    @property
    def running_count(self) -> int:
        """Number of currently running pipelines."""
        return sum(1 for g in self._games.values() if g.status == "running")

    @property
    def game_ids(self) -> list[str]:
        return list(self._games.keys())

    # ── Event system ──────────────────────────────────────

    def on_event(self, callback: EventCallback) -> None:
        """Register event callback for real-time updates."""
        self._event_callbacks.append(callback)

    async def _emit(self, event_type: str, data: dict[str, Any]) -> None:
        event = {"type": event_type, "data": data}
        for cb in self._event_callbacks:
            try:
                await cb(event)
            except Exception as exc:
                logger.warning("MultiPipeline event callback error: %s", exc)

    # ── CRUD ──────────────────────────────────────────────

    def add_game(
        self,
        game_id: str | None = None,
        project_config: ProjectConfig | None = None,
        priority: int = 5,
        max_iterations: int = 100,
    ) -> GameSlot:
        """Add a new game to the multi-pipeline manager.

        Args:
            game_id: Unique identifier. Auto-generated if None.
            project_config: Game project configuration.
            priority: Scheduling priority (0=highest, 10=lowest).
            max_iterations: Default max iterations for this game.

        Returns:
            The created GameSlot.

        Raises:
            ValueError: If game_id already exists.
        """
        if game_id is None:
            game_id = str(uuid.uuid4())[:8]

        if game_id in self._games:
            raise ValueError(f"Game '{game_id}' already exists")

        if project_config is None:
            project_config = ProjectConfig()

        slot = GameSlot(
            game_id=game_id,
            project_config=project_config,
            priority=max(0, min(10, priority)),
            max_iterations=max_iterations,
        )
        self._games[game_id] = slot
        self._resource_scheduler.register(game_id, priority=slot.priority)

        logger.info(
            "MultiPipeline: added game '%s' (%s) priority=%d",
            game_id, project_config.game_name, slot.priority,
        )
        return slot

    def remove_game(self, game_id: str) -> bool:
        """Remove a game. Stops its pipeline if running.

        Returns:
            True if removed, False if not found.
        """
        slot = self._games.get(game_id)
        if not slot:
            return False

        # Cancel running task
        if slot._task and not slot._task.done():
            slot._task.cancel()

        self._resource_scheduler.unregister(game_id)
        del self._games[game_id]

        logger.info("MultiPipeline: removed game '%s'", game_id)
        return True

    def get_game(self, game_id: str) -> GameSlot | None:
        """Get a game slot by ID."""
        return self._games.get(game_id)

    def list_games(self) -> list[GameSlot]:
        """List all registered games."""
        return list(self._games.values())

    # ── Lifecycle ─────────────────────────────────────────

    def _can_start(self) -> bool:
        """Check if another pipeline can be started."""
        return self.running_count < self._max_concurrent

    def _create_pipeline(self, slot: GameSlot) -> Any:
        """Create a Pipeline instance for the given game slot."""
        from backend.orchestrator.pipeline import Pipeline

        # Build an AppConfig tailored to this game
        game_config = AppConfig(
            llm=self._config.llm,
            pipeline=self._config.pipeline,
            server=self._config.server,
            project=slot.project_config,
        )
        pipeline = Pipeline(config=game_config)

        # Share event callbacks
        for cb in self._event_callbacks:
            pipeline.on_event(cb)

        return pipeline

    async def start_game(
        self,
        game_id: str,
        max_iterations: int | None = None,
    ) -> dict[str, str]:
        """Start the pipeline for a game.

        Returns:
            Status dict with result.

        Raises:
            ValueError: If game not found.
        """
        slot = self._games.get(game_id)
        if not slot:
            raise ValueError(f"Game '{game_id}' not found")

        if slot.status == "running":
            return {"status": "already_running", "game_id": game_id}

        if not self._can_start():
            return {
                "status": "max_concurrent_reached",
                "game_id": game_id,
                "max_concurrent": str(self._max_concurrent),
                "running": str(self.running_count),
            }

        max_iter = max_iterations or slot.max_iterations

        # Create pipeline if needed
        if slot.pipeline is None:
            slot.pipeline = self._create_pipeline(slot)

        slot.status = "running"
        slot.error = None

        async def _run_pipeline():
            try:
                await slot.pipeline.start(max_iterations=max_iter)
            except asyncio.CancelledError:
                logger.info("Pipeline for game '%s' was cancelled", game_id)
            except Exception as exc:
                logger.error("Pipeline for game '%s' failed: %s", game_id, exc)
                slot.error = str(exc)
                slot.status = "error"
            finally:
                if slot.status == "running":
                    slot.status = "stopped"
                await self._emit("game_pipeline_stopped", {"game_id": game_id})

        slot._task = asyncio.create_task(_run_pipeline())

        await self._emit("game_pipeline_started", {
            "game_id": game_id,
            "game_name": slot.project_config.game_name,
            "max_iterations": max_iter,
        })

        logger.info(
            "MultiPipeline: started game '%s' (%s) max_iter=%d",
            game_id, slot.project_config.game_name, max_iter,
        )
        return {"status": "started", "game_id": game_id}

    async def stop_game(self, game_id: str) -> dict[str, str]:
        """Stop the pipeline for a game."""
        slot = self._games.get(game_id)
        if not slot:
            raise ValueError(f"Game '{game_id}' not found")

        if slot.pipeline and slot.status == "running":
            await slot.pipeline.stop()
            slot.status = "stopped"
            return {"status": "stopping", "game_id": game_id}

        return {"status": "not_running", "game_id": game_id}

    async def pause_game(self, game_id: str) -> dict[str, str]:
        """Pause the pipeline for a game."""
        slot = self._games.get(game_id)
        if not slot:
            raise ValueError(f"Game '{game_id}' not found")

        if slot.pipeline and slot.status == "running":
            await slot.pipeline.pause()
            slot.status = "paused"
            return {"status": "paused", "game_id": game_id}

        return {"status": "not_running", "game_id": game_id}

    async def resume_game(self, game_id: str) -> dict[str, str]:
        """Resume the pipeline for a game."""
        slot = self._games.get(game_id)
        if not slot:
            raise ValueError(f"Game '{game_id}' not found")

        if slot.pipeline and slot.status == "paused":
            await slot.pipeline.resume()
            slot.status = "running"
            return {"status": "resumed", "game_id": game_id}

        return {"status": "not_paused", "game_id": game_id}

    async def stop_all(self) -> dict[str, Any]:
        """Stop all running pipelines."""
        results: dict[str, str] = {}
        for game_id, slot in self._games.items():
            if slot.status in ("running", "paused"):
                try:
                    result = await self.stop_game(game_id)
                    results[game_id] = result["status"]
                except Exception as exc:
                    results[game_id] = f"error: {exc}"
        return {"stopped": results}

    # ── Cross-pollination ─────────────────────────────────

    def get_cross_insights(self, game_id: str) -> dict[str, Any]:
        """Get insights from other running games for cross-pollination.

        Returns quality scores, best practices, and learnings from
        sibling pipelines that could benefit the target game.
        """
        slot = self._games.get(game_id)
        if not slot:
            return {"error": "game not found"}

        insights: list[dict[str, Any]] = []
        for gid, other_slot in self._games.items():
            if gid == game_id or other_slot.pipeline is None:
                continue

            try:
                other_state = other_slot.pipeline.state
                insight = {
                    "game_id": gid,
                    "game_name": other_slot.project_config.game_name,
                    "genre": other_slot.project_config.genre,
                    "engine": other_slot.project_config.engine,
                    "best_score": other_state.best_score,
                    "total_iterations": other_state.total_iterations,
                    "score_trend": other_state.get_score_trend(),
                }

                # Quality data if available
                try:
                    quality_trend = other_slot.pipeline.quality_engine.get_trend()
                    insight["quality_trend"] = quality_trend
                except Exception:
                    pass

                insights.append(insight)
            except Exception as exc:
                logger.debug("Could not get insights from '%s': %s", gid, exc)

        return {
            "target_game": game_id,
            "sibling_count": len(insights),
            "insights": insights,
        }

    # ── Dashboard ─────────────────────────────────────────

    def get_summary(self) -> dict[str, Any]:
        """Get unified dashboard summary of all games."""
        games_list = []
        total_cost = 0.0

        for slot in self._games.values():
            game_data = slot.to_dict()

            # Add cost data if pipeline exists
            if slot.pipeline:
                try:
                    cost_stats = slot.pipeline.cost_guard.get_stats()
                    game_data["cost_usd"] = cost_stats.get("total_cost_usd", 0.0)
                    total_cost += game_data["cost_usd"]
                except Exception:
                    game_data["cost_usd"] = 0.0
            else:
                game_data["cost_usd"] = 0.0

            games_list.append(game_data)

        status_counts = {}
        for slot in self._games.values():
            status_counts[slot.status] = status_counts.get(slot.status, 0) + 1

        return {
            "total_games": len(self._games),
            "max_concurrent": self._max_concurrent,
            "running_count": self.running_count,
            "status_counts": status_counts,
            "total_cost_usd": round(total_cost, 6),
            "resource_allocation": self._resource_scheduler.get_stats(),
            "games": games_list,
        }
