"""
GORVAX GAME FACTORY — Stale Agent Skipper

Determines whether an analysis agent can be skipped in the current
iteration because its inputs haven't changed meaningfully.  When an
agent is skipped the pipeline reuses the result from the previous
iteration, saving an LLM call.
"""

from __future__ import annotations

import fnmatch
import logging
from typing import Any

logger = logging.getLogger(__name__)

# ── File-pattern rules per agent ──────────────────────────────
# Keys are lowercase globs matched against file basenames.

AGENT_RELEVANT_PATTERNS: dict[str, list[str]] = {
    "economy_guardian": [
        "*economy*", "*shop*", "*currency*", "*loot*",
        "*reward*", "*store*", "*price*", "*gold*",
        "*coin*", "*gem*", "*monetiz*", "*iap*",
    ],
    "exploit_detector": [
        "*combat*", "*reward*", "*loot*", "*damage*",
        "*pvp*", "*attack*", "*weapon*", "*exploit*",
        "*hack*", "*cheat*",
    ],
}


class StaleAgentSkipper:
    """Centralises the skip-or-run decision for analysis agents."""

    # ── public API ────────────────────────────────────────

    @staticmethod
    def should_skip(
        agent_name: str,
        iteration: int,
        changed_files: dict[str, str] | None = None,
        prev_perf_score: float | None = None,
        curr_perf_score: float | None = None,
    ) -> bool:
        """Return *True* if *agent_name* can safely be skipped.

        Rules
        -----
        * **Iteration 1** — never skip (no previous result to reuse).
        * **Economy Guardian** — skip when no economy-related file changed.
        * **Performance Agent** — skip when performance score didn't drop.
        * **Exploit Detector** — skip when no combat/reward file changed.
        * **Researcher** — skip when ``iteration < 3`` (too early to
          research again after the first run).
        """
        if iteration <= 1:
            return False

        if agent_name == "economy_guardian":
            return not StaleAgentSkipper._has_relevant_changes(
                "economy_guardian", changed_files,
            )

        if agent_name == "performance":
            return StaleAgentSkipper._performance_stable(
                prev_perf_score, curr_perf_score,
            )

        if agent_name == "exploit_detector":
            return not StaleAgentSkipper._has_relevant_changes(
                "exploit_detector", changed_files,
            )

        if agent_name == "researcher":
            return iteration < 3

        return False

    # ── internal helpers ──────────────────────────────────

    @staticmethod
    def _has_relevant_changes(
        agent_name: str,
        changed_files: dict[str, str] | None,
    ) -> bool:
        """Check whether any changed file matches the agent's patterns."""
        if not changed_files:
            return False

        patterns = AGENT_RELEVANT_PATTERNS.get(agent_name, [])
        if not patterns:
            return True  # no patterns ⇒ always relevant

        for fname in changed_files:
            basename = fname.rsplit("/", 1)[-1].rsplit("\\", 1)[-1].lower()
            for pat in patterns:
                if fnmatch.fnmatch(basename, pat):
                    return True
        return False

    @staticmethod
    def _performance_stable(
        prev_score: float | None,
        curr_score: float | None,
    ) -> bool:
        """Return True when performance hasn't degraded."""
        if prev_score is None or curr_score is None:
            return False  # no data ⇒ can't skip
        prev: float = prev_score
        curr: float = curr_score
        return curr >= prev
