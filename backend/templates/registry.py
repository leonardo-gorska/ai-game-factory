"""
GORVAX GAME FACTORY — Template Registry

Indexes and serves reusable JavaScript templates for common game systems.
The Developer agent receives relevant template suggestions based on GDD
analysis, reducing tokens, errors, and code generation time.

Roadmap v2 Item #3.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ── Template data class ───────────────────────────────────

@dataclass(frozen=True)
class Template:
    """A reusable code template for a game system."""

    system: str            # e.g. "inventory", "combat_turn"
    category: str          # e.g. "game_systems", "ui", "core"
    description: str       # Human-readable one-liner
    code: str              # Full JS source
    filename: str          # Original filename

    def to_dict(self) -> dict[str, Any]:
        return {
            "system": self.system,
            "category": self.category,
            "description": self.description,
            "code": self.code,
            "filename": self.filename,
        }


# ── System keyword mapping ────────────────────────────────
#
# Maps GDD keywords to template system names.  When the GDD
# mentions any of these keywords, the corresponding template
# is considered relevant.

SYSTEM_KEYWORDS: dict[str, list[str]] = {
    "inventory": [
        "inventory", "item", "items", "backpack", "bag", "equipment",
        "equip", "unequip", "stack", "weight",
    ],
    "combat_turn": [
        "turn-based", "turn based", "turnos", "initiative", "combate por turnos",
        "tactical combat", "rpg combat",
    ],
    "combat_realtime": [
        "real-time combat", "realtime combat", "action combat",
        "hitbox", "cooldown", "combo", "hack and slash",
    ],
    "shop": [
        "shop", "store", "loja", "buy", "sell", "merchant",
        "vendor", "pricing", "trade",
    ],
    "loot_table": [
        "loot", "drop", "rarity", "legendary", "epic",
        "drop rate", "treasure", "reward table",
    ],
    "progression": [
        "xp", "experience", "level", "leveling", "skill point",
        "prestige", "stat growth", "progression",
    ],
    "quest_system": [
        "quest", "mission", "objective", "quest log", "journal",
        "quest chain", "side quest", "daily quest",
    ],
    "save_load": [
        "save", "load", "save game", "save slot", "auto-save",
        "autosave", "checkpoint", "persistence",
    ],
    "hud": [
        "hud", "heads-up", "health bar", "hp bar", "mana bar",
        "status bar", "overlay", "gold display",
    ],
    "dialog_box": [
        "dialog", "dialogue", "conversation", "npc talk",
        "speech bubble", "text box", "branching dialog",
    ],
    "menu_system": [
        "menu", "main menu", "pause menu", "settings menu",
        "options", "title screen",
    ],
    "minimap": [
        "minimap", "mini-map", "radar", "map overlay",
        "fog of war", "world map",
    ],
    "game_loop": [
        "game loop", "update loop", "render loop",
        "requestanimationframe", "delta time", "fixed timestep",
    ],
    "state_machine": [
        "state machine", "fsm", "game state", "finite state",
        "state transition", "game states",
    ],
    "event_bus": [
        "event bus", "event system", "pub/sub", "publish subscribe",
        "event emitter", "observer pattern", "events",
    ],
    "entity_component": [
        "ecs", "entity component", "entity-component",
        "component system", "entity system",
    ],
}

# ── Detection patterns ────────────────────────────────────
#
# Regex patterns to detect whether a system is already
# implemented in existing code files.

DETECTION_PATTERNS: dict[str, list[str]] = {
    "inventory": [r"class\s+Inventory", r"addItem\s*\(", r"removeItem\s*\("],
    "combat_turn": [r"class\s+.*Combat", r"turnOrder", r"executeAction"],
    "combat_realtime": [r"class\s+Hitbox", r"cooldown", r"combo(?:Count|System)"],
    "shop": [r"class\s+Shop", r"buy\s*\(", r"sell\s*\("],
    "loot_table": [r"class\s+Loot", r"lootTable", r"dropRate|RARITY"],
    "progression": [r"class\s+Progression", r"addXp\s*\(", r"levelUp|level_up"],
    "quest_system": [r"class\s+Quest", r"questLog|QuestManager", r"objective"],
    "save_load": [r"class\s+Save", r"localStorage\.setItem", r"autoSave|auto_save"],
    "hud": [r"class\s+HUD", r"drawBar|healthBar|hp.*bar"],
    "dialog_box": [r"class\s+Dialog", r"typewriter|typeSpeed", r"dialogTree"],
    "menu_system": [r"class\s+Menu", r"menuScreen|MenuScreen", r"pause.*menu"],
    "minimap": [r"class\s+Minimap", r"fogOfWar|fog_of_war", r"minimap"],
    "game_loop": [r"class\s+GameLoop", r"requestAnimationFrame", r"fixedStep|deltaTime"],
    "state_machine": [r"class\s+State(?:Machine)?", r"setState\s*\(", r"transition"],
    "event_bus": [r"class\s+EventBus", r"\.emit\s*\(", r"\.on\s*\(.*,.*\)"],
    "entity_component": [r"class\s+Entity", r"addComponent\s*\(", r"class\s+World"],
}

# ── Template descriptions ─────────────────────────────────

TEMPLATE_DESCRIPTIONS: dict[str, str] = {
    "inventory": "Item management system with add/remove, stacking, weight, and equip/unequip slots",
    "combat_turn": "Turn-based combat with initiative, abilities, status effects, and combat log",
    "combat_realtime": "Real-time combat with cooldowns, AABB hitboxes, combos, and i-frames",
    "shop": "Shop system with dynamic pricing, buy/sell, stock limits, and discount events",
    "loot_table": "Weighted loot drops with rarity tiers, pity system, and level scaling",
    "progression": "XP and leveling system with stat growth, skill points, and prestige",
    "quest_system": "Quest tracker with multi-objectives, chains, rewards, and daily quests",
    "save_load": "Save/load with multiple slots, auto-save, versioning, and integrity checks",
    "hud": "HUD overlay with animated HP/MP bars, gold display, and status effects",
    "dialog_box": "Dialog system with typewriter effect, character portraits, and branching choices",
    "menu_system": "Menu system with screen stack, settings persistence, and transitions",
    "minimap": "Canvas-based minimap with fog of war, entity markers, and zoom",
    "game_loop": "Standard game loop with fixed timestep, delta time, and FPS tracking",
    "state_machine": "Finite state machine with transitions, guards, and state history",
    "event_bus": "Pub/sub event system with priority, wildcards, and async emission",
    "entity_component": "Basic ECS with entities, components, systems, queries, and pooling",
}


# ── Registry ──────────────────────────────────────────────

class TemplateRegistry:
    """Indexes and serves templates for the Developer agent.

    Auto-discovers .js template files from the ``backend/templates/``
    directory tree.  Given a GDD and existing code files, suggests
    templates that are relevant but not yet implemented.
    """

    def __init__(self, templates_dir: Path | str | None = None) -> None:
        if templates_dir is None:
            templates_dir = Path(__file__).parent
        self._templates_dir = Path(templates_dir)
        self._templates: list[Template] = []
        self._load_templates()

    # ── Public API ────────────────────────────────────────

    @property
    def templates(self) -> list[Template]:
        """All registered templates."""
        return list(self._templates)

    @property
    def template_count(self) -> int:
        return len(self._templates)

    def suggest(
        self,
        gdd: dict[str, Any],
        existing_files: dict[str, str],
        max_suggestions: int = 3,
    ) -> list[Template]:
        """Suggest relevant templates based on the GDD and existing code.

        Args:
            gdd: The current Game Design Document (dict).
            existing_files: Map of filename → source code for the game.
            max_suggestions: Maximum number of templates to return.

        Returns:
            List of ``Template`` objects, most relevant first.
        """
        needed_systems = self._analyze_gdd(gdd)
        already_implemented = self._detect_existing(existing_files)
        missing = needed_systems - already_implemented

        suggestions = [t for t in self._templates if t.system in missing]

        if suggestions:
            logger.info(
                "📚 Template suggestions: %d needed, %d already implemented, %d suggested",
                len(needed_systems), len(already_implemented), len(suggestions),
            )

        return suggestions[:max_suggestions]

    def get_template(self, system: str) -> Template | None:
        """Return a specific template by system name."""
        for t in self._templates:
            if t.system == system:
                return t
        return None

    def get_by_category(self, category: str) -> list[Template]:
        """Return all templates in a category."""
        return [t for t in self._templates if t.category == category]

    def get_available_systems(self) -> list[str]:
        """Return list of all available system names."""
        return [t.system for t in self._templates]

    # ── GDD Analysis ──────────────────────────────────────

    def _analyze_gdd(self, gdd: dict[str, Any]) -> set[str]:
        """Extract needed game systems from GDD by keyword matching.

        Flattens the GDD into a single text blob and searches for
        keywords that indicate a particular game system is needed.
        """
        text = self._flatten_to_text(gdd).lower()
        needed: set[str] = set()

        for system, keywords in SYSTEM_KEYWORDS.items():
            for keyword in keywords:
                if keyword.lower() in text:
                    needed.add(system)
                    break

        return needed

    def _detect_existing(self, files: dict[str, str]) -> set[str]:
        """Detect which systems are already implemented in existing code.

        Scans file contents for class/function patterns that indicate
        a system is already present.
        """
        combined_code = "\n".join(files.values())
        detected: set[str] = set()

        for system, patterns in DETECTION_PATTERNS.items():
            match_count = 0
            for pattern in patterns:
                if re.search(pattern, combined_code, re.IGNORECASE):
                    match_count += 1
            # Require at least 2 pattern matches for confidence
            if match_count >= 2:
                detected.add(system)

        return detected

    # ── Internal ──────────────────────────────────────────

    def _load_templates(self) -> None:
        """Discover and load all .js templates from subdirectories."""
        categories = ["game_systems", "ui", "core"]
        for category in categories:
            cat_dir = self._templates_dir / category
            if not cat_dir.is_dir():
                continue
            for js_file in sorted(cat_dir.glob("*.js")):
                system = js_file.stem  # e.g. "inventory"
                try:
                    code = js_file.read_text(encoding="utf-8")
                except Exception as exc:
                    logger.warning("Failed to read template %s: %s", js_file, exc)
                    continue

                description = TEMPLATE_DESCRIPTIONS.get(
                    system,
                    f"{system.replace('_', ' ').title()} template",
                )

                self._templates.append(Template(
                    system=system,
                    category=category,
                    description=description,
                    code=code,
                    filename=js_file.name,
                ))

        logger.info(
            "📚 TemplateRegistry loaded %d templates from %s",
            len(self._templates), self._templates_dir,
        )

    @staticmethod
    def _flatten_to_text(obj: Any, depth: int = 0) -> str:
        """Recursively flatten a dict/list into a single text string."""
        if depth > 10:
            return ""
        if isinstance(obj, str):
            return obj
        if isinstance(obj, dict):
            parts = []
            for k, v in obj.items():
                parts.append(str(k))
                parts.append(TemplateRegistry._flatten_to_text(v, depth + 1))
            return " ".join(parts)
        if isinstance(obj, (list, tuple)):
            return " ".join(
                TemplateRegistry._flatten_to_text(item, depth + 1) for item in obj
            )
        return str(obj)
