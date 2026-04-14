"""
Pipeline Steps — Evaluate & Finalize (Steps 12–19)
"""

from __future__ import annotations

import json
import logging
from typing import Any, TYPE_CHECKING

from backend.core.prompt_compressor import summarize_history, smart_truncate

from backend.core.quality_engine import QualityMetrics

if TYPE_CHECKING:
    from backend.orchestrator.pipeline import Pipeline

logger = logging.getLogger(__name__)


async def run_novelty_step(
    ctx: Pipeline,
    iteration: int,
    gdd_update: dict[str, Any],
) -> dict[str, Any]:
    """Step 12: Novelty Engine — compute diversity score."""
    await ctx._emit("step_start", {"iteration": iteration, "agent": "novelty_engine"})

    novelty_score = ctx.novelty_engine.compute_novelty(gdd_update)
    ctx.novelty_engine.record_iteration(gdd_update)
    ctx._last_novelty_score = novelty_score

    await ctx._emit("novelty_computed", {
        "iteration": iteration,
        "novelty_score": novelty_score,
        "stats": ctx.novelty_engine.get_stats(),
    })

    return {"novelty_score": novelty_score}


async def run_quality_step(
    ctx: Pipeline,
    iteration: int,
    test_report: dict[str, Any],
    sim_metrics: dict[str, Any],
    eval_metrics: dict[str, Any],
    novelty_score: float,
    build_success: bool,
    headless_result: Any,
) -> dict[str, Any]:
    """Step 13: Quality Engine — multi-objective score."""
    await ctx._emit("step_start", {"iteration": iteration, "agent": "quality_engine"})

    headless_crash_rate = 0.0
    headless_error_count = 0
    if headless_result is not None and hasattr(headless_result, 'crash_detected'):
        if headless_result.crash_detected:
            headless_crash_rate = 0.5
        headless_error_count = len(getattr(headless_result, 'js_exceptions', []))

    # v2.1: Calculate integration score from roadmap progress
    integration_score = 0.0
    try:
        progress = ctx.roadmap.scan_progress()
        integration_score = progress.get("progress_pct", 0.0)
        logger.info(
            "🗺️ Integration score: %.1f%% (%d/%d tasks complete)",
            integration_score,
            len(progress.get("completed_tasks", [])),
            progress.get("total_tasks", 0),
        )
    except Exception as e:
        logger.warning("⚠️ Could not compute integration score: %s", e)

    # v2.2: Extract headless health score for stability dimension
    headless_health_score = -1.0  # -1 means not available
    if headless_result is not None:
        if isinstance(headless_result, dict):
            headless_health_score = headless_result.get("health_score", -1.0)
        elif hasattr(headless_result, "health_score"):
            headless_health_score = headless_result.health_score

    quality_metrics = QualityMetrics(
        fun_score=test_report.get("player_experience", {}).get("score", 50) if isinstance(test_report, dict) else 50,
        session_length_avg=sim_metrics.get("session_length_avg", 0),
        engagement_rate=sim_metrics.get("engagement_rate", 0),
        crash_rate=max(sim_metrics.get("crash_rate", 0), headless_crash_rate),
        build_success=build_success,
        error_count=len(eval_metrics.get("issues", [])) + headless_error_count,
        file_count=eval_metrics.get("total_files", 0),
        total_lines=eval_metrics.get("total_lines", 0),
        economy_inflation=sim_metrics.get("economy_inflation", 0),
        progression_slope=sim_metrics.get("progression_slope", 0),
        novelty_score=novelty_score,
        sim_runs=sim_metrics.get("sim_runs", 0),
        sim_variance=sim_metrics.get("sim_variance", 0),
        gold_per_hour=sim_metrics.get("gold_per_hour", 0),
        xp_per_hour=sim_metrics.get("xp_per_hour", 0),
        estimated_retention_d1=sim_metrics.get("estimated_retention_d1", 0),
        estimated_retention_d7=sim_metrics.get("estimated_retention_d7", 0),
        estimated_retention_d30=sim_metrics.get("estimated_retention_d30", 0),
        integration_score=integration_score,
        headless_health_score=headless_health_score,
    )

    quality_breakdown = ctx.quality_engine.evaluate(
        metrics=quality_metrics,
        previous_metrics=ctx._previous_metrics,
    )
    ctx._previous_metrics = quality_metrics

    await ctx._emit("quality_scored", {
        "iteration": iteration,
        "composite": quality_breakdown.composite,
        "confidence_interval": [
            quality_breakdown.confidence_lower,
            quality_breakdown.confidence_upper,
        ],
        "fun": quality_breakdown.fun,
        "stability": quality_breakdown.stability,
        "performance": quality_breakdown.performance,
        "balance": quality_breakdown.balance,
        "novelty": quality_breakdown.novelty,
        "retention": quality_breakdown.retention,
        "integration": quality_breakdown.integration,
        "regression_penalty": quality_breakdown.regression_penalty,
        "weights": ctx.quality_engine.get_weights(),
    })

    return {
        "quality_metrics": quality_metrics,
        "quality_breakdown": quality_breakdown,
    }


async def run_diff_step(
    ctx: Pipeline,
    iteration: int,
    current_score: int,
) -> dict[str, Any]:
    """Step 14: Diff Analyzer — analyze code change risk."""
    await ctx._emit("step_start", {"iteration": iteration, "agent": "diff_analyzer"})

    current_game_files = ctx.diff_analyzer.get_current_files()
    diff_report = ctx.diff_analyzer.analyze(
        previous_files=ctx._previous_files,
        current_files=current_game_files,
    )

    # Generate unified diff text for the Critic (Roadmap #7: Diff-aware Critic)
    code_diff = ctx.diff_analyzer.generate_diff(
        previous_files=ctx._previous_files,
        current_files=current_game_files,
    )

    ctx._previous_files = current_game_files

    adjusted_score = current_score
    if diff_report.risk_score > 60:
        penalty = diff_report.risk_score * 0.05
        adjusted_score = max(0, int(current_score - penalty))
        logger.warning(
            "⚠️ Diff risk penalty: -%.1f pontos (risk=%.0f, level=%s)",
            penalty, diff_report.risk_score, diff_report.risk_level,
        )

    return {
        "diff_report": diff_report,
        "current_game_files": current_game_files,
        "code_diff": code_diff,
        "adjusted_score": adjusted_score,
    }


async def run_critic_step(
    ctx: Pipeline,
    iteration: int,
    test_report: dict[str, Any],
    gdd_update: dict[str, Any],
    quality_breakdown: Any,
    diff_report: Any,
    sim_aggregate: Any,
    exploration: bool,
    dev_result: Any,
    build_success: bool,
    build_output: str,
    current_game_files: dict[str, str],
    perf_score: float,
    code_diff: str = "",
    benchmark_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Step 15: Critic — strategic analysis and instructions.

    Roadmap #7 (Diff-aware Critic): receives a unified diff of the
    iteration's code changes so feedback targets what actually changed.
    """
    await ctx._emit("step_start", {"iteration": iteration, "agent": "critic"})
    ctx.llm_router.set_context("critic", iteration)

    critic_input = {
        "test_report": test_report,
        "gdd_update": gdd_update,
        "iteration_history": summarize_history(ctx.state.get_recent_history()),
        "quality_breakdown": {
            "composite": quality_breakdown.composite,
            "fun": quality_breakdown.fun,
            "stability": quality_breakdown.stability,
            "performance": quality_breakdown.performance,
            "balance": quality_breakdown.balance,
            "novelty": quality_breakdown.novelty,
            "regression_penalty": quality_breakdown.regression_penalty,
        },
        "diff_risk": diff_report.to_dict(),
        "code_diff": code_diff or "(no changes)",
        "simulation_summary": {
            "avg_level": sim_aggregate.avg_level,
            "crash_rate": sim_aggregate.crash_rate,
            "economy_inflation": sim_aggregate.economy_inflation,
            "progression_slope": sim_aggregate.progression_slope,
            "is_bimodal": sim_aggregate.is_bimodal,
        },
        "cost_stats": ctx.cost_guard.get_stats(),
        "exploration_mode": exploration,
        "implemented_files": list(current_game_files.keys()),
        "developer_summary": smart_truncate(dev_result.output, 1500) if (dev_result and dev_result.success) else "Developer failed",
        "build_output": smart_truncate(build_output, 1000) if not build_success else "Build OK",
        "benchmark_context": benchmark_report or {},
    }

    # v3 Item #13: Inject GDD drift alerts
    if hasattr(ctx, "gdd_tracker"):
        try:
            critic_input["gdd_drift_alerts"] = ctx.gdd_tracker.get_drift_alerts()
            critic_input["gdd_evolution_summary"] = ctx.gdd_tracker.get_evolution_summary()
        except Exception:
            pass

    critic_result = await ctx.critic.run(iteration, critic_input)
    critic_feedback = critic_result.metadata.get("feedback", {})

    # Save context for next iteration's Developer
    ctx._last_test_report = test_report if isinstance(test_report, dict) else {}
    ctx._last_critic_feedback = critic_feedback if isinstance(critic_feedback, dict) else {}
    ctx._last_quality_breakdown = {
        "fun": quality_breakdown.fun,
        "stability": quality_breakdown.stability,
        "performance": quality_breakdown.performance,
        "balance": quality_breakdown.balance,
        "novelty": quality_breakdown.novelty,
    }
    # Accumulate known bugs
    if isinstance(test_report, dict):
        bugs = test_report.get("bugs", []) or test_report.get("critical_bugs", [])
        for bug in (bugs or []):
            bug_str = str(bug) if not isinstance(bug, str) else bug
            if bug_str not in ctx._known_bugs:
                ctx._known_bugs.append(bug_str)
        ctx._known_bugs = ctx._known_bugs[-20:]

    return {"critic_feedback": critic_feedback}


async def run_stagnation_step(
    ctx: Pipeline,
    iteration: int,
    quality_breakdown: Any,
    novelty_score: float,
) -> dict[str, Any]:
    """Step 16: Stagnation Guard — detect plateau and trigger exploration."""
    await ctx._emit("step_start", {"iteration": iteration, "agent": "stagnation_guard"})

    ctx.stagnation_guard.record(
        score=quality_breakdown.composite,
        novelty=novelty_score,
    )
    stagnation_result = ctx.stagnation_guard.check()

    if stagnation_result.should_rollback:
        best = ctx.versioner.get_best_snapshot()
        if best:
            rollback_iter = best["iteration"]
            logger.warning(
                "🔄 Rollback para iteração #%d (score: %d)",
                rollback_iter, best.get("score", 0),
            )
            ctx.versioner.restore_snapshot(rollback_iter)
            await ctx._emit("rollback", {
                "iteration": iteration,
                "rollback_to": rollback_iter,
                "reason": stagnation_result.reason,
            })
    elif stagnation_result.exploration_mode:
        await ctx._emit("stagnation_detected", {
            "iteration": iteration,
            "reason": stagnation_result.reason,
            "exploration_iterations": stagnation_result.exploration_iterations,
            "recommended_temperature": stagnation_result.recommended_temperature,
        })

    return {"stagnation_result": stagnation_result}


async def run_cost_check_step(
    ctx: Pipeline,
) -> dict[str, Any]:
    """Step 17: Cost Guard — verify budget (advisory only, never stops pipeline)."""
    can_continue, cost_reason = ctx.cost_guard.check_budget()
    if not can_continue:
        logger.warning("💰 Cost Guard: budget excedido — %s (pipeline continua)", cost_reason)
        # Advisory only: log the warning but do NOT stop the pipeline.
        # The factory must keep running until the game is ready.
        await ctx.emit_chat(
            "cost_guard",
            f"💰 Aviso de budget: {cost_reason}. Pipeline continua operando.",
            ctx.state.current_iteration, "warning",
        )

    return {"can_continue": can_continue, "cost_reason": cost_reason}


async def run_experiment_step(
    ctx: Pipeline,
    iteration: int,
    quality_breakdown: Any,
    novelty_score: float,
    perf_score: float,
    sim_aggregate: Any,
    diff_report: Any,
    build_success: bool,
    exploration: bool,
    is_milestone: bool,
    iteration_score: int,
    stagnation_result: Any,
) -> None:
    """Step 18: Experiment Tracker — snapshot iteration."""
    cost_stats = ctx.cost_guard.get_stats()
    iter_cost = cost_stats.get("total_cost_usd", 0.0)

    tags: list[str] = []
    if is_milestone:
        tags.append("milestone")
    if exploration:
        tags.append("exploration_mode")
    if stagnation_result.should_rollback:
        tags.append("rollback")
    if iteration_score == ctx.state.best_score:
        tags.append("best_score")

    ctx.experiment_tracker.record_from_dict(
        iteration=iteration,
        quality_score=quality_breakdown.composite,
        quality_breakdown={
            "fun": quality_breakdown.fun,
            "stability": quality_breakdown.stability,
            "performance": quality_breakdown.performance,
            "balance": quality_breakdown.balance,
            "novelty": quality_breakdown.novelty,
        },
        novelty_score=novelty_score,
        performance_score=perf_score,
        sim_runs=sim_aggregate.total_runs,
        sim_crash_rate=sim_aggregate.crash_rate,
        sim_engagement=sim_aggregate.engagement_rate,
        diff_risk_score=diff_report.risk_score,
        cost_usd=iter_cost,
        build_success=build_success,
        iteration_status="completed",
        exploration_mode=exploration,
        tags=tags,
    )


async def run_memory_curator_step(
    ctx: Pipeline,
    iteration: int,
) -> None:
    """Step 19: Memory Curator — curate agent memories (every 5 iters)."""
    if not ctx.memory_curator.should_run(iteration):
        return

    await ctx._emit("step_start", {"iteration": iteration, "agent": "memory_curator"})
    ctx.llm_router.set_context("memory_curator", iteration)

    curator_input: dict[str, Any] = {
        "quality_history": [
            {"composite": h.score}
            for h in ctx.state.history[-20:]
        ],
    }

    if ctx.experience_db and ctx.experience_db.is_available:
        try:
            curator_input["experience_stats"] = ctx.experience_db.get_stats()
        except Exception:
            pass

    curator_result = await ctx.memory_curator.run(iteration, curator_input)
    await ctx._emit("memory_curated", {
        "iteration": iteration,
        "meta_insights": curator_result.metadata.get("meta_insights", 0),
        "winning_patterns": curator_result.metadata.get("winning_patterns", 0),
        "memory_status": curator_result.metadata.get("memory_status", "unknown"),
    })
