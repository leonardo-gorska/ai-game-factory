"""
GORVAX GAME FACTORY — Game Roadmap
Tracks development phases and tells the pipeline what to build next.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ── Phased roadmap ──────────────────────────────────────
# Each phase has concrete tasks the LLM should implement one at a time.
PHASES: list[dict[str, Any]] = [
    {
        "id": "phase_0",
        "name": "Foundation",
        "description": "Set up the absolute minimum for a visible, running game",
        "tasks": [
            {
                "id": "p0_asset_loading",
                "name": "Asset loading / procedural textures",
                "description": (
                    "BootScene.preload() MUST generate procedural textures for every sprite the game uses. "
                    "Without this, Phaser shows a green square fallback for every sprite.\n\n"
                    "REQUIRED TEXTURES (minimum):\n"
                    "- 'hero': 32x32 blue square\n"
                    "- 'enemy': 28x28 red square\n"
                    "- 'particle': 4x4 gold square\n\n"
                    "Use this pattern in preload():\n"
                    "```\n"
                    "const gfx = this.add.graphics();\n"
                    "gfx.fillStyle(0x3399ff, 1);\n"
                    "gfx.fillRect(0, 0, 32, 32);\n"
                    "gfx.generateTexture('hero', 32, 32);\n"
                    "gfx.destroy();\n"
                    "```\n"
                    "Repeat for each texture key. Do this BEFORE create() runs."
                ),
                "files_expected": [],
                "imports_in": [],
                "integration_class": "",
                "validation": "BootScene.preload must contain generateTexture calls",
            },
            {
                "id": "p0_game_loop",
                "name": "Game loop (MainScene.update)",
                "description": (
                    "MainScene MUST have an update(time, delta) method. Without this, "
                    "no game systems run — enemies don't spawn, combat doesn't happen, "
                    "and the game is a static screen.\n\n"
                    "The update() method should call update/tick on all active systems:\n"
                    "- this.enemySpawner.spawnTick(time, this.hero)\n"
                    "- this.combatSystem.update(time, delta, this.hero, this.enemySpawner)\n\n"
                    "Systems that don't have update methods yet should get them added."
                ),
                "files_expected": [],
                "imports_in": [],
                "integration_class": "",
                "validation": "MainScene must contain update(time",
            },
            {
                "id": "p0_hud",
                "name": "Basic HUD (gold and level display)",
                "description": (
                    "Add a minimal HUD to MainScene showing:\n"
                    "- Gold count (top-left, gold color)\n"
                    "- Level and XP (below gold)\n\n"
                    "Use this.add.text() in create() and update the text in update().\n"
                    "This gives visual proof the game is running."
                ),
                "files_expected": [],
                "imports_in": [],
                "integration_class": "",
            },
        ],
    },
    {
        "id": "phase_1",
        "name": "Core Combat Loop",
        "description": "Get the hero fighting enemies on screen",
        "tasks": [
            {
                "id": "p1_enemy_spawner",
                "name": "Enemy spawner",
                "description": (
                    "Create an EnemySpawner system that spawns enemies on the right side of the screen "
                    "at random Y positions. Use DUNGEON_ENEMIES from config.js for enemy data. Spawn one enemy every 3 seconds.\n\n"
                    "INTEGRATION REQUIRED: You MUST import EnemySpawner in MainScene.js and call "
                    "`this.enemySpawner = new EnemySpawner(this); this.enemySpawner.start();` inside create(). "
                    "Include MainScene.js in your files list with the updated import and initialization."
                ),
                "files_expected": ["src/systems/EnemySpawner.js"],
                "imports_in": ["src/scenes/MainScene.js"],
                "integration_class": "EnemySpawner",
            },
            {
                "id": "p1_combat",
                "name": "Auto-combat system",
                "description": (
                    "Create a CombatSystem that makes the hero automatically attack the nearest enemy. "
                    "Calculate damage as hero.atk - enemy.def (minimum 1). When enemy HP <= 0, destroy it and award gold + XP. "
                    "Show damage numbers using FeedbackSystem.\n\n"
                    "INTEGRATION REQUIRED: You MUST import CombatSystem in MainScene.js and call "
                    "`this.combatSystem = new CombatSystem(this); this.combatSystem.startCombat();` inside create(). "
                    "Include MainScene.js in your files list with the updated import and initialization."
                ),
                "files_expected": ["src/systems/CombatSystem.js"],
                "imports_in": ["src/scenes/MainScene.js"],
                "integration_class": "CombatSystem",
            },
            {
                "id": "p1_enemy_entity",
                "name": "Enemy entity",
                "description": (
                    "Create an Enemy entity class (like Hero) with a sprite, HP bar, and stats from DUNGEON_ENEMIES config. "
                    "Green circle sprite. Show HP as a small bar above the enemy."
                ),
                "files_expected": ["src/entities/Enemy.js"],
                "imports_in": [],
                "integration_class": "",
            },
            {
                "id": "p1_hero_hp_bar",
                "name": "Hero HP bar",
                "description": (
                    "Add a health bar above the hero sprite showing current HP / max HP. Red bar on dark background. "
                    "Update in real-time during combat. Modify Hero.js to add the HP bar in the constructor."
                ),
                "files_expected": [],
                "imports_in": [],
                "integration_class": "",
            },
        ],
    },
    {
        "id": "phase_2",
        "name": "Progression & UI",
        "description": "Make the player feel progression and have things to do",
        "tasks": [
            {
                "id": "p2_upgrade_ui",
                "name": "Stat upgrade buttons",
                "description": (
                    "Add buttons at the bottom of the screen to spend gold on upgrading hero ATK, DEF, HP. "
                    "Each upgrade costs increasing gold. Show current stat values and upgrade cost.\n\n"
                    "INTEGRATION REQUIRED: You MUST import UpgradeSystem in MainScene.js and call "
                    "`this.upgradeSystem = new UpgradeSystem(this);` inside create(). "
                    "Include MainScene.js in your files list with the updated import and initialization."
                ),
                "files_expected": ["src/systems/UpgradeSystem.js"],
                "imports_in": ["src/scenes/MainScene.js"],
                "integration_class": "UpgradeSystem",
            },
            {
                "id": "p2_difficulty",
                "name": "Enemy difficulty scaling",
                "description": (
                    "Make enemies get stronger as the player levels up. Multiply enemy stats by (1 + hero.level * 0.15). "
                    "Spawn faster enemies at higher levels. Modify EnemySpawner.js or CombatSystem.js."
                ),
                "files_expected": [],
                "imports_in": [],
                "integration_class": "",
            },
            {
                "id": "p2_death_respawn",
                "name": "Death and respawn",
                "description": (
                    "When hero HP reaches 0, show a 'Defeated!' overlay with a respawn button. "
                    "On respawn, restore full HP and keep all gold/XP. Add a brief invulnerability period after respawn. "
                    "Modify CombatSystem.js to detect death and call a respawn method."
                ),
                "files_expected": [],
                "imports_in": [],
                "integration_class": "",
            },
            {
                "id": "p2_save_load",
                "name": "Save/Load system",
                "description": (
                    "Save hero level, gold, gems, stats, and enemies defeated to localStorage every 30 seconds. "
                    "Load on game start. Show 'Game Saved!' feedback text briefly.\n\n"
                    "INTEGRATION REQUIRED: You MUST import SaveSystem in MainScene.js and call "
                    "`this.saveSystem = new SaveSystem(this); this.saveSystem.loadGame();` inside create(). "
                    "Include MainScene.js in your files list with the updated import and initialization."
                ),
                "files_expected": ["src/systems/SaveSystem.js"],
                "imports_in": ["src/scenes/MainScene.js"],
                "integration_class": "SaveSystem",
            },
        ],
    },
    {
        "id": "phase_3",
        "name": "Content & Depth",
        "description": "Add variety and replayability",
        "tasks": [
            {
                "id": "p3_enemy_types",
                "name": "Multiple enemy types",
                "description": (
                    "Use all 5 enemy types from DUNGEON_ENEMIES config with different colors and scales. "
                    "Stronger enemies appear less frequently. Each type has unique visual (color + scale from config). "
                    "Modify EnemySpawner.js to use different enemy types."
                ),
                "files_expected": [],
                "imports_in": [],
                "integration_class": "",
            },
            {
                "id": "p3_floor_system",
                "name": "Dungeon floor progression",
                "description": (
                    "Add a floor counter. After defeating 10 enemies, advance to next floor. "
                    "Each floor increases enemy stats by 20%. Show 'Floor X' at the top of the screen. "
                    "Max 5 floors, then loop with bonus multiplier.\n\n"
                    "INTEGRATION REQUIRED: You MUST import FloorSystem in MainScene.js and call "
                    "`this.floorSystem = new FloorSystem(this);` inside create(). "
                    "Include MainScene.js in your files list with the updated import and initialization."
                ),
                "files_expected": ["src/systems/FloorSystem.js"],
                "imports_in": ["src/scenes/MainScene.js"],
                "integration_class": "FloorSystem",
            },
            {
                "id": "p3_boss",
                "name": "Boss encounter",
                "description": (
                    "On floor 5, spawn a boss enemy (Mini-Boss from config) with 3x stats, larger sprite, and red glow. "
                    "Boss drops 5x gold and gems. Show special 'BOSS!' text when boss appears. "
                    "Modify FloorSystem.js and EnemySpawner.js."
                ),
                "files_expected": [],
                "imports_in": [],
                "integration_class": "",
            },
        ],
    },
    {
        "id": "phase_4",
        "name": "Polish & Monetization",
        "description": "Make it feel premium and add monetization hooks",
        "tasks": [
            {
                "id": "p4_particles",
                "name": "Particle effects",
                "description": (
                    "Add particle bursts on enemy death (gold sparkles), on level up (white stars), and on hit (small red sparks). "
                    "Use Phaser particle emitter with the 'particle' texture. "
                    "Modify CombatSystem.js and FeedbackSystem.js to trigger particles."
                ),
                "files_expected": [],
                "imports_in": [],
                "integration_class": "",
            },
            {
                "id": "p4_offline",
                "name": "Offline gold calculation",
                "description": (
                    "On game load, calculate time since last save. Award OFFLINE_GOLD_PER_SECOND * seconds_away gold "
                    "(capped at MAX_OFFLINE_HOURS). Show a 'Welcome back! You earned X gold while away' overlay. "
                    "Modify SaveSystem.js to calculate offline earnings on loadGame()."
                ),
                "files_expected": [],
                "imports_in": [],
                "integration_class": "",
            },
            {
                "id": "p4_boost",
                "name": "Boost system",
                "description": (
                    "Add a boost button that doubles gold income for BOOST_DURATION. Show countdown timer. "
                    "Use BOOST_DURATION and IAP_BOOST_BENEFIT_MULTIPLIER from config.\n\n"
                    "INTEGRATION REQUIRED: You MUST import BoostSystem in MainScene.js and call "
                    "`this.boostSystem = new BoostSystem(this);` inside create(). "
                    "Include MainScene.js in your files list with the updated import and initialization."
                ),
                "files_expected": ["src/systems/BoostSystem.js"],
                "imports_in": ["src/scenes/MainScene.js"],
                "integration_class": "BoostSystem",
            },
        ],
    },
]


# Skip a task after this many consecutive failed attempts
MAX_CONSECUTIVE_ATTEMPTS = 8

# How many iterations to wait before retrying a deferred task
_DEFER_COOLDOWN_ITERATIONS = 5

# After this many deferrals, permanently skip the task
_MAX_DEFERRALS = 3

# Minimum file size (bytes) to consider a JS file as a real implementation
# (not just a stub with only a constructor)
_MIN_IMPL_BYTES = 200


class GameRoadmap:
    """Tracks which tasks are done and recommends the next task."""

    def __init__(self, game_src_dir: Path) -> None:
        self._game_src = game_src_dir
        self._completed_tasks: set[str] = set()
        self._skipped_tasks: set[str] = set()
        # Deferred tasks: {task_id: {"deferred_at": iteration, "count": N}}
        self._deferred_tasks: dict[str, dict[str, int]] = {}
        # Stall detection: track consecutive attempts at same task
        self._last_task_id: str = ""
        self._consecutive_attempts: int = 0
        # Track iteration for defer cooldown
        self._current_iteration: int = 0
        # Track previous file count to detect accidental deletion
        self._prev_file_count: int = 0

    def set_iteration(self, iteration: int) -> None:
        """Update the current iteration number for defer cooldown tracking."""
        self._current_iteration = iteration

        # Re-activate deferred tasks whose cooldown expired
        reactivated = []
        for task_id, info in list(self._deferred_tasks.items()):
            if iteration - info["deferred_at"] >= _DEFER_COOLDOWN_ITERATIONS:
                if task_id in self._skipped_tasks:
                    self._skipped_tasks.discard(task_id)
                    reactivated.append(task_id)
                    logger.info(
                        "🔄 Roadmap: re-activating deferred task '%s' (attempt #%d)",
                        task_id, info["count"] + 1,
                    )
        for task_id in reactivated:
            del self._deferred_tasks[task_id]

    def scan_progress(self) -> dict[str, Any]:
        """Scan game/src/ to detect which tasks are likely complete."""
        existing_files = set()
        if self._game_src.exists():
            for f in self._game_src.rglob("*.js"):
                rel = f.relative_to(self._game_src.parent).as_posix()
                existing_files.add(rel)

        # Detect accidental file deletion (regression guard)
        current_count = len(existing_files)
        if self._prev_file_count > 0 and current_count < self._prev_file_count - 2:
            logger.warning(
                "⚠️ Roadmap: file count dropped from %d to %d — possible accidental deletion!",
                self._prev_file_count, current_count,
            )
        self._prev_file_count = current_count

        # Read MainScene.js to detect integrated systems
        main_scene = self._game_src / "scenes" / "MainScene.js"
        main_scene_imports: set[str] = set()
        main_scene_content: str = ""
        if main_scene.exists():
            main_scene_content = main_scene.read_text(encoding="utf-8", errors="replace")
            for line in main_scene_content.splitlines():
                if line.strip().startswith("import"):
                    main_scene_imports.add(line.strip())

        completed: list[str] = []
        current_phase = None
        current_task = None

        for phase in PHASES:
            phase_done = True
            for task in phase["tasks"]:
                # Permanently skipped tasks count as "done" for progression
                if task["id"] in self._skipped_tasks and task["id"] not in self._deferred_tasks:
                    completed.append(task["id"])
                    continue

                task_done = True

                # Check if expected files exist AND are real implementations
                for expected in task.get("files_expected", []):
                    if expected not in existing_files:
                        task_done = False
                    else:
                        # Stub detection: file exists but is too small to be real
                        full_path = self._game_src.parent / expected
                        if full_path.exists() and self._is_stub_file(full_path):
                            task_done = False
                            logger.debug(
                                "Roadmap: '%s' exists but is a stub (<=%d bytes or no methods)",
                                expected, _MIN_IMPL_BYTES,
                            )

                # Phase 0 validation checks (special: no files_expected)
                validation = task.get("validation", "")
                if validation and not task.get("files_expected"):
                    task_done = self._check_validation(validation, main_scene_content, existing_files)

                # Check if the system is integrated in MainScene
                # This is the key check: file existing is not enough,
                # the class must actually be imported+used in MainScene
                integration_class = task.get("integration_class", "")
                if integration_class:
                    found_import = any(integration_class in line for line in main_scene_imports)
                    found_usage = integration_class in main_scene_content if main_scene_content else False
                    if not found_import or not found_usage:
                        task_done = False

                if task_done:
                    completed.append(task["id"])
                    self._completed_tasks.add(task["id"])
                else:
                    phase_done = False
                    if current_task is None:
                        current_phase = phase
                        current_task = task

            if not phase_done and current_task:
                break

        return {
            "completed_tasks": completed,
            "total_tasks": sum(len(p["tasks"]) for p in PHASES),
            "current_phase": current_phase,
            "current_task": current_task,
            "existing_files": sorted(existing_files),
            "progress_pct": len(completed) / max(1, sum(len(p["tasks"]) for p in PHASES)) * 100,
            "skipped_tasks": sorted(self._skipped_tasks),
        }

    def get_designer_context(self) -> str:
        """Build context string for the Designer agent."""
        progress = self.scan_progress()
        phase = progress["current_phase"]
        task = progress["current_task"]

        if not phase or not task:
            return "All roadmap tasks are complete. Focus on polish and balance."

        completed = progress["completed_tasks"]
        total = progress["total_tasks"]
        pct = progress["progress_pct"]

        lines = [
            f"## 🗺️ Development Roadmap — {pct:.0f}% Complete ({len(completed)}/{total} tasks)",
            f"",
            f"### Current Phase: {phase['name']}",
            f"{phase['description']}",
            f"",
            f"### 🎯 NEXT TASK: {task['name']}",
            f"{task['description']}",
            f"",
            f"Design your GDD update to ONLY address this specific task.",
            f"Do NOT redesign existing systems that already work.",
        ]

        if completed:
            lines.append(f"\n### ✅ Already Completed ({len(completed)} tasks)")
            for tid in completed:
                tname = self._task_name(tid)
                if tname:
                    lines.append(f"- {tname}")

        return "\n".join(lines)

    def get_developer_context(self) -> str:
        """Build context string for the Developer agent."""
        progress = self.scan_progress()
        phase = progress["current_phase"]
        task = progress["current_task"]

        if not phase or not task:
            return "All roadmap tasks complete. Focus on bug fixes and polish only."

        # Track stall — same task repeating?
        task_id = task["id"]
        if task_id == self._last_task_id:
            self._consecutive_attempts += 1
        else:
            self._last_task_id = task_id
            self._consecutive_attempts = 1

        lines = [
            f"## \ud83c\udfaf YOUR TASK THIS ITERATION: {task['name']}",
            f"",
            f"{task['description']}",
            f"",
        ]

        # Task defer: after MAX_CONSECUTIVE_ATTEMPTS, defer with cooldown instead of permanent skip
        if self._consecutive_attempts >= MAX_CONSECUTIVE_ATTEMPTS:
            defer_count = self._deferred_tasks.get(task_id, {}).get("count", 0) + 1
            if defer_count >= _MAX_DEFERRALS:
                logger.warning(
                    "⏭️ Roadmap: PERMANENTLY SKIPPING task '%s' after %d deferrals",
                    task['name'], defer_count,
                )
                self._skipped_tasks.add(task_id)
                if task_id in self._deferred_tasks:
                    del self._deferred_tasks[task_id]
            else:
                logger.warning(
                    "⏸️ Roadmap: DEFERRING task '%s' (deferral #%d, retry in %d iterations)",
                    task['name'], defer_count, _DEFER_COOLDOWN_ITERATIONS,
                )
                self._skipped_tasks.add(task_id)
                self._deferred_tasks[task_id] = {
                    "deferred_at": self._current_iteration,
                    "count": defer_count,
                }
            self._last_task_id = ""
            self._consecutive_attempts = 0
            # Re-scan to find the NEXT task after defer/skip
            return self.get_developer_context()

        # Stall escalation: after 3+ attempts, diagnose exactly what's missing
        if self._consecutive_attempts >= 3:
            lines.append(f"### \ud83d\udea8 STALL ALERT — Attempt #{self._consecutive_attempts} at this task! (SKIP after {MAX_CONSECUTIVE_ATTEMPTS})")
            lines.append("Previous attempts did NOT complete this task. Here is exactly what is MISSING:")
            lines.append("")
            existing_files = set(progress["existing_files"])
            for expected in task.get("files_expected", []):
                if expected in existing_files:
                    lines.append(f"- \u2705 `{expected}` — FILE EXISTS")
                else:
                    lines.append(f"- \u274c `{expected}` — FILE MISSING (you must create it)")

            integration_class = task.get("integration_class", "")
            if integration_class:
                main_scene = self._game_src / "scenes" / "MainScene.js"
                if main_scene.exists():
                    content = main_scene.read_text(encoding="utf-8", errors="replace")
                    has_import = integration_class in content.split("create")[0] if "create" in content else False
                    has_usage = integration_class in content
                    if has_import:
                        lines.append(f"- \u2705 `{integration_class}` import in MainScene.js — FOUND")
                    else:
                        lines.append(f"- \u274c `{integration_class}` import in MainScene.js — MISSING")
                        lines.append(f"  ADD: `import {{ {integration_class} }} from '../systems/{integration_class}.js';`")
                    if has_usage:
                        lines.append(f"- \u2705 `{integration_class}` used in MainScene.js — FOUND")
                    else:
                        lines.append(f"- \u274c `{integration_class}` used in MainScene.js create() — MISSING")
                        lines.append(f"  ADD: `this.{integration_class[0].lower()}{integration_class[1:]} = new {integration_class}(this);`")
                else:
                    lines.append(f"- \u274c MainScene.js does not exist yet")
            lines.append("")
            lines.append("**FIX ALL items marked \u274c above. Include MainScene.js in your output files.**")
            lines.append("")
            logger.warning(
                "[!] Roadmap stall: task '%s' attempted %d times (skip at %d)",
                task['name'], self._consecutive_attempts, MAX_CONSECUTIVE_ATTEMPTS,
            )

        if task.get("files_expected"):
            lines.append("### Files to Create/Modify:")
            for f in task["files_expected"]:
                lines.append(f"- `{f}`")
            lines.append("")

        # Critical: tell developer which files MUST be in their output
        integration_class = task.get("integration_class", "")
        if integration_class:
            lines.extend([
                "### \u26a1 MANDATORY: MainScene.js Integration",
                f"Your output MUST include `src/scenes/MainScene.js` with:",
                f"1. An import: `import {{ {integration_class} }} from '../systems/{integration_class}.js';`",
                f"2. In create(): `this.{integration_class[0].lower()}{integration_class[1:]} = new {integration_class}(this);`",
                f"",
                f"**The task will NOT be marked complete unless {integration_class} appears in MainScene.js imports AND body.**",
                "",
            ])

        lines.extend([
            "### ⚠️ CRITICAL RULES:",
            "- ONLY create/modify files needed for THIS task",
            "- Do NOT rewrite files that already work from scratch — only add new code",
            "- Do NOT recreate config.js, main.js, or Hero.js",
            "- If you need new constants, ADD them to config.js WITHOUT removing existing ones",
            "- When modifying MainScene.js, keep ALL existing imports and code — only ADD new lines",
            "",
            "### 🎨 TEXTURE RULES (CRITICAL):",
            "- EVERY sprite MUST have its texture loaded in BootScene.preload()",
            "- If no asset files exist, use `this.add.graphics()` + `generateTexture(key, w, h)` to create procedural textures",
            "- NEVER use a texture key in `new Phaser.GameObjects.Sprite(scene, x, y, KEY)` without loading it first",
            "- Missing textures cause Phaser to show a GREEN SQUARE fallback",
            "",
            "### 🔄 GAME LOOP RULES (CRITICAL):",
            "- MainScene MUST have an `update(time, delta)` method",
            "- The update() method must call tick/update on ALL active systems",
            "- Without update(), nothing happens — no spawning, no combat, no game",
            "- Hero.js MUST have an `addXP(amount)` method for level progression",
            "",
            "### 🛡️ SAFE EDITING RULES:",
            "- NEVER remove existing imports from MainScene.js — only ADD new ones",
            "- NEVER delete files that already exist — only modify or create new ones",
            "- ALWAYS include ALL existing code when modifying a file — do not truncate",
            "- When outputting a file, include EVERY line of the original — do NOT shorten or summarize",
        ])

        # v2.3 P2: Detect and report stub files across ALL tasks
        stub_files: list[str] = []
        for phase in PHASES:
            for task in phase["tasks"]:
                for expected in task.get("files_expected", []):
                    full_path = self._game_src.parent / expected
                    if full_path.exists() and self._is_stub_file(full_path):
                        stub_files.append(expected)
        if stub_files:
            lines.append("\n### 🚨 STUB FILES DETECTED (must be filled with real implementation):")
            for sf in stub_files:
                lines.append(f"- ⚠️ `{sf}` — EXISTS but is an EMPTY STUB (only has constructor)")
                lines.append(f"  This file must have real methods to count as implemented.")
            lines.append("")
            lines.append("**If your current task involves any of these files, FILL THEM with real logic.**")
            lines.append("")

        # List existing files as "DO NOT TOUCH"
        existing = progress["existing_files"]
        if existing:
            task_files = set(task.get("files_expected", []) + task.get("imports_in", []))
            protected = [f for f in existing if not any(tf in f for tf in task_files)]
            if protected:
                lines.append(f"\n### \ud83d\udee1\ufe0f Existing Files (DO NOT rewrite from scratch):")
                for f in protected[:15]:
                    lines.append(f"- `{f}` \u2705 working")

        return "\n".join(lines)

    def _task_name(self, task_id: str) -> str | None:
        for phase in PHASES:
            for task in phase["tasks"]:
                if task["id"] == task_id:
                    return task["name"]
        return None

    def _check_validation(
        self,
        validation: str,
        main_scene_content: str,
        existing_files: set[str],
    ) -> bool:
        """Check Phase 0 validation rules against actual file contents."""
        if "BootScene.preload must contain generateTexture" in validation:
            boot_scene = self._game_src / "scenes" / "BootScene.js"
            if not boot_scene.exists():
                return False
            content = boot_scene.read_text(encoding="utf-8", errors="replace")
            if "preload" not in content or "generateTexture" not in content:
                return False
            return True

        if "MainScene must contain update(time" in validation:
            if "update(time" not in main_scene_content:
                return False
            return True

        # Unknown validation rule — pass by default
        return True

    @staticmethod
    def _is_stub_file(path: Path) -> bool:
        """Return True if a JS file is a stub (too small or no methods beyond constructor)."""
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return True
        # Too small to be a real implementation
        if len(content.encode("utf-8")) <= _MIN_IMPL_BYTES:
            return True
        # Count method-like definitions (excluding constructor)
        lines = content.splitlines()
        method_count = 0
        for line in lines:
            stripped = line.strip()
            # Match JS method patterns: foo() { or foo(args) {
            if (
                stripped
                and not stripped.startswith("//")
                and not stripped.startswith("import")
                and not stripped.startswith("export")
                and "(" in stripped
                and "{" in stripped
                and "constructor" not in stripped
                and not stripped.startswith("if")
                and not stripped.startswith("for")
                and not stripped.startswith("while")
            ):
                method_count += 1
        return method_count == 0
