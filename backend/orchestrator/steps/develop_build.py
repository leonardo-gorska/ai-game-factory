"""
Pipeline Steps — Develop & Build (Steps 3–4)
"""

from __future__ import annotations

import logging
from typing import Any, TYPE_CHECKING

from backend.core.prompt_compressor import compress_code_context
from backend.config import GAME_DIR

import re
from pathlib import Path

if TYPE_CHECKING:
    from backend.orchestrator.pipeline import Pipeline

logger = logging.getLogger(__name__)


async def run_developer_step(
    ctx: Pipeline,
    iteration: int,
    gdd_update: dict[str, Any],
) -> dict[str, Any]:
    """Step 3: Developer — write game code."""
    await ctx._emit("step_start", {"iteration": iteration, "agent": "developer"})
    ctx.llm_router.set_context("developer", iteration)

    current_files = ctx.builder.get_source_files()
    current_files = compress_code_context(current_files)

    # Get roadmap task context for focused development
    roadmap_task = ctx.roadmap.get_developer_context()

    # v2 Roadmap: Template Library — suggest relevant templates
    suggested_templates = ctx.template_registry.suggest(
        gdd=gdd_update,
        existing_files=current_files,
    )
    available_templates = None
    if suggested_templates:
        available_templates = [
            {
                "system": t.system,
                "category": t.category,
                "description": t.description,
                "code": t.code,
            }
            for t in suggested_templates
        ]
        ctx._metrics["templates_suggested"] += len(suggested_templates)
        logger.info(
            "📚 %d template(s) suggested for iteration %d: %s",
            len(suggested_templates), iteration,
            [t.system for t in suggested_templates],
        )
        await ctx._emit("templates_suggested", {
            "iteration": iteration,
            "templates": [t.system for t in suggested_templates],
        })

    # v3 Item 8: Semantic Code Graph — inject dependents context
    dependency_context: dict[str, str] = {}
    if hasattr(ctx, "code_graph") and ctx.code_graph.is_initialized:
        try:
            changed_files_list = list(current_files.keys())
            dependency_context = ctx.code_graph.get_context_for_developer(
                changed_files_list, current_files,
            )
            if dependency_context:
                ctx._metrics["code_graph_context_files"] += len(dependency_context)
                logger.info(
                    "📊 Code Graph: injecting %d dependent file(s) into developer context",
                    len(dependency_context),
                )
        except Exception as exc:
            logger.warning("Code Graph context failed: %s", exc)

    input_data = {
        "gdd_update": gdd_update,
        "current_files": current_files,
        "last_test_report": ctx._last_test_report,
        "last_critic_feedback": ctx._last_critic_feedback,
        "quality_breakdown": ctx._last_quality_breakdown,
        "known_bugs": ctx._known_bugs,
        "roadmap_task": roadmap_task,
        "available_templates": available_templates,
        "dependency_context": dependency_context,
    }

    # v3 Item 9: Agent Specialization Fork
    forked = False
    if hasattr(ctx, "agent_forker"):
        try:
            decision = ctx.agent_forker.detect_divergent_goals(input_data)
            if decision.should_fork:
                ctx._metrics["agent_forks_detected"] += 1
                logger.info("🔀 Forking developer: %s", decision.reason)
                merged = await ctx.agent_forker.execute_forks(
                    ctx.developer, iteration, decision.tasks,
                )
                ctx._metrics["agent_forks_executed"] += 1
                ctx._metrics["agent_fork_conflicts"] += len(merged.conflicts)
                forked = True
                code_changes = merged.merged_code_changes
        except Exception as exc:
            logger.warning("Agent fork failed, falling back to normal: %s", exc)

    dev_result = None
    if not forked:
        dev_result = await ctx.developer.run(iteration, input_data)
        code_changes = dev_result.metadata.get("code_changes", {})
    files_written = (
        dev_result.metadata.get("files_written", [])
        if dev_result else code_changes.get("files", [])
    )

    # ── Detect empty file output ────────────────────────
    if (dev_result and dev_result.success and not files_written) or (forked and not files_written):
        logger.warning(
            "⚠️ Developer agent succeeded but wrote 0 files on iteration %d. "
            "GDD update had %d keys. This iteration will be degraded.",
            iteration, len(gdd_update) if isinstance(gdd_update, dict) else 0,
        )
        await ctx._emit("developer_no_files", {
            "iteration": iteration,
            "message": "Developer produced no code changes this iteration",
        })
    else:
        logger.info(
            "Developer wrote %d file(s) on iteration %d",
            len(files_written), iteration,
        )

    # v2.3 P5/P7: Line-loss guard — reject writes that remove >30% of existing file
    if files_written and not forked:
        _protected_files = _check_line_loss(
            ctx, iteration, current_files, code_changes,
        )
        if _protected_files:
            logger.warning(
                "🛡️ Line-loss guard protected %d file(s) from truncation: %s",
                len(_protected_files), _protected_files,
            )

    return {
        "dev_result": dev_result,
        "code_changes": code_changes,
    }


async def run_build_step(
    ctx: Pipeline,
    iteration: int,
    gdd_update: dict[str, Any],
) -> dict[str, Any]:
    """Step 4: Build + Lint — validate compilation."""
    await ctx._emit("step_start", {"iteration": iteration, "agent": "builder"})

    build_success, build_output = await ctx._build_with_retries(
        iteration, gdd_update
    )

    return {
        "build_success": build_success,
        "build_output": build_output,
    }


# ── v2.3 P5/P7: Line-Loss Guard ──────────────────────────────────────

_LINE_LOSS_THRESHOLD = 0.30  # reject if >30% of lines are removed


def _check_line_loss(
    ctx: Pipeline,
    iteration: int,
    previous_files: dict[str, str],
    code_changes: dict[str, Any],
) -> list[str]:
    """Detect and reject files where the developer removed >30% of lines.

    Returns list of protected filenames.
    """
    protected: list[str] = []
    new_files = code_changes.get("files", {})
    if not isinstance(new_files, dict):
        return protected

    for filename, new_content in new_files.items():
        if filename not in previous_files:
            continue  # new file, no comparison
        old_content = previous_files[filename]
        old_lines = len(old_content.splitlines())
        new_lines = len(new_content.splitlines()) if isinstance(new_content, str) else 0

        if old_lines < 10:
            continue  # too small to matter

        loss_ratio = (old_lines - new_lines) / old_lines
        if loss_ratio > _LINE_LOSS_THRESHOLD:
            logger.warning(
                "🛡️ Line-loss guard: '%s' would shrink from %d→%d lines (%.0f%% loss). "
                "Restoring original.",
                filename, old_lines, new_lines, loss_ratio * 100,
            )
            # Restore the original file on disk
            try:
                game_dir = GAME_DIR
                full_path = game_dir / filename
                full_path.write_text(old_content, encoding="utf-8")
                protected.append(filename)
                ctx._metrics.setdefault("line_loss_protections", 0)
                ctx._metrics["line_loss_protections"] += 1
            except Exception as exc:
                logger.warning("Line-loss restore failed for %s: %s", filename, exc)

    return protected


# ── v2.3 P8: Post-Build Validation ───────────────────────────────────

async def run_post_build_validation(
    ctx: Pipeline,
    iteration: int,
    build_success: bool,
) -> list[str]:
    """Quick integrity checks after a successful build.

    Returns list of warning messages (empty = all good).
    """
    if not build_success:
        return []

    warnings: list[str] = []
    game_dir = GAME_DIR
    src_dir = game_dir / "src"

    if not src_dir.exists():
        return []

    # 1. Check for stub files in systems/
    systems_dir = src_dir / "systems"
    if systems_dir.exists():
        from backend.core.game_roadmap import GameRoadmap
        for js_file in systems_dir.glob("*.js"):
            if GameRoadmap._is_stub_file(js_file):
                warnings.append(f"⚠️ Stub: {js_file.name} has no real methods")

    # 2. Check MainScene has update() method
    main_scene = src_dir / "scenes" / "MainScene.js"
    if main_scene.exists():
        content = main_scene.read_text(encoding="utf-8", errors="replace")
        if "update(time" not in content and "update (time" not in content:
            warnings.append("⚠️ MainScene.js is missing update(time, delta) method")

    # 3. Check BootScene has texture generation
    boot_scene = src_dir / "scenes" / "BootScene.js"
    if boot_scene.exists():
        content = boot_scene.read_text(encoding="utf-8", errors="replace")
        if "generateTexture" not in content:
            warnings.append("⚠️ BootScene.js has no generateTexture() calls — sprites will be green squares")

    # 4. Check for malformed filenames (path concatenation bugs)
    for f in src_dir.iterdir():
        if f.is_file() and f.suffix == ".js" and ("systems" in f.stem or "scenes" in f.stem or "entities" in f.stem):
            warnings.append(f"⚠️ Malformed filename: {f.name} (looks like a path concatenation bug)")

    # Emit warnings
    if warnings:
        logger.warning(
            "📋 Post-build validation found %d issue(s) on iter %d:",
            len(warnings), iteration,
        )
        for w in warnings:
            logger.warning("  %s", w)
        await ctx.emit_chat(
            "validator",
            f"📋 {len(warnings)} issue(s) found: {'; '.join(w[:60] for w in warnings[:3])}",
            iteration, "warning",
        )
        ctx._metrics.setdefault("post_build_warnings", 0)
        ctx._metrics["post_build_warnings"] += len(warnings)

    return warnings
