"""
GORVAX GAME FACTORY — Researcher Agent
Analyses past iterations, market patterns and proposes innovative
feature ideas for the Designer to consider.
"""

from __future__ import annotations

import json
from backend.utils.json_parser import extract_json_from_response
import logging
from typing import Any

from backend.agents.result_types import ResearcherMetadata

from backend.agents.base_agent import BaseAgent, AgentResult
from backend.config import PROMPTS_DIR

logger = logging.getLogger(__name__)


class ResearcherAgent(BaseAgent):
    """
    The Game Researcher agent. Scouts innovation opportunities
    by analysing past experiences, quality trends, and market patterns.

    Runs BEFORE the Designer each iteration to provide inspiration
    and data-driven feature proposals.
    """

    def __init__(self, **kwargs: Any) -> None:
        system_prompt = kwargs.pop("system_prompt", None)
        if not system_prompt:
            prompt_path = PROMPTS_DIR / "researcher.md"
            system_prompt = (
                prompt_path.read_text(encoding="utf-8") if prompt_path.exists() else ""
            )
        super().__init__(
            name="researcher",
            role="Game Researcher",
            system_prompt=system_prompt,
            **kwargs,
        )

    async def execute(
        self,
        iteration: int,
        input_data: dict[str, Any],
    ) -> AgentResult:
        """
        Research feature ideas for the next iteration.

        input_data may contain:
          - current_gdd: dict (current GDD state)
          - quality_history: list[dict] (past quality breakdowns)
          - novelty_score: float (current novelty score)
          - past_experiences: str (formatted context from ExperienceDB)
          - exploration_mode: bool (whether system is exploring)
        """
        context = self.memory.get_context()
        prompt = self._build_prompt(iteration, input_data)

        try:
            response = await self._call_llm(
                prompt=prompt,
                context=context,
                temperature=0.85,  # Creative — high temp
                max_tokens=4096,
            )

            research = self._parse_research(response)

            metadata: ResearcherMetadata = {
                "research_report": research,
                "proposals_count": len(research.get("feature_proposals", [])),
                "market_insights_count": len(research.get("market_insights", [])),
            }
            return AgentResult(
                agent_name=self.name,
                action="research_features",
                output=json.dumps(research, indent=2),
                success=True,
                metadata=metadata,
            )

        except Exception as exc:
            logger.error("Researcher failed: %s", exc)
            return AgentResult(
                agent_name=self.name,
                action="research_features",
                output="",
                success=False,
                error=str(exc),
            )

    def _build_prompt(self, iteration: int, input_data: dict[str, Any]) -> str:
        """Build the research prompt with current context."""
        parts = [
            f"Research feature ideas for iteration #{iteration}.\n"
        ]

        # Current GDD
        gdd = input_data.get("current_gdd", {})
        if gdd:
            gdd_text = json.dumps(gdd, indent=2) if isinstance(gdd, dict) else str(gdd)
            parts.append(f"## Current GDD\n```json\n{gdd_text[:3000]}\n```\n")

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
                    f"balance={q.get('balance', '?')}, "
                    f"novelty={q.get('novelty', '?')}"
                )
            parts.append("")

        # Novelty context
        novelty = input_data.get("novelty_score", -1)
        if novelty >= 0:
            parts.append(f"## Current Novelty Score: {novelty}/100\n")
            if novelty < 30:
                parts.append(
                    "⚠️ Novelty is LOW — the system is generating clones. "
                    "Propose bold, innovative features.\n"
                )

        # Exploration mode
        if input_data.get("exploration_mode"):
            parts.append(
                "🔀 **EXPLORATION MODE ACTIVE** — The system is stagnated. "
                "Propose radical new mechanics, not incremental improvements.\n"
            )

        parts.append(
            "Analyse the above context and propose feature ideas. "
            "Respond in the specified JSON format."
        )

        return "\n\n".join(parts)

    def _parse_research(self, response: str) -> dict[str, Any]:
        """Extract research report JSON from LLM response."""
        return extract_json_from_response(response, fallback={
            "analysis": response[:500],
            "feature_proposals": [],
            "market_insights": [],
            "anti_patterns": [],
            "recommended_focus": "",
            "error": "Could not parse research report",
        })
