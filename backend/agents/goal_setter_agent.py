"""
GORVAX GAME FACTORY — Goal Setter Agent (Roadmap v3 Item #15)
Meta-Agent that analyses pipeline state and generates prioritised
improvement goals for the Designer and Developer agents.

Runs as Step 0 of the iteration pipeline.  Full re-evaluation every
5 iterations; in between, the previous goals are reused unless a
significant score drop is detected.
"""

from __future__ import annotations

import json
from backend.utils.json_parser import extract_json_from_response
import logging
from typing import Any

from backend.agents.base_agent import BaseAgent, AgentResult
from backend.config import PROMPTS_DIR

logger = logging.getLogger(__name__)

# ── Default evaluation interval ────────────────────────
_REEVALUATE_INTERVAL = 5
_SCORE_DROP_THRESHOLD = 15  # pts — triggers immediate re-evaluation


class GoalSetterMetadata(dict):
    """Metadata returned by GoalSetterAgent."""
    # goals_count: int
    # focus_summary: str
    # reused: bool
    pass


class GoalSetterAgent(BaseAgent):
    """
    Meta-Agent that sets explicit improvement goals for each iteration.

    Instead of the pipeline telling agents to "improve the game", the
    GoalSetterAgent analyses quality breakdowns, known bugs, simulator
    data, and economy reports to produce a prioritised list of concrete
    objectives.

    Goals are re-evaluated every ``reevaluate_interval`` iterations,
    or immediately when the quality score drops by more than
    ``score_drop_threshold`` points.
    """

    def __init__(
        self,
        reevaluate_interval: int = _REEVALUATE_INTERVAL,
        score_drop_threshold: float = _SCORE_DROP_THRESHOLD,
        **kwargs: Any,
    ) -> None:
        system_prompt = kwargs.pop("system_prompt", None)
        if not system_prompt:
            prompt_path = PROMPTS_DIR / "goal_setter.md"
            system_prompt = (
                prompt_path.read_text(encoding="utf-8")
                if prompt_path.exists()
                else self._default_system_prompt()
            )
        super().__init__(
            name="goal_setter",
            role="Goal Setter",
            system_prompt=system_prompt,
            **kwargs,
        )
        self.reevaluate_interval = reevaluate_interval
        self.score_drop_threshold = score_drop_threshold
        self._last_goals: dict[str, Any] = {}
        self._last_eval_iteration: int = 0
        self._last_score: float = 0.0

    # ── Public helpers ─────────────────────────────────

    def should_reevaluate(
        self,
        iteration: int,
        current_score: float,
    ) -> bool:
        """Determine whether goals should be regenerated.

        Returns True when:
        - It's the first iteration
        - The reevaluate interval has elapsed
        - The score dropped significantly since last evaluation
        """
        if iteration <= 1 or not self._last_goals:
            return True
        if (iteration - self._last_eval_iteration) >= self.reevaluate_interval:
            return True
        if self._last_score - current_score >= self.score_drop_threshold:
            return True
        return False

    @property
    def last_goals(self) -> dict[str, Any]:
        return self._last_goals

    # ── Agent execution ────────────────────────────────

    async def execute(
        self,
        iteration: int,
        input_data: dict[str, Any],
    ) -> AgentResult:
        """
        Analyse pipeline state and produce prioritised goals.

        input_data may contain:
          - quality_history: list[dict]
          - current_gdd: dict
          - known_bugs: list[str]
          - simulator_stats: dict
          - economy_report: dict
          - confidence_stats: dict
          - current_score: float
        """
        context = self.memory.get_context()
        prompt = self._build_prompt(iteration, input_data)

        try:
            response = await self._call_llm(
                prompt=prompt,
                context=context,
                temperature=0.6,  # Analytical — moderate temp
                max_tokens=4096,
                json_mode=True,
            )

            goals = self._parse_goals(response)
            self._last_goals = goals
            self._last_eval_iteration = iteration
            self._last_score = input_data.get("current_score", 0.0)

            goals_list = goals.get("goals", [])
            metadata: dict[str, Any] = {
                "goals_count": len(goals_list),
                "focus_summary": goals.get("focus_summary", ""),
                "reused": False,
            }
            return AgentResult(
                agent_name=self.name,
                action="set_goals",
                output=json.dumps(goals, indent=2),
                success=True,
                metadata=metadata,
            )

        except Exception as exc:
            logger.error("GoalSetter failed: %s", exc)
            return AgentResult(
                agent_name=self.name,
                action="set_goals",
                output="",
                success=False,
                error=str(exc),
            )

    # ── Prompt building ────────────────────────────────

    def _build_prompt(self, iteration: int, input_data: dict[str, Any]) -> str:
        parts = [
            f"Analyse the current pipeline state at iteration #{iteration} "
            f"and define the TOP 3-5 concrete improvement goals.\n"
        ]

        # Quality history
        quality_history = input_data.get("quality_history", [])
        if quality_history:
            last_3 = quality_history[-3:]
            parts.append("## Recent Quality Scores")
            for i, q in enumerate(last_3):
                parts.append(
                    f"- Iteration {len(quality_history) - len(last_3) + i + 1}: "
                    f"composite={q.get('composite', '?')}, "
                    f"fun={q.get('fun', '?')}, "
                    f"stability={q.get('stability', '?')}, "
                    f"balance={q.get('balance', '?')}, "
                    f"novelty={q.get('novelty', '?')}, "
                    f"retention={q.get('retention', '?')}"
                )
            parts.append("")

        # Current GDD summary
        gdd = input_data.get("current_gdd", {})
        if gdd:
            summary = gdd.get("latest_summary", "")
            if summary:
                parts.append(f"## Current GDD Summary\n{summary[:1000]}\n")

        # Known bugs
        bugs = input_data.get("known_bugs", [])
        if bugs:
            parts.append("## Known Bugs")
            for bug in bugs[:10]:
                parts.append(f"- {bug}")
            parts.append("")

        # Simulator stats
        sim = input_data.get("simulator_stats", {})
        if sim:
            parts.append(
                f"## Simulator Stats\n"
                f"```json\n{json.dumps(sim, indent=2)[:1500]}\n```\n"
            )

        # Economy report
        econ = input_data.get("economy_report", {})
        if econ:
            parts.append(
                f"## Economy Report\n"
                f"```json\n{json.dumps(econ, indent=2)[:1500]}\n```\n"
            )

        # Confidence stats
        conf = input_data.get("confidence_stats", {})
        if conf:
            low_agents = conf.get("low_confidence_agents", [])
            if low_agents:
                names = [a.get("agent", a) if isinstance(a, dict) else str(a) for a in low_agents]
                parts.append(f"## Low Confidence Agents: {', '.join(names)}\n")

        parts.append(
            "Based on the above data, generate 3-5 **concrete, actionable** goals.\n"
            "Each goal should target the WEAKEST dimension or the most critical bug.\n"
            "Prioritise goals by expected impact.\n\n"
            "Respond with JSON:\n"
            "```json\n"
            "{\n"
            '  "goals": [\n'
            "    {\n"
            '      "id": "goal_1",\n'
            '      "priority": 1,\n'
            '      "area": "stability|fun|balance|performance|novelty|retention|bugs",\n'
            '      "description": "Concrete description of what to improve",\n'
            '      "success_criteria": "How to know this goal is achieved"\n'
            "    }\n"
            "  ],\n"
            '  "focus_summary": "One-line summary of the overall focus"\n'
            "}\n"
            "```"
        )

        return "\n\n".join(parts)

    def _parse_goals(self, response: str) -> dict[str, Any]:
        """Extract goals JSON from LLM response."""
        return extract_json_from_response(response, fallback={
            "goals": [],
            "focus_summary": "Could not parse goals",
            "error": "Parse failure",
        })

    @staticmethod
    def _default_system_prompt() -> str:
        return (
            "You are a Goal Setter meta-agent for an autonomous game factory.\n"
            "Your job is to analyse the pipeline's current state — quality scores,\n"
            "known bugs, simulator data, economy health — and produce a prioritised\n"
            "list of concrete improvement goals.\n\n"
            "Focus on the WEAKEST dimensions. Be specific and actionable.\n"
            "Always respond in valid JSON."
        )
