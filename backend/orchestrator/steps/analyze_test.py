"""
Pipeline Steps — Analysis & Testing (Steps 5–11)
"""

from __future__ import annotations

import logging
from typing import Any, TYPE_CHECKING

from backend.core.prompt_compressor import compress_code_context

if TYPE_CHECKING:
    from backend.orchestrator.pipeline import Pipeline

logger = logging.getLogger(__name__)


async def run_performance_step(
    ctx: Pipeline,
    iteration: int,
    build_output: str,
    build_success: bool,
    gdd_update: dict[str, Any],
) -> dict[str, Any]:
    """Step 5: Performance Agent — analyze bundle, game loops, memory leaks."""
    await ctx._emit("step_start", {"iteration": iteration, "agent": "performance"})
    ctx.llm_router.set_context("performance", iteration)

    perf_result = await ctx.performance_agent.run(iteration, {
        "game_files": compress_code_context(ctx.builder.get_source_files()),
        "build_output": build_output,
        "build_success": build_success,
        "gdd_update": gdd_update,
    })
    perf_score = perf_result.metadata.get("performance_score", 50.0)

    await ctx._emit("performance_analyzed", {
        "iteration": iteration,
        "performance_score": perf_score,
        "optimizations_count": perf_result.metadata.get("optimizations_count", 0),
    })

    return {"perf_score": perf_score, "perf_result": perf_result}


async def run_headless_test_step(
    ctx: Pipeline,
    iteration: int,
    build_success: bool,
) -> dict[str, Any]:
    """Step 6: Headless Browser Test (optional, P11)."""
    headless_result = None
    if ctx.headless_tester and build_success:
        await ctx._emit("step_start", {"iteration": iteration, "agent": "headless_tester"})
        try:
            server_ok, server_msg = await ctx.builder.start_dev_server()
            if server_ok:
                headless_result = await ctx.headless_tester.run_test(
                    iteration=iteration,
                    observe_seconds=8,
                )
                await ctx._emit("headless_test_complete", {
                    "iteration": iteration,
                    **headless_result.to_dict(),
                })
                logger.info(
                    "🎮 Headless: health=%.0f, fps=%.0f, errors=%d",
                    headless_result.health_score,
                    headless_result.avg_fps,
                    len(headless_result.console_errors),
                )
            else:
                logger.warning("Dev server failed: %s", server_msg)
        except Exception as exc:
            logger.warning("Headless test failed: %s", exc)

    return {"headless_result": headless_result}


async def run_simulator_step(
    ctx: Pipeline,
    iteration: int,
) -> dict[str, Any]:
    """Step 7: Simulator — playtest with multiple profiles."""
    await ctx._emit("step_start", {"iteration": iteration, "agent": "simulator"})

    sim_aggregate = ctx.simulator.run_simulation(
        num_runs=50,
        durations_hours=[1.0, 6.0, 24.0, 48.0, 168.0, 720.0],
        seed=iteration,
    )
    sim_metrics = sim_aggregate.to_quality_metrics()

    await ctx._emit("simulation_complete", {
        "iteration": iteration,
        "runs": sim_aggregate.total_runs,
        "crash_rate": sim_aggregate.crash_rate,
        "avg_level": sim_aggregate.avg_level,
        "gold_per_hour": sim_aggregate.avg_gold_per_hour,
        "is_bimodal": sim_aggregate.is_bimodal,
        "confidence_interval": [
            sim_aggregate.confidence_lower,
            sim_aggregate.confidence_upper,
        ],
        "per_profile": [
            {"profile": ps.profile, "avg_level": ps.avg_level}
            for ps in sim_aggregate.per_profile_stats
        ],
        "retention": {
            "d1": sim_aggregate.estimated_retention_d1,
            "d7": sim_aggregate.estimated_retention_d7,
            "d30": sim_aggregate.estimated_retention_d30,
        },
        "heatmap": sim_aggregate.gameplay_heatmap.to_dict(),
    })

    return {
        "sim_aggregate": sim_aggregate,
        "sim_metrics": sim_metrics,
    }


async def run_exploit_step(
    ctx: Pipeline,
    iteration: int,
    sim_aggregate: Any,
) -> dict[str, Any]:
    """Step 8: Exploit Detector — scan for exploits."""
    exploit_report = ctx.exploit_detector.scan({
        "gold_per_hour": sim_aggregate.avg_gold_per_hour,
        "xp_per_hour": getattr(sim_aggregate, 'avg_xp_per_hour', 0),
        "economy_inflation": sim_aggregate.economy_inflation,
        "progression_slope": sim_aggregate.progression_slope,
        "stuck_rate": sim_aggregate.stuck_rate,
        "per_profile_stats": [
            {"profile": ps.profile, "avg_level": ps.avg_level}
            for ps in sim_aggregate.per_profile_stats
        ],
    })

    if exploit_report.exploit_count > 0:
        await ctx._emit("exploits_detected", {
            "iteration": iteration,
            "exploit_count": exploit_report.exploit_count,
            "has_critical": exploit_report.has_critical,
            "severity_breakdown": exploit_report.severity_breakdown,
        })

    return {"exploit_report": exploit_report}


async def run_sim_analyst_step(
    ctx: Pipeline,
    iteration: int,
    sim_metrics: dict[str, Any],
    exploit_report: Any,
    sim_aggregate: Any,
) -> dict[str, Any]:
    """Step 9: Simulation Analyst — interpret simulation data."""
    await ctx._emit("step_start", {"iteration": iteration, "agent": "simulation_analyst"})
    ctx.llm_router.set_context("simulation_analyst", iteration)

    sim_analyst_result = await ctx.simulation_analyst.run(iteration, {
        "sim_aggregate": sim_metrics,
        "exploit_report": exploit_report.to_dict() if hasattr(exploit_report, 'to_dict') else {},
        "per_profile_stats": [
            {
                "profile": ps.profile,
                "avg_level": ps.avg_level,
                "avg_gold_per_hour": getattr(ps, 'avg_gold_per_hour', 0),
                "avg_deaths": getattr(ps, 'avg_deaths', 0),
                "engagement_rate": getattr(ps, 'engagement_rate', 0),
            }
            for ps in sim_aggregate.per_profile_stats
        ],
    })
    sim_analysis = sim_analyst_result.metadata.get("simulation_analysis", {})

    await ctx._emit("simulation_analyzed", {
        "iteration": iteration,
        "insights_count": len(sim_analysis.get("insights", [])),
        "action_items_count": len(sim_analysis.get("action_items", [])),
        "economy_status": sim_analysis.get("economy_health", {}).get("status", "unknown"),
    })

    return {"sim_analysis": sim_analysis}


async def run_economy_step(
    ctx: Pipeline,
    iteration: int,
    sim_metrics: dict[str, Any],
    gdd_update: dict[str, Any],
) -> dict[str, Any]:
    """Step 10: Economy Guardian — deep economy analysis."""
    await ctx._emit("step_start", {"iteration": iteration, "agent": "economy_guardian"})
    ctx.llm_router.set_context("economy_guardian", iteration)

    economy_result = await ctx.economy_guardian.run(iteration, {
        "sim_aggregate": sim_metrics,
        "game_params": gdd_update,
        "previous_economy": ctx._previous_economy_report,
    })
    economy_report = economy_result.metadata.get("economy_report", {})
    economy_health_score = economy_result.metadata.get("economy_health_score", 50)
    ctx._previous_economy_report = economy_report

    await ctx._emit("economy_analyzed", {
        "iteration": iteration,
        "economy_health_score": economy_health_score,
        "warnings_count": len(economy_report.get("warnings", [])),
    })

    return {"economy_report": economy_report}


async def run_tester_step(
    ctx: Pipeline,
    iteration: int,
    build_success: bool,
    build_output: str,
    gdd_update: dict[str, Any],
    code_changes: dict[str, str],
    sim_aggregate: Any,
    sim_analysis: dict[str, Any],
    economy_report: dict[str, Any],
) -> dict[str, Any]:
    """Step 11: Tester — LLM evaluation with simulation and analysis data."""
    await ctx._emit("step_start", {"iteration": iteration, "agent": "tester"})
    ctx.llm_router.set_context("tester", iteration)

    updated_files = ctx.builder.get_source_files()
    eval_metrics = ctx.evaluator.evaluate()

    tester_result = await ctx.tester.run(iteration, {
        "game_files": compress_code_context(updated_files),
        "build_success": build_success,
        "build_output": build_output,
        "gdd_update": gdd_update,
        "code_changes": code_changes,
        "simulation_data": {
            "runs": sim_aggregate.total_runs,
            "crash_rate": sim_aggregate.crash_rate,
            "avg_level": sim_aggregate.avg_level,
            "avg_gold_per_hour": sim_aggregate.avg_gold_per_hour,
            "economy_inflation": sim_aggregate.economy_inflation,
            "progression_slope": sim_aggregate.progression_slope,
            "engagement_rate": sim_aggregate.engagement_rate,
            "stuck_rate": sim_aggregate.stuck_rate,
            "is_bimodal": sim_aggregate.is_bimodal,
        },
        "simulation_analysis": sim_analysis,
        "economy_report": economy_report,
    })

    test_report = tester_result.metadata.get("test_report", {})

    return {
        "test_report": test_report,
        "eval_metrics": eval_metrics,
        "tester_result": tester_result,
    }
