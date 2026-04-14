"""
GORVAX GAME FACTORY — API Server v5
FastAPI application with REST endpoints, WebSocket support,
caching, rate limiting, CI/CD pipeline, and endpoints for
quality, costs, health, experiments, and routing.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles

from backend.api.auth import APIKeyMiddleware
from backend.api.ws import websocket_endpoint, pipeline_event_handler, ws_manager
from backend.api.cache import get_cache, cache_response
from backend.api.rate_limiter import RateLimitMiddleware, RateLimitConfig
from backend.core.ci_pipeline import CIPipeline
from backend.orchestrator.pipeline import Pipeline
from backend.orchestrator.multi_pipeline import MultiPipeline
from backend.api.analytics import PipelineAnalytics
from backend.config import (
    get_config, ROOT_DIR, GAME_DIR, load_project_config, save_project_config,
    ProjectConfig, VALID_PLATFORMS, VALID_ENGINES, VALID_GENRES, VALID_MONETIZATIONS,
)

logger = logging.getLogger(__name__)

# Global singletons
_pipeline: Pipeline | None = None
_ci_pipeline: CIPipeline | None = None
_multi_pipeline: MultiPipeline | None = None


def get_pipeline() -> Pipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = Pipeline()
        _pipeline.on_event(pipeline_event_handler)
    return _pipeline


def get_ci_pipeline() -> CIPipeline:
    global _ci_pipeline
    if _ci_pipeline is None:
        _ci_pipeline = CIPipeline()
    return _ci_pipeline


def get_multi_pipeline() -> MultiPipeline:
    global _multi_pipeline
    if _multi_pipeline is None:
        _multi_pipeline = MultiPipeline(max_concurrent=3, total_budget_usd=10.0)
    return _multi_pipeline


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan: startup and shutdown."""
    logger.info("🏭 GORVAX GAME FACTORY v5 API starting up...")
    cache = get_cache()
    await cache.start()

    # PIP-01: auto-start pipeline if requested via app.state
    max_iter = getattr(app.state, "auto_start_max_iterations", None)
    if max_iter is not None:
        pipeline = get_pipeline()
        logger.info("Auto-starting pipeline (max %d iterations)...", max_iter)
        asyncio.create_task(pipeline.start(max_iterations=max_iter))

    yield
    pipeline = get_pipeline()
    if pipeline.state.is_running:
        await pipeline.stop()
    await cache.stop()
    logger.info("GORVAX GAME FACTORY API shut down.")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    config = get_config()

    app = FastAPI(
        title="GORVAX GAME FACTORY",
        description="Autonomous multi-agent AI game development system v5 — with caching, rate limiting, and CI/CD",
        version="5.0.0",
        lifespan=lifespan,
    )

    # API key authentication middleware
    app.add_middleware(APIKeyMiddleware)

    # Rate limiting middleware (single instance via add_middleware)
    rate_limit_config = RateLimitConfig()
    app.add_middleware(RateLimitMiddleware, config=rate_limit_config)

    # CORS for dashboard — restricted origins
    allowed_origins_str = os.getenv("ALLOWED_ORIGINS", "")
    if allowed_origins_str:
        allowed_origins = [o.strip() for o in allowed_origins_str.split(",")]
    else:
        allowed_origins = [
            "http://localhost:3000",
            "http://localhost:3001",
            f"http://localhost:{config.server.game_port}",
        ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── WebSocket ──────────────────────────────────────
    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket) -> None:
        await websocket_endpoint(ws)

    # ── Pipeline Control ───────────────────────────────

    @app.get("/api/v1/status")
    async def get_status() -> dict[str, Any]:
        """Get the current pipeline status with quality and cost data."""
        pipeline = get_pipeline()
        return {
            "status": "running" if pipeline.state.is_running else "stopped",
            "paused": pipeline.state.is_paused,
            "pipeline": pipeline.state.to_dict(),
            "providers": pipeline.llm_router.available_providers,
            "ws_clients": ws_manager.connection_count,
            "cost": pipeline.cost_guard.get_stats(),
            "quality_trend": pipeline.quality_engine.get_trend(),
            "health": pipeline.watchdog.get_health().to_dict(),
        }

    @app.post("/api/v1/start")
    async def start_pipeline(max_iterations: int = 100) -> dict[str, str]:
        pipeline = get_pipeline()
        if pipeline.state.is_running:
            return {"status": "already_running"}
        # Invalidate cache on pipeline state change
        await get_cache().invalidate_prefix("get_")
        asyncio.create_task(pipeline.start(max_iterations=max_iterations))
        return {"status": "started", "max_iterations": str(max_iterations)}

    @app.post("/api/v1/stop")
    async def stop_pipeline() -> dict[str, str]:
        pipeline = get_pipeline()
        await pipeline.stop()
        await get_cache().clear()
        return {"status": "stopping"}

    @app.post("/api/v1/pause")
    async def pause_pipeline() -> dict[str, str]:
        pipeline = get_pipeline()
        await pipeline.pause()
        return {"status": "paused"}

    @app.post("/api/v1/resume")
    async def resume_pipeline() -> dict[str, str]:
        pipeline = get_pipeline()
        await pipeline.resume()
        return {"status": "resumed"}

    # ── Chat History ───────────────────────────────────

    @app.get("/api/v1/chat/history")
    async def get_chat_history(
        limit: int = 100, after_id: int = 0,
    ) -> dict[str, Any]:
        """Get recent agent chat messages."""
        from backend.storage.chat_store import get_chat_store
        store = get_chat_store()
        messages = store.get_recent(limit=limit, after_id=after_id)
        return {"messages": messages, "count": len(messages)}

    # ── Terminal Logs ──────────────────────────────────

    @app.get("/api/v1/logs/stream")
    async def get_log_stream(
        limit: int = 200, after_id: int = 0,
    ) -> dict[str, Any]:
        """Get recent log entries from the ring buffer."""
        from backend.storage.session_logger import get_session_logger
        sl = get_session_logger()
        entries = sl.get_recent(limit=limit, after_id=after_id)
        return {"entries": entries, "count": len(entries)}

    @app.get("/api/v1/logs/sessions")
    async def get_log_sessions() -> dict[str, Any]:
        """List archived session log files."""
        from backend.storage.session_logger import get_session_logger
        sl = get_session_logger()
        sessions = sl.list_sessions()
        return {"sessions": sessions}

    @app.get("/api/v1/logs/sessions/{filename}")
    async def get_log_session_file(filename: str) -> Any:
        """Download a specific session log file."""
        from backend.storage.session_logger import get_session_logger
        from fastapi.responses import FileResponse
        sl = get_session_logger()
        path = sl.get_session_path(filename)
        if not path:
            return {"error": "Arquivo não encontrado"}
        return FileResponse(
            path=str(path),
            media_type="text/plain",
            filename=filename,
        )

    # ── Data Endpoints ─────────────────────────────────

    @app.get("/api/v1/iterations")
    async def get_iterations(
        limit: int = 20, cursor: int | None = None,
    ) -> dict[str, Any]:
        """#16: Cursor-based paginated iterations."""
        pipeline = get_pipeline()
        return await pipeline.database.get_recent_iterations(limit, after_cursor=cursor)

    @app.get("/api/v1/iterations/{iteration_number}")
    async def get_iteration(iteration_number: int) -> dict[str, Any]:
        pipeline = get_pipeline()
        result = await pipeline.database.get_iteration(iteration_number)
        return result or {"error": "not found"}

    @app.get("/api/v1/logs")
    async def get_logs(
        limit: int = 50, cursor: int | None = None,
    ) -> dict[str, Any]:
        """#16: Cursor-based paginated logs."""
        pipeline = get_pipeline()
        return await pipeline.database.get_recent_logs(limit, after_cursor=cursor)

    @app.get("/api/v1/versions")
    async def get_versions(offset: int = 0, limit: int = 50) -> list[dict[str, Any]]:
        """M8: Paginated version list."""
        pipeline = get_pipeline()
        all_versions = pipeline.versioner.list_snapshots()
        return all_versions[offset : offset + limit]

    @app.get("/api/v1/versions/best")
    async def get_best_version() -> dict[str, Any]:
        pipeline = get_pipeline()
        result = pipeline.versioner.get_best_snapshot()
        return result or {"error": "no versions yet"}

    @app.post("/api/v1/versions/{iteration_number}/restore")
    async def restore_version(iteration_number: int) -> dict[str, Any]:
        pipeline = get_pipeline()
        success = pipeline.versioner.restore_snapshot(iteration_number)
        return {"success": success, "iteration": iteration_number}

    # ── Quality & Cost ─────────────────────────────────

    @app.get("/api/v1/quality")
    @cache_response(ttl=10.0, prefix="get_quality")
    async def get_quality() -> dict[str, Any]:
        """Quality Engine data: history, trend, weights."""
        pipeline = get_pipeline()
        return {
            "history": pipeline.quality_engine.get_history(),
            "trend": pipeline.quality_engine.get_trend(),
            "weights": pipeline.quality_engine.get_weights(),
        }

    @app.get("/api/v1/costs")
    @cache_response(ttl=5.0, prefix="get_costs")
    async def get_costs() -> dict[str, Any]:
        """Cost Guard data: breakdown by agent, provider, iteration."""
        pipeline = get_pipeline()
        return pipeline.cost_guard.get_stats()

    @app.get("/api/v1/stats")
    async def get_stats() -> dict[str, Any]:
        """Get LLM provider usage stats."""
        pipeline = get_pipeline()
        stats = pipeline.llm_router.get_stats()
        return {
            provider: {
                "total_calls": s.total_calls,
                "total_errors": s.total_errors,
                "total_tokens": s.total_tokens,
                "total_cost_usd": s.total_cost_usd,
            }
            for provider, s in stats.items()
        }

    # ── Phase 3: Health, Experiments, Routing ──────────

    @app.get("/api/v1/health")
    @cache_response(ttl=15.0, prefix="get_health")
    async def get_health() -> dict[str, Any]:
        """Watchdog health status with active alerts."""
        pipeline = get_pipeline()
        return pipeline.watchdog.get_health().to_dict()

    @app.get("/api/v1/experiments")
    async def get_experiments(
        tag: str | None = None,
        min_score: float | None = None,
        max_score: float | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> dict[str, Any]:
        """M8: Experiment Tracker with pagination."""
        pipeline = get_pipeline()
        all_results = pipeline.experiment_tracker.get_history(
            tag=tag,
            min_score=min_score,
            max_score=max_score,
            limit=offset + limit,
        )
        return {
            "experiments": all_results[offset : offset + limit],
            "stats": pipeline.experiment_tracker.get_stats(),
        }

    @app.get("/api/v1/experiments/{iter_a}/compare/{iter_b}")
    async def compare_experiments(iter_a: int, iter_b: int) -> dict[str, Any]:
        """Compare two experiment iterations."""
        pipeline = get_pipeline()
        comparison = pipeline.experiment_tracker.compare(iter_a, iter_b)
        return comparison.to_dict()

    @app.get("/api/v1/experiments/export")
    async def export_experiments() -> PlainTextResponse:
        """Export all experiments as CSV."""
        pipeline = get_pipeline()
        csv_data = pipeline.experiment_tracker.export_csv()
        return PlainTextResponse(
            content=csv_data,
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=experiments.csv"},
        )

    @app.get("/api/v1/routing")
    async def get_routing() -> dict[str, Any]:
        """Smart Router configuration and provider scoring."""
        pipeline = get_pipeline()
        return {
            "routing": pipeline.llm_router.get_routing_info(),
            "provider_stats": {
                provider: {
                    "total_calls": s.total_calls,
                    "total_errors": s.total_errors,
                    "total_cost_usd": s.total_cost_usd,
                    "last_call_time": s.last_call_time,
                }
                for provider, s in pipeline.llm_router.get_stats().items()
            },
        }

    # ── Phase D: Stagnation, Heatmaps, Evolution ──────

    @app.get("/api/v1/stagnation")
    @cache_response(ttl=10.0, prefix="get_stagnation")
    async def get_stagnation() -> dict[str, Any]:
        """Stagnation guard state + exploration controller stats."""
        pipeline = get_pipeline()
        stag_data = pipeline.stagnation_guard.get_stats()
        exploration_data = pipeline.exploration_controller.get_stats()
        return {
            "stagnation": stag_data,
            "exploration": exploration_data,
        }

    @app.get("/api/v1/roadmap")
    @cache_response(ttl=5.0, prefix="get_roadmap")
    async def get_roadmap() -> dict[str, Any]:
        """Game development roadmap progress."""
        from backend.core.game_roadmap import PHASES
        pipeline = get_pipeline()
        progress = pipeline.roadmap.scan_progress()

        # Build enriched phases with completion status
        completed_set = set(progress["completed_tasks"])
        skipped_set = set(progress.get("skipped_tasks", []))
        phases = []
        for phase in PHASES:
            tasks = []
            for task in phase["tasks"]:
                tasks.append({
                    "id": task["id"],
                    "name": task["name"],
                    "description": task["description"][:200],
                    "completed": task["id"] in completed_set,
                    "skipped": task["id"] in skipped_set,
                    "files_expected": task.get("files_expected", []),
                    "integration_class": task.get("integration_class", ""),
                })
            phase_done = all(t["completed"] for t in tasks)
            phases.append({
                "id": phase["id"],
                "name": phase["name"],
                "description": phase["description"],
                "tasks": tasks,
                "completed": phase_done,
            })

        current_task = progress["current_task"]
        return {
            "phases": phases,
            "progress_pct": progress["progress_pct"],
            "completed_count": len(progress["completed_tasks"]),
            "total_count": progress["total_tasks"],
            "current_task_id": current_task["id"] if current_task else None,
            "current_task_name": current_task["name"] if current_task else None,
            "current_phase_name": progress["current_phase"]["name"] if progress["current_phase"] else None,
            "existing_files": progress["existing_files"],
            "skipped_tasks": sorted(skipped_set),
        }


    @app.get("/api/v1/heatmaps")
    async def get_heatmaps() -> dict[str, Any]:
        """Gameplay heatmap data from the most recent simulation."""
        pipeline = get_pipeline()
        # API-01: _last_heatmap is now declared in Pipeline.__init__
        return {
            "iteration": pipeline.state.current_iteration,
            "heatmap": pipeline._last_heatmap,
        }

    @app.get("/api/v1/evolution")
    @cache_response(ttl=10.0, prefix="get_evolution")
    async def get_evolution(limit: int = 50) -> dict[str, Any]:
        """Feature evolution timeline: quality + novelty + retention over time."""
        pipeline = get_pipeline()
        quality_hist = pipeline.quality_engine.get_history()
        novelty_stats = pipeline.novelty_engine.get_stats()
        trend = pipeline.quality_engine.get_trend()
        weights = pipeline.quality_engine.get_weights()

        # Build timeline entries from quality history
        timeline = []
        for i, entry in enumerate(quality_hist[-limit:]):
            timeline.append({
                "iteration": i + 1,
                "composite": round(entry.get("composite", 0), 1) if isinstance(entry, dict) else round(getattr(entry, "composite", 0), 1),
                "fun": round(entry.get("fun", 0), 1) if isinstance(entry, dict) else round(getattr(entry, "fun", 0), 1),
                "stability": round(entry.get("stability", 0), 1) if isinstance(entry, dict) else round(getattr(entry, "stability", 0), 1),
                "balance": round(entry.get("balance", 0), 1) if isinstance(entry, dict) else round(getattr(entry, "balance", 0), 1),
                "novelty": round(entry.get("novelty", 0), 1) if isinstance(entry, dict) else round(getattr(entry, "novelty", 0), 1),
                "retention": round(entry.get("retention", 0), 1) if isinstance(entry, dict) else round(getattr(entry, "retention", 0), 1),
                "confidence_lower": round(entry.get("confidence_lower", 0), 1) if isinstance(entry, dict) else round(getattr(entry, "confidence_lower", 0), 1),
                "confidence_upper": round(entry.get("confidence_upper", 0), 1) if isinstance(entry, dict) else round(getattr(entry, "confidence_upper", 0), 1),
            })

        return {
            "timeline": timeline,
            "trend": trend,
            "weights": weights,
            "novelty_stats": novelty_stats,
            "total_iterations": len(quality_hist),
        }

    # ── Phase E: Cache, Rate Limit, CI/CD ──────────────

    @app.get("/api/v1/cache")
    async def get_cache_stats() -> dict[str, Any]:
        """Cache statistics: hits, misses, hit rate."""
        return get_cache().get_stats()

    @app.post("/api/v1/cache/clear")
    async def clear_cache() -> dict[str, str]:
        """Clear all cached responses."""
        await get_cache().clear()
        return {"status": "cleared"}

    @app.get("/api/v1/rate-limit")
    async def get_rate_limit_stats() -> dict[str, Any]:
        """Rate limiter statistics."""
        instance = RateLimitMiddleware._instance
        if instance:
            return instance.get_stats()
        return {"status": "not configured"}

    @app.get("/api/v1/ci")
    async def get_ci_stats() -> dict[str, Any]:
        """CI/CD pipeline statistics and recent runs."""
        ci = get_ci_pipeline()
        return {
            "stats": ci.get_stats(),
            "recent_runs": ci.get_history(limit=10),
        }

    @app.get("/api/v1/ci/{run_id}")
    async def get_ci_run(run_id: int) -> dict[str, Any]:
        """Get details of a specific CI run."""
        ci = get_ci_pipeline()
        run = ci.get_run(run_id)
        return run.to_dict() if run else {"error": "not found"}

    # ── Phase 3: Project Configuration ──────────────────

    # CFG-01: Using canonical lists from config.py (single source of truth)

    @app.get("/api/v1/project")
    async def get_project() -> dict[str, Any]:
        """Retorna a configuração atual do projeto."""
        cfg = load_project_config()
        return {
            "game_name": cfg.game_name,
            "platform": cfg.platform,
            "engine": cfg.engine,
            "genre": cfg.genre,
            "monetization": cfg.monetization,
            "max_iterations": cfg.max_iterations,
            "options": {
                "platforms": VALID_PLATFORMS,
                "engines": VALID_ENGINES,
                "genres": VALID_GENRES,
                "monetizations": list(VALID_MONETIZATIONS),
            },
        }

    @app.post("/api/v1/project")
    async def update_project(body: dict[str, Any]) -> dict[str, Any]:
        """Save the project configuration and reinitialize the pipeline."""
        errors: list[str] = []

        game_name = body.get("game_name", "").strip()
        platform = body.get("platform", "")
        engine = body.get("engine", "")
        genre = body.get("genre", "")
        monetization = body.get("monetization", "hybrid")
        max_iterations = int(body.get("max_iterations", 100))

        if not game_name:
            errors.append("game_name is required")
        if platform not in VALID_PLATFORMS:
            errors.append(f"invalid platform: {platform}")
        if engine not in VALID_ENGINES:
            errors.append(f"invalid engine: {engine}")
        if genre not in VALID_GENRES:
            errors.append(f"invalid genre: {genre}")
        if monetization not in VALID_MONETIZATIONS:
            errors.append(f"invalid monetization: {monetization}")
        if max_iterations < 1 or max_iterations > 10000:
            errors.append("max_iterations must be between 1 and 10000")

        if errors:
            return {"success": False, "errors": errors}

        new_cfg = ProjectConfig(
            game_name=game_name,
            platform=platform,
            engine=engine,
            genre=genre,
            monetization=monetization,
            max_iterations=max_iterations,
        )
        save_project_config(new_cfg)

        # Reinitialize the global pipeline to use the new prompts
        global _pipeline
        _pipeline = None

        return {"success": True, "project": {
            "game_name": new_cfg.game_name,
            "platform": new_cfg.platform,
            "engine": new_cfg.engine,
            "genre": new_cfg.genre,
            "monetization": new_cfg.monetization,
            "max_iterations": new_cfg.max_iterations,
        }}

    # ── Reset / Delete project ────────────────────────

    @app.delete("/api/v1/project")
    async def delete_project() -> dict[str, Any]:
        """Reset the project: stop pipeline, clear DB, delete all generated files."""
        global _pipeline

        try:
            # 1. Stop pipeline if running
            pipeline = get_pipeline()
            if pipeline.state.is_running:
                await pipeline.stop()
                # Give pipeline time to fully stop
                await asyncio.sleep(1)

            # 2. Clear all database tables
            if pipeline.database:
                await pipeline.database.reset_all_data()
                await pipeline.database.close()

            # 3. Delete project.json to restore defaults
            project_file = ROOT_DIR / "project.json"
            if project_file.exists():
                project_file.unlink()

            # 4. Clear generated game source files (keep game/ dir itself)
            game_src = GAME_DIR / "src"
            if game_src.exists():
                shutil.rmtree(game_src, ignore_errors=True)
                game_src.mkdir(exist_ok=True)  # Recreate empty src/

            # 5. Clear snapshots
            snapshots_dir = GAME_DIR / ".snapshots"
            if snapshots_dir.exists():
                shutil.rmtree(snapshots_dir, ignore_errors=True)

            # 6. Clear agent memories
            memory_dir = ROOT_DIR / "data" / "memory"
            if memory_dir.exists():
                shutil.rmtree(memory_dir, ignore_errors=True)

            # 7. Clear chat store
            chat_db = ROOT_DIR / "data" / "chat_store.db"
            if chat_db.exists():
                chat_db.unlink(missing_ok=True)

            # 8. Clear pipeline journal (legacy single-file formats)
            for journal_ext in ("db", "json"):
                journal_file = ROOT_DIR / "data" / f"pipeline_journal.{journal_ext}"
                if journal_file.exists():
                    journal_file.unlink(missing_ok=True)

            # 8b. Clear journal iteration files (data/journal/)
            journal_dir = ROOT_DIR / "data" / "journal"
            if journal_dir.exists():
                shutil.rmtree(journal_dir, ignore_errors=True)

            # 8c. Clear screenshots from previous iterations
            screenshots_dir = ROOT_DIR / "data" / "screenshots"
            if screenshots_dir.exists():
                shutil.rmtree(screenshots_dir, ignore_errors=True)

            # 8d. Clear session logs (but keep logs/ dir)
            logs_dir = ROOT_DIR / "data" / "logs"
            if logs_dir.exists():
                shutil.rmtree(logs_dir, ignore_errors=True)

            # 8e. Clear error patterns JSON
            error_patterns_json = ROOT_DIR / "data" / "error_patterns.json"
            if error_patterns_json.exists():
                error_patterns_json.unlink(missing_ok=True)


            # 10. Reset pipeline singleton
            _pipeline = None

            # 11. Clear cache
            await get_cache().clear()

            # 12. Broadcast reset event to all WS clients
            await ws_manager.broadcast({
                "type": "project_reset",
                "data": {"message": "Project has been reset"},
            })

            logger.info("Project reset: all data and generated files cleared")
            return {"success": True, "message": "Project reset successfully"}

        except Exception as exc:
            logger.exception("Failed to reset project: %s", exc)
            return {"success": False, "error": str(exc)}

    # ── M6: Batched dashboard endpoint ─────────────────

    @app.get("/api/v1/dashboard-data")
    @cache_response(ttl=5.0, prefix="dashboard_data")
    async def get_dashboard_data() -> dict[str, Any]:
        """Return all dashboard data in a single request to reduce round-trips."""
        pipeline = get_pipeline()
        return {
            "status": {
                "status": "running" if pipeline.state.is_running else "stopped",
                "paused": pipeline.state.is_paused,
                "pipeline": pipeline.state.to_dict(),
                "providers": pipeline.llm_router.available_providers,
                "ws_clients": ws_manager.connection_count,
            },
            "quality": {
                "history": pipeline.quality_engine.get_history(),
                "trend": pipeline.quality_engine.get_trend(),
                "weights": pipeline.quality_engine.get_weights(),
            },
            "cost": pipeline.cost_guard.get_stats(),
            "health": pipeline.watchdog.get_health().to_dict(),
            "stagnation": {
                "stagnation": pipeline.stagnation_guard.get_stats(),
                "exploration": pipeline.exploration_controller.get_stats(),
            },
            "experiments": {
                "experiments": pipeline.experiment_tracker.get_history(limit=20),
                "stats": pipeline.experiment_tracker.get_stats(),
            },
            # v3 Item 16: Real-Time Dashboard Analytics
            "analytics": PipelineAnalytics.get_full_analytics(pipeline),
        }

    # ── v3 Item 16: Analytics endpoints ──────────────────

    @app.get("/api/v1/analytics")
    @cache_response(ttl=10.0, prefix="analytics")
    async def get_analytics() -> dict[str, Any]:
        """Full analytics payload for the dashboard."""
        pipeline = get_pipeline()
        return PipelineAnalytics.get_full_analytics(pipeline)

    @app.get("/api/v1/analytics/projections")
    @cache_response(ttl=15.0, prefix="analytics_proj")
    async def get_analytics_projections() -> dict[str, Any]:
        """Quality score projections only."""
        pipeline = get_pipeline()
        return PipelineAnalytics.get_quality_projection(
            pipeline.quality_engine
        )

    # ── Snapshots endpoint ──────────────────────────────

    @app.get("/api/v1/snapshots")
    async def get_snapshots() -> dict[str, Any]:
        """List available code snapshots with metadata."""
        import datetime
        snap_dir = GAME_DIR / ".snapshots"
        snapshots: list[dict[str, Any]] = []
        if snap_dir.exists():
            for d in sorted(snap_dir.iterdir(), reverse=True):
                if d.is_dir() and d.name.startswith("iter_"):
                    try:
                        iter_num = int(d.name.split("_")[1])
                    except (ValueError, IndexError):
                        iter_num = 0
                    stat = d.stat()
                    file_count = sum(1 for _ in d.rglob("*.js"))
                    snapshots.append({
                        "iteration": iter_num,
                        "name": d.name,
                        "timestamp": datetime.datetime.fromtimestamp(
                            stat.st_mtime
                        ).isoformat(),
                        "file_count": file_count,
                    })
        return {"snapshots": snapshots, "total": len(snapshots)}


    @app.get("/api/v1/productivity-metrics")
    async def get_productivity_metrics() -> dict[str, Any]:
        """Pipeline productivity metrics (build rates, cache, retries)."""
        pipeline = get_pipeline()
        return pipeline.get_productivity_metrics()


    # ── v3 Item 17: Multi-Game Factory endpoints ────────

    @app.get("/api/v1/games")
    async def list_games() -> dict[str, Any]:
        """List all registered games."""
        mp = get_multi_pipeline()
        return mp.get_summary()

    @app.post("/api/v1/games")
    async def create_game(body: dict[str, Any]) -> dict[str, Any]:
        """Create a new game in the multi-pipeline manager."""
        game_id = body.get("game_id")
        game_name = body.get("game_name", "New Game").strip()
        platform = body.get("platform", "browser")
        engine = body.get("engine", "phaser3")
        genre = body.get("genre", "idle_rpg")
        monetization = body.get("monetization", "hybrid")
        priority = int(body.get("priority", 5))
        max_iterations = int(body.get("max_iterations", 100))

        errors: list[str] = []
        if not game_name:
            errors.append("game_name is required")
        if platform not in VALID_PLATFORMS:
            errors.append(f"invalid platform: {platform}")
        if engine not in VALID_ENGINES:
            errors.append(f"invalid engine: {engine}")
        if genre not in VALID_GENRES:
            errors.append(f"invalid genre: {genre}")
        if monetization not in VALID_MONETIZATIONS:
            errors.append(f"invalid monetization: {monetization}")
        if errors:
            return {"success": False, "errors": errors}

        project_config = ProjectConfig(
            game_name=game_name,
            platform=platform,
            engine=engine,
            genre=genre,
            monetization=monetization,
            max_iterations=max_iterations,
        )

        mp = get_multi_pipeline()
        try:
            slot = mp.add_game(
                game_id=game_id,
                project_config=project_config,
                priority=priority,
                max_iterations=max_iterations,
            )
            return {"success": True, "game": slot.to_dict()}
        except ValueError as exc:
            return {"success": False, "errors": [str(exc)]}

    @app.get("/api/v1/games/summary")
    async def get_games_summary() -> dict[str, Any]:
        """Unified dashboard summary of all games."""
        mp = get_multi_pipeline()
        return mp.get_summary()

    @app.get("/api/v1/games/{game_id}")
    async def get_game(game_id: str) -> dict[str, Any]:
        """Get status of a specific game."""
        mp = get_multi_pipeline()
        slot = mp.get_game(game_id)
        if not slot:
            return {"error": f"Game '{game_id}' not found"}
        return slot.to_dict()

    @app.delete("/api/v1/games/{game_id}")
    async def delete_game(game_id: str) -> dict[str, Any]:
        """Remove a game from the multi-pipeline."""
        mp = get_multi_pipeline()
        removed = mp.remove_game(game_id)
        return {"success": removed, "game_id": game_id}

    @app.post("/api/v1/games/{game_id}/start")
    async def start_game_pipeline(
        game_id: str, max_iterations: int = 100,
    ) -> dict[str, Any]:
        """Start the pipeline for a specific game."""
        mp = get_multi_pipeline()
        try:
            return await mp.start_game(game_id, max_iterations=max_iterations)
        except ValueError as exc:
            return {"error": str(exc)}

    @app.post("/api/v1/games/{game_id}/stop")
    async def stop_game_pipeline(game_id: str) -> dict[str, Any]:
        """Stop the pipeline for a specific game."""
        mp = get_multi_pipeline()
        try:
            return await mp.stop_game(game_id)
        except ValueError as exc:
            return {"error": str(exc)}

    @app.post("/api/v1/games/{game_id}/pause")
    async def pause_game_pipeline(game_id: str) -> dict[str, Any]:
        """Pause the pipeline for a specific game."""
        mp = get_multi_pipeline()
        try:
            return await mp.pause_game(game_id)
        except ValueError as exc:
            return {"error": str(exc)}

    @app.post("/api/v1/games/{game_id}/resume")
    async def resume_game_pipeline(game_id: str) -> dict[str, Any]:
        """Resume the pipeline for a specific game."""
        mp = get_multi_pipeline()
        try:
            return await mp.resume_game(game_id)
        except ValueError as exc:
            return {"error": str(exc)}

    @app.get("/api/v1/games/{game_id}/insights")
    async def get_game_insights(game_id: str) -> dict[str, Any]:
        """Cross-pollination insights from sibling games."""
        mp = get_multi_pipeline()
        return mp.get_cross_insights(game_id)

    # ── Serve game static files ────────────────────────
    game_dist = GAME_DIR / "dist"
    if game_dist.exists():
        app.mount(
            "/game",
            StaticFiles(directory=str(game_dist), html=True),
            name="game",
        )

    return app
