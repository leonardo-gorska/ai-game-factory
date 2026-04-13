"""
GORVAX GAME FACTORY — Simulation Analyst Agent
Interprets Monte Carlo simulation data, exploit reports,
and per-profile metrics into actionable insights.
"""

from __future__ import annotations

import json
from backend.utils.json_parser import extract_json_from_response
import logging
from typing import Any

from backend.agents.result_types import SimulationAnalystMetadata

from backend.agents.base_agent import BaseAgent, AgentResult
from backend.config import PROMPTS_DIR

logger = logging.getLogger(__name__)


class SimulationAnalystAgent(BaseAgent):
    """
    The Simulation Analyst agent. Interprets raw simulation data
    and translates it into actionable recommendations.

    Runs AFTER the Simulator, BEFORE the Tester.
    """

    def __init__(self, **kwargs: Any) -> None:
        system_prompt = kwargs.pop("system_prompt", None)
        if not system_prompt:
            prompt_path = PROMPTS_DIR / "simulation_analyst.md"
            system_prompt = (
                prompt_path.read_text(encoding="utf-8") if prompt_path.exists() else ""
            )
        super().__init__(
            name="simulation_analyst",
            role="Simulation Analyst",
            system_prompt=system_prompt,
            **kwargs,
        )

    async def execute(
        self,
        iteration: int,
        input_data: dict[str, Any],
    ) -> AgentResult:
        """
        Analyse simulation results and produce actionable insights.

        input_data should contain:
          - sim_aggregate: dict (SimulationAggregate.to_quality_metrics() output)
          - exploit_report: dict (ExploitReport.to_dict() output)
          - per_profile_stats: list[dict] (ProfileStats per player type)
          - game_params: dict (extracted game parameters)
        """
        context = self.memory.get_context()
        prompt = self._build_prompt(iteration, input_data)

        try:
            response = await self._call_llm(
                prompt=prompt,
                context=context,
                temperature=0.5,  # Analytical — moderate temp
                max_tokens=1024,  # Reduced from 4096 — analytical output is concise
            )

            analysis = self._parse_analysis(response)

            metadata: SimulationAnalystMetadata = {
                "simulation_analysis": analysis,
                "insights_count": len(analysis.get("insights", [])),
                "action_items_count": len(analysis.get("action_items", [])),
                "risk_warnings_count": len(analysis.get("risk_warnings", [])),
                "economy_status": analysis.get("economy_health", {}).get(
                    "status", "unknown"
                ),
            }
            return AgentResult(
                agent_name=self.name,
                action="analyse_simulation",
                output=json.dumps(analysis, indent=2),
                success=True,
                metadata=metadata,
            )

        except Exception as exc:
            logger.error("Simulation Analyst failed: %s", exc)
            return AgentResult(
                agent_name=self.name,
                action="analyse_simulation",
                output="",
                success=False,
                error=str(exc),
            )

    def _build_prompt(self, iteration: int, input_data: dict[str, Any]) -> str:
        """Build the analysis prompt with simulation data."""
        parts = [
            f"Analyse the simulation data for iteration #{iteration}.\n"
        ]

        # Simulation aggregate
        sim = input_data.get("sim_aggregate", {})
        if sim:
            parts.append("## Simulation Results")
            parts.append(f"```json\n{json.dumps(sim, indent=2, default=str)[:4000]}\n```\n")

        # Exploit report
        exploit = input_data.get("exploit_report", {})
        if exploit:
            exploit_count = exploit.get("exploit_count", 0)
            parts.append(f"## Exploit Report ({exploit_count} exploits found)")
            parts.append(f"```json\n{json.dumps(exploit, indent=2, default=str)[:2000]}\n```\n")

        # Per-profile stats
        profiles = input_data.get("per_profile_stats", [])
        if profiles:
            parts.append("## Per-Profile Stats")
            for p in profiles:
                if isinstance(p, dict):
                    parts.append(
                        f"- **{p.get('profile', '?')}**: "
                        f"avg_level={p.get('avg_level', '?')}, "
                        f"gold/hr={p.get('avg_gold_per_hour', '?')}, "
                        f"deaths={p.get('avg_deaths', '?')}, "
                        f"engagement={p.get('engagement_rate', '?')}"
                    )
            parts.append("")

        parts.append(
            "Analyse the data above and provide insights, action items, and "
            "risk warnings. Respond in the specified JSON format."
        )

        return "\n\n".join(parts)

    def _parse_analysis(self, response: str) -> dict[str, Any]:
        """Extract analysis JSON from LLM response."""
        return extract_json_from_response(response, fallback={
            "summary": response[:500],
            "insights": [],
            "action_items": [],
            "risk_warnings": [],
            "economy_health": {"status": "unknown"},
            "error": "Could not parse simulation analysis",
        })
