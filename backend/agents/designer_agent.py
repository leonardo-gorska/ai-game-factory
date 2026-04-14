"""
GORVAX GAME FACTORY — Designer Agent
Creates and iterates on the Game Design Document (GDD).
"""

from __future__ import annotations

import json
from backend.utils.json_parser import extract_json_from_response
import logging
from typing import Any

from backend.agents.result_types import DesignerMetadata

from backend.agents.base_agent import BaseAgent, AgentResult
from backend.config import PROMPTS_DIR, load_project_config

logger = logging.getLogger(__name__)


class DesignerAgent(BaseAgent):
    """
    The Game Designer agent. Creates and evolves the GDD
    based on critic feedback and testing results.
    """

    def __init__(self, **kwargs: Any) -> None:
        system_prompt = kwargs.pop("system_prompt", None)
        if not system_prompt:
            system_prompt = (PROMPTS_DIR / "designer.md").read_text(encoding="utf-8")
        super().__init__(
            name="designer",
            role="Game Designer",
            system_prompt=system_prompt,
            **kwargs,
        )
        self._current_gdd: dict[str, Any] = {}

    @property
    def current_gdd(self) -> dict[str, Any]:
        return self._current_gdd

    async def execute(
        self,
        iteration: int,
        input_data: dict[str, Any],
    ) -> AgentResult:
        """
        Generate or update the Game Design Document.

        input_data may contain:
          - critic_feedback: str (from Critic agent)
          - test_report: dict (from Tester agent)
          - current_gdd: dict (current GDD state)
        """
        context = self.memory.get_context()

        # Build the prompt based on iteration
        if iteration == 1:
            prompt = self._build_initial_prompt()
        else:
            prompt = self._build_iteration_prompt(input_data)

        try:
            response = await self._call_llm(
                prompt=prompt,
                context=context,
                temperature=0.8,
                max_tokens=4096,
                json_mode=True,  # Force JSON output for reliable parsing
            )

            # Try to parse JSON from the response
            gdd_update = self._parse_gdd_response(response)
            self._current_gdd = self._merge_gdd(gdd_update)

            metadata: DesignerMetadata = {"gdd_update": gdd_update}
            return AgentResult(
                agent_name=self.name,
                action="update_gdd",
                output=json.dumps(gdd_update, indent=2),
                success=True,
                metadata=metadata,
            )

        except Exception as exc:
            logger.error("Designer failed: %s", exc)
            return AgentResult(
                agent_name=self.name,
                action="update_gdd",
                output="",
                success=False,
                error=str(exc),
            )

    def _build_initial_prompt(self) -> str:
        game_name = load_project_config().game_name
        return f"""Create the initial Game Design Document for "{game_name}".

This is iteration 1 — design the MINIMUM VIABLE GAME with these core features:

1. **Main Screen**: A simple realm view showing the player's resources (gold, gems, XP)
2. **Hero System**: Start with 1 hero type (Warrior) with basic stats (HP, ATK, DEF, SPD)
3. **Idle System**: Heroes auto-generate gold over time even when player is away
4. **Combat**: Simple auto-combat: hero attacks monster, deal damage based on ATK vs DEF
5. **Progression**: Heroes gain XP from combat, level up to increase stats
6. **First Dungeon**: 1 dungeon with 5 floors, each with a simple monster

Keep it SIMPLE. We'll add depth in later iterations.

Respond with the GDD update in the specified JSON format."""

    def _build_iteration_prompt(self, input_data: dict[str, Any]) -> str:
        parts = ["Based on the following feedback, update the Game Design Document:\n"]

        # v3 Item 15: Inject Goal Setter goals FIRST for maximum influence
        goals_data = input_data.get("goal_setter_goals", {})
        if goals_data:
            goals_list = goals_data.get("goals", [])
            focus = goals_data.get("focus_summary", "")
            if goals_list:
                goal_lines = [f"## 🎯 Goal Setter Objectives"]
                if focus:
                    goal_lines.append(f"**Focus**: {focus}\n")
                for g in goals_list:
                    goal_lines.append(
                        f"- **[P{g.get('priority', '?')}] {g.get('area', '?')}**: "
                        f"{g.get('description', '')} "
                        f"(success: {g.get('success_criteria', 'N/A')})"
                    )
                goal_lines.append("")
                parts.insert(0, "\n".join(goal_lines) + "\n")

        # Inject roadmap context first — this is the most important signal
        if "roadmap_context" in input_data:
            parts.insert(0, f"{input_data['roadmap_context']}\n")

        if "critic_feedback" in input_data:
            parts.append(f"## Critic Feedback\n{input_data['critic_feedback']}\n")

        if "test_report" in input_data:
            report = input_data["test_report"]
            if isinstance(report, dict):
                parts.append(f"## Test Report\nScore: {report.get('score', '?')}/100")
                if "critical_bugs" in report:
                    parts.append(f"Critical bugs: {report['critical_bugs']}")
                if "improvement_suggestions" in report:
                    parts.append(f"Suggestions: {report['improvement_suggestions']}")
            else:
                parts.append(f"## Test Report\n{report}")

        if "designer_instructions" in input_data:
            parts.append(
                f"## PM Instructions\n{input_data['designer_instructions']}"
            )

        parts.append(
            "\nFocus on the NEXT TASK from the roadmap above. "
            "Design changes for ONLY that specific task. "
            "Respond with the GDD update in the specified JSON format."
        )

        return "\n\n".join(parts)

    def _parse_gdd_response(self, response: str) -> dict[str, Any]:
        """Extract JSON from the LLM response."""
        return extract_json_from_response(response, fallback={
            "summary": response[:500],
            "changes": [],
            "raw_response": response,
        })

    def _merge_gdd(self, update: dict[str, Any]) -> dict[str, Any]:
        """Merge a GDD update into the current GDD state."""
        merged = dict(self._current_gdd)

        if "changes" in update:
            existing_changes = merged.get("changes", [])
            existing_changes.extend(update["changes"])
            merged["changes"] = existing_changes

        merged["latest_summary"] = update.get("summary", "")
        merged["latest_update"] = update

        return merged

    def consolidate_gdd(self, gdd: dict[str, Any]) -> dict[str, Any]:
        """Consolidate GDD by archiving old changes (run every 5 iterations).

        Keeps only the last 10 changes active, moving older ones to a
        consolidated_history summary to prevent prompt noise.
        """
        changes = gdd.get("changes", [])
        if len(changes) <= 10:
            return gdd

        # Keep only the last 10 changes
        gdd["changes"] = changes[-10:]

        # Archive old changes as summary
        old_changes = changes[:-10]
        summary_items = [
            (c.get("area", "unknown") + ": " + c.get("description", "")[:80])
            for c in old_changes
            if isinstance(c, dict)
        ]
        gdd.setdefault("consolidated_history", [])
        gdd["consolidated_history"].append({
            "items_consolidated": len(old_changes),
            "summary": summary_items[:20],
        })

        logger.info("GDD consolidated: %d old changes archived", len(old_changes))
        return gdd
