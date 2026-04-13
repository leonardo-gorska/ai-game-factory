"""
Pipeline Steps — Research & Design (Steps 1–2)
"""

from __future__ import annotations

import json
import logging
from backend.core.agent_cache import AgentCache
from backend.core.prompt_compressor import summarize_history
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from backend.orchestrator.pipeline import Pipeline

logger = logging.getLogger(__name__)


async def run_researcher_step(
    ctx: Pipeline,
    iteration: int,
    exploration: bool,
) -> dict[str, Any]:
    """Step 1: Researcher — feature research and innovation proposals."""
    await ctx._emit("step_start", {"iteration": iteration, "agent": "researcher"})
    ctx.llm_router.set_context("researcher", iteration)

    researcher_input: dict[str, Any] = {
        "current_gdd": ctx.designer.current_gdd,
        "exploration_mode": exploration,
    }

    if ctx.state.history:
        raw_history = [
            {
                "composite": h.score,
                "fun": h.critic_feedback.get("fun", 0) if isinstance(h.critic_feedback, dict) else 0,
                "balance": h.critic_feedback.get("balance", 0) if isinstance(h.critic_feedback, dict) else 0,
                "novelty": h.critic_feedback.get("novelty", 0) if isinstance(h.critic_feedback, dict) else 0,
            }
            for h in ctx.state.history[-10:]
        ]
        researcher_input["quality_history"] = summarize_history(raw_history, keep_last=3)

    # PIP-03: _last_novelty_score is always available (declared in Pipeline.__init__)
    researcher_input["novelty_score"] = ctx._last_novelty_score

    # ── Agent Cache: check for cached result ──
    input_hash = AgentCache.hash_input(researcher_input)
    cached = ctx.agent_cache.get("researcher", input_hash, iteration)
    if cached is not None:
        researcher_result = cached
    else:
        researcher_result = await ctx.researcher.run(iteration, researcher_input)
        ctx.agent_cache.put("researcher", input_hash, researcher_result, iteration)
    research_report = researcher_result.metadata.get("research_report", {})

    await ctx._emit("research_complete", {
        "iteration": iteration,
        "proposals": len(research_report.get("feature_proposals", [])),
        "insights": len(research_report.get("market_insights", [])),
    })

    return {
        "researcher_result": researcher_result,
        "research_report": research_report,
    }


async def _prepare_designer_context(
    ctx: Pipeline,
    iteration: int,
    exploration: bool,
) -> dict[str, Any]:
    """Pre-build designer context data (can run in parallel with researcher).

    This prepares everything that doesn't depend on the researcher result:
    history, roadmap, past experiences, exploration mode.
    """
    designer_input: dict[str, Any] = {}

    if iteration > 1 and ctx.state.history:
        prev = ctx.state.history[-1]
        cf = prev.critic_feedback
        designer_input = {
            "critic_feedback": json.dumps(cf) if isinstance(cf, dict) else str(cf or ""),
            "test_report": prev.test_report,
            "designer_instructions": cf.get(
                "designer_instructions", ""
            ) if isinstance(cf, dict) else "",
        }

    # Roadmap context
    roadmap_context = ctx.roadmap.get_designer_context()
    if roadmap_context:
        designer_input["roadmap_context"] = roadmap_context

    # Exploration mode
    if exploration:
        designer_input["exploration_mode"] = True
        designer_input["exploration_instructions"] = (
            "⚡ MODO EXPLORAÇÃO ATIVO: O sistema detectou estagnação. "
            "Você DEVE tentar algo radicalmente diferente. "
            "Mude pelo menos 2 sistemas do GDD. "
            "Adicione uma mecânica completamente nova."
        )

    # Past experiences (can be slow with vector DB)
    if ctx.experience_db and ctx.experience_db.is_available:
        situation = f"Iteration {iteration}, designing game update"
        if designer_input.get("critic_feedback"):
            situation += f", feedback: {str(designer_input['critic_feedback'])[:200]}"
        experiences = ctx.experience_db.get_similar_experiences(
            situation, top_k=3, agent="designer"
        )
        if experiences:
            designer_input["past_experiences"] = (
                ctx.experience_db.format_context(experiences)
            )

    return designer_input


async def run_designer_step(
    ctx: Pipeline,
    iteration: int,
    exploration: bool,
    exploration_decision: Any,
    researcher_result: Any,
    research_report: dict[str, Any],
    pre_built_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Step 2: Designer — update GDD with research insights.

    If pre_built_context is provided (from _prepare_designer_context running
    in parallel with researcher), it is used as starting point + merged with
    researcher results. Otherwise context is built inline.
    """
    await ctx._emit("step_start", {"iteration": iteration, "agent": "designer"})
    ctx.llm_router.set_context("designer", iteration)

    # Use pre-built context if available, otherwise build inline
    if pre_built_context is not None:
        designer_input = dict(pre_built_context)
        logger.info("⚡ Using pre-built designer context (parallel prep)")
    else:
        designer_input: dict[str, Any] = {}
        if iteration > 1 and ctx.state.history:
            prev = ctx.state.history[-1]
            designer_input = {
                "critic_feedback": json.dumps(prev.critic_feedback),
                "test_report": prev.test_report,
                "designer_instructions": prev.critic_feedback.get(
                    "designer_instructions", ""
                ) if isinstance(prev.critic_feedback, dict) else "",
            }

        # Inject roadmap context
        roadmap_context = ctx.roadmap.get_designer_context()
        if roadmap_context:
            designer_input["roadmap_context"] = roadmap_context
            logger.info("🗺️ Roadmap context injected for designer")

        # Exploration mode
        if exploration:
            designer_input["exploration_mode"] = True
            designer_input["exploration_instructions"] = (
                "⚡ MODO EXPLORAÇÃO ATIVO: O sistema detectou estagnação. "
                "Você DEVE tentar algo radicalmente diferente. "
                "Mude pelo menos 2 sistemas do GDD. "
                "Adicione uma mecânica completamente nova."
            )
            logger.info("🔀 Iter #%d em MODO EXPLORAÇÃO", iteration)

        # Past experiences
        if ctx.experience_db and ctx.experience_db.is_available:
            situation = f"Iteration {iteration}, designing game update"
            if designer_input.get("critic_feedback"):
                situation += f", feedback: {str(designer_input['critic_feedback'])[:200]}"
            experiences = ctx.experience_db.get_similar_experiences(
                situation, top_k=3, agent="designer"
            )
            if experiences:
                designer_input["past_experiences"] = (
                    ctx.experience_db.format_context(experiences)
                )

    # ── Progressive Complexity: inject phase constraints ──
    phase = ctx.complexity_manager.get_current_phase(iteration, ctx.state.best_score)
    designer_input["complexity_constraints"] = ctx.complexity_manager.get_designer_constraints(phase)
    transitioned, _ = ctx.complexity_manager.check_phase_transition(iteration, ctx.state.best_score)
    if transitioned:
        ctx._metrics["phase_transitions"] += 1
    logger.info("📊 Fase atual: %s (iter=%d, score=%d)", phase.name, iteration, ctx.state.best_score)

    # Inject Researcher proposals (always depends on researcher result)
    if researcher_result.success and research_report:
        designer_input["research_report"] = json.dumps(research_report)
        recommended = research_report.get("recommended_focus", "")
        if recommended:
            designer_input["researcher_recommendation"] = recommended

    # ── v3 Item 15: Inject Goal Setter goals ──
    if hasattr(ctx, '_last_goals') and ctx._last_goals:
        designer_input["goal_setter_goals"] = ctx._last_goals

    # ── Agent Cache: check for cached result ──
    designer_hash = AgentCache.hash_input(designer_input)
    cached_designer = ctx.agent_cache.get("designer", designer_hash, iteration)
    if cached_designer is not None:
        designer_result = cached_designer
    else:
        designer_result = await ctx.designer.run(iteration, designer_input)
        ctx.agent_cache.put("designer", designer_hash, designer_result, iteration)
    gdd_update = designer_result.metadata.get("gdd_update", {})

    # Consolidate GDD every 5 iterations
    if iteration % 5 == 0 and isinstance(gdd_update, dict):
        gdd_update = ctx.designer.consolidate_gdd(gdd_update)

    # Grace period for major exploration changes
    if exploration_decision.is_exploring:
        ctx.quality_engine.signal_major_change()

    return {
        "designer_result": designer_result,
        "gdd_update": gdd_update,
    }

