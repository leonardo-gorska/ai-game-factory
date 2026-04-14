"""
GORVAX GAME FACTORY — Agent Specialization Router

Dynamically decides which analysis agents to run each iteration based on
the type of code/GDD changes made, going beyond the static file-pattern
approach of ``StaleAgentSkipper``.

Roadmap v2 Item #8.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ── Change-type → agent mapping ───────────────────────────

CHANGE_TYPE_AGENTS: dict[str, list[str]] = {
    "combat":     ["tester", "exploit_detector", "performance"],
    "economy":    ["economy_guardian", "simulation_analyst"],
    "ui":         ["tester", "performance"],
    "core_logic": ["tester", "performance", "exploit_detector"],
    "content":    ["tester", "simulation_analyst"],
    "balance":    ["economy_guardian", "simulation_analyst", "exploit_detector"],
    "rendering":  ["performance", "tester"],
    "audio":      ["tester"],
    "save_load":  ["tester", "exploit_detector"],
}

# Keyword patterns used to classify file changes into change types
_FILE_KEYWORDS: dict[str, list[str]] = {
    "combat":    ["combat", "fight", "battle", "attack", "damage", "weapon",
                  "defense", "health", "hp", "enemy", "boss", "pvp"],
    "economy":   ["economy", "shop", "store", "currency", "gold", "coin",
                  "gem", "price", "loot", "reward", "iap", "monetiz", "trade"],
    "ui":        ["ui", "hud", "menu", "dialog", "button", "screen",
                  "modal", "tooltip", "panel", "overlay", "input"],
    "core_logic":["game", "engine", "loop", "state", "manager", "controller",
                  "system", "entity", "component", "event", "scene", "world"],
    "content":   ["quest", "mission", "story", "npc", "character", "level",
                  "map", "dungeon", "item", "skill", "spell", "ability"],
    "balance":   ["balance", "difficulty", "scaling", "curve", "progression",
                  "xp", "experience", "tier", "rank"],
    "rendering": ["render", "sprite", "animation", "particle", "shader",
                  "canvas", "draw", "graphic", "visual", "effect"],
    "audio":     ["audio", "sound", "music", "sfx"],
    "save_load": ["save", "load", "storage", "persist", "serial"],
}

# GDD section keys → change types
_GDD_SECTION_TYPES: dict[str, str] = {
    "combat": "combat",
    "combat_system": "combat",
    "battle": "combat",
    "economy": "economy",
    "shop": "economy",
    "currency": "economy",
    "rewards": "economy",
    "loot": "economy",
    "ui": "ui",
    "hud": "ui",
    "interface": "ui",
    "progression": "balance",
    "balance": "balance",
    "difficulty": "balance",
    "quests": "content",
    "story": "content",
    "characters": "content",
    "levels": "content",
    "world": "core_logic",
    "systems": "core_logic",
    "mechanics": "core_logic",
    "core": "core_logic",
    "rendering": "rendering",
    "graphics": "rendering",
    "audio": "audio",
}

# Agents that ALWAYS run (baseline)
ALWAYS_RUN = {"tester"}

# All known analysis agents
ALL_AGENTS = {
    "tester", "performance", "economy_guardian",
    "simulation_analyst", "exploit_detector",
}


@dataclass
class RoutingDecision:
    """Which agents should run and why."""

    agents_to_run: set[str] = field(default_factory=set)
    skipped_agents: set[str] = field(default_factory=set)
    change_types_detected: set[str] = field(default_factory=set)
    is_full_sweep: bool = False
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "agents_to_run": sorted(self.agents_to_run),
            "skipped_agents": sorted(self.skipped_agents),
            "change_types": sorted(self.change_types_detected),
            "is_full_sweep": self.is_full_sweep,
            "reason": self.reason,
        }


class AgentRouter:
    """Decides which analysis agents to run based on what changed."""

    def __init__(self, full_sweep_interval: int = 5) -> None:
        self._full_sweep_interval = full_sweep_interval

    def select_agents(
        self,
        changed_files: dict[str, str] | None = None,
        gdd_changes: dict[str, Any] | None = None,
        iteration: int = 1,
    ) -> RoutingDecision:
        """Determine which agents should run this iteration.

        Args:
            changed_files: Files that changed since last iteration
                (filepath → content).
            gdd_changes: GDD sections that were modified (top-level keys).
            iteration: Current pipeline iteration number.

        Returns:
            RoutingDecision with agents_to_run and metadata.
        """
        # Iteration 1 or full sweep interval: run everything
        if iteration <= 1 or iteration % self._full_sweep_interval == 0:
            return RoutingDecision(
                agents_to_run=set(ALL_AGENTS),
                skipped_agents=set(),
                is_full_sweep=True,
                reason=f"Full sweep (iteração {iteration})",
            )

        change_types: set[str] = set()

        # Classify file changes
        if changed_files:
            change_types |= self._classify_file_changes(changed_files)

        # Classify GDD changes
        if gdd_changes:
            change_types |= self._classify_gdd_changes(gdd_changes)

        # If no changes detected, run baseline only
        if not change_types:
            return RoutingDecision(
                agents_to_run=set(ALWAYS_RUN),
                skipped_agents=ALL_AGENTS - ALWAYS_RUN,
                change_types_detected=set(),
                reason="Nenhuma mudança significativa detectada",
            )

        # Map change types to agents
        agents: set[str] = set(ALWAYS_RUN)
        for ct in change_types:
            agents |= set(CHANGE_TYPE_AGENTS.get(ct, []))

        skipped = ALL_AGENTS - agents

        decision = RoutingDecision(
            agents_to_run=agents,
            skipped_agents=skipped,
            change_types_detected=change_types,
            reason=f"Tipos de mudança: {', '.join(sorted(change_types))}",
        )

        logger.info(
            "🧭 Agent Router: %d agentes selecionados, %d pulados | %s",
            len(agents), len(skipped), decision.reason,
        )

        return decision

    # ── Internal classifiers ──────────────────────────────

    @staticmethod
    def _classify_file_changes(
        changed_files: dict[str, str],
    ) -> set[str]:
        """Classify file paths into change types using keyword matching."""
        types: set[str] = set()

        for filepath in changed_files:
            basename = Path(filepath).stem.lower()
            for change_type, keywords in _FILE_KEYWORDS.items():
                if any(kw in basename for kw in keywords):
                    types.add(change_type)

        return types

    @staticmethod
    def _classify_gdd_changes(
        gdd_changes: dict[str, Any],
    ) -> set[str]:
        """Classify GDD section changes into change types."""
        types: set[str] = set()

        for section_key in gdd_changes:
            key_lower = section_key.lower().replace(" ", "_")
            # Direct match
            if key_lower in _GDD_SECTION_TYPES:
                types.add(_GDD_SECTION_TYPES[key_lower])
                continue
            # Partial match
            for pattern, change_type in _GDD_SECTION_TYPES.items():
                if pattern in key_lower or key_lower in pattern:
                    types.add(change_type)
                    break

        return types
