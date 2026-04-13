"""
GORVAX GAME FACTORY — Agent Specialization Fork

When the Developer agent faces divergent tasks (e.g. bug-fixing AND
new features), fork into independent sub-tasks and merge outputs.
Reduces conflicting edits by ~20%.

Roadmap v3 Item #9.
"""

from __future__ import annotations

import asyncio
import copy
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ForkDecision:
    """Whether the agent should fork and into which tasks."""

    should_fork: bool = False
    tasks: list[dict[str, Any]] = field(default_factory=list)
    reason: str = ""


@dataclass
class MergeResult:
    """Result of merging forked agent outputs."""

    merged_code_changes: dict[str, Any] = field(default_factory=dict)
    conflicts: list[str] = field(default_factory=list)
    fork_count: int = 0

    @property
    def has_conflicts(self) -> bool:
        return len(self.conflicts) > 0


class AgentForker:
    """Detects divergent objectives and forks agent tasks.

    Heuristic: when the developer is asked to both fix build errors
    AND implement new features (GDD), split into two sub-tasks —
    one focused on fixes, one on features.

    Usage::

        forker = AgentForker()
        decision = forker.detect_divergent_goals(input_data)
        if decision.should_fork:
            tasks = decision.tasks
            results = await asyncio.gather(
                *[agent_clone.execute(iter, task) for agent_clone, task in zip(clones, tasks)]
            )
            merged = forker.merge_results(results)
    """

    # Minimum number of build errors to consider "fix task" worth forking
    MIN_ERRORS_FOR_FORK = 2
    # Minimum GDD length for "feature task" to be worth forking
    MIN_GDD_LENGTH = 50

    def detect_divergent_goals(
        self, input_data: dict[str, Any],
    ) -> ForkDecision:
        """Analyze input_data and decide if forking is beneficial.

        Forks when both conditions are met:
        1. There are build errors or known bugs to fix
        2. There is a substantial GDD update or new feature request
        """
        build_errors = input_data.get("last_critic_feedback", "") or ""
        known_bugs = input_data.get("known_bugs", []) or []
        gdd_update = input_data.get("gdd_update", "") or ""
        roadmap_task = input_data.get("roadmap_task", "") or ""

        # Coerce dicts to strings to avoid AttributeError on .strip()
        if isinstance(build_errors, dict):
            import json as _json
            build_errors = _json.dumps(build_errors, default=str)
        if isinstance(gdd_update, dict):
            import json as _json
            gdd_update = _json.dumps(gdd_update, default=str)
        if isinstance(roadmap_task, dict):
            import json as _json
            roadmap_task = _json.dumps(roadmap_task, default=str)

        has_fixes = (
            bool(str(build_errors).strip())
            or len(known_bugs) >= self.MIN_ERRORS_FOR_FORK
        )
        has_features = (
            len(str(gdd_update)) >= self.MIN_GDD_LENGTH
            or len(str(roadmap_task)) >= self.MIN_GDD_LENGTH
        )

        if has_fixes and has_features:
            tasks = self.fork_tasks(input_data)
            return ForkDecision(
                should_fork=True,
                tasks=tasks,
                reason=f"Divergent goals: {len(known_bugs)} bugs + GDD ({len(gdd_update)} chars)",
            )

        return ForkDecision(should_fork=False)

    def fork_tasks(
        self, input_data: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Split input_data into fix-focused and feature-focused sub-tasks."""
        # Task 1: Fix bugs and address critic feedback
        fix_task = copy.deepcopy(input_data)
        fix_task["gdd_update"] = ""  # Don't distract with new features
        fix_task["roadmap_task"] = ""
        fix_task["_fork_role"] = "fix"

        # Task 2: Implement new features from GDD
        feature_task = copy.deepcopy(input_data)
        feature_task["known_bugs"] = []  # Don't distract with bugs
        feature_task["last_critic_feedback"] = ""
        feature_task["_fork_role"] = "feature"

        return [fix_task, feature_task]

    def merge_results(
        self, results: list[Any],
    ) -> MergeResult:
        """Merge code changes from multiple forked agent results.

        If two forks modify the same file, the fix-fork wins
        (because correctness > features).
        """
        if not results:
            return MergeResult()

        merged_files: dict[str, dict[str, Any]] = {}
        conflicts: list[str] = []

        for result in results:
            metadata = getattr(result, "metadata", {}) or {}
            code_changes = metadata.get("code_changes", {})
            fork_role = metadata.get("_fork_role", "unknown")

            for file_entry in code_changes.get("files", []):
                file_path = file_entry.get("path", "")
                if not file_path:
                    continue

                if file_path in merged_files:
                    existing_role = merged_files[file_path].get(
                        "_fork_role", "unknown",
                    )
                    conflicts.append(
                        f"{file_path}: conflict between {existing_role} and {fork_role}",
                    )
                    # Fix-fork wins over feature-fork
                    if fork_role == "fix":
                        merged_files[file_path] = {**file_entry, "_fork_role": fork_role}
                else:
                    merged_files[file_path] = {**file_entry, "_fork_role": fork_role}

        # Build final merged code_changes structure
        clean_files = []
        for file_data in merged_files.values():
            clean = {k: v for k, v in file_data.items() if not k.startswith("_")}
            clean_files.append(clean)

        return MergeResult(
            merged_code_changes={
                "summary": f"Merged {len(results)} fork(s), {len(conflicts)} conflict(s)",
                "files": clean_files,
            },
            conflicts=conflicts,
            fork_count=len(results),
        )

    async def execute_forks(
        self,
        agent: Any,
        iteration: int,
        tasks: list[dict[str, Any]],
    ) -> MergeResult:
        """Clone the agent, execute tasks in parallel, and merge results."""
        clones = []
        for task in tasks:
            clone = agent.clone()
            clones.append((clone, task))

        results = await asyncio.gather(
            *[clone.execute(iteration, task) for clone, task in clones],
            return_exceptions=True,
        )

        # Filter out exceptions
        valid_results = [r for r in results if not isinstance(r, Exception)]

        if not valid_results:
            logger.warning("All forked tasks failed, returning empty merge")
            return MergeResult()

        for r in results:
            if isinstance(r, Exception):
                logger.warning("Fork failed: %s", r)

        merged = self.merge_results(valid_results)
        logger.info(
            "🔀 Fork merge: %d file(s), %d conflict(s)",
            len(merged.merged_code_changes.get("files", [])),
            len(merged.conflicts),
        )
        return merged
