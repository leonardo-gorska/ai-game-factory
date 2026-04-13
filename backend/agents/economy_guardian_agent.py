"""
GORVAX GAME FACTORY — Economy Guardian Agent
Monitors game economy health across multiple time horizons,
detects inflation, power creep, and balance issues.
"""

from __future__ import annotations

import json
from backend.utils.json_parser import extract_json_from_response
import logging
from typing import Any

from backend.agents.result_types import EconomyGuardianMetadata

from backend.agents.base_agent import BaseAgent, AgentResult
from backend.config import PROMPTS_DIR

logger = logging.getLogger(__name__)


class EconomyGuardianAgent(BaseAgent):
    """
    The Economy Guardian agent. Specialises in monitoring the game's
    virtual economy for inflation, power creep, and progression issues.

    Runs AFTER the Simulation Analyst to provide deep economy analysis.
    """

    def __init__(self, **kwargs: Any) -> None:
        system_prompt = kwargs.pop("system_prompt", None)
        if not system_prompt:
            prompt_path = PROMPTS_DIR / "economy_guardian.md"
            system_prompt = (
                prompt_path.read_text(encoding="utf-8") if prompt_path.exists() else ""
            )
        super().__init__(
            name="economy_guardian",
            role="Economy Guardian",
            system_prompt=system_prompt,
            **kwargs,
        )

    async def execute(
        self,
        iteration: int,
        input_data: dict[str, Any],
    ) -> AgentResult:
        """
        Analyse economy health across multiple time horizons.

        input_data should contain:
          - sim_aggregate: dict (simulation results)
          - game_params: dict (game economy parameters)
          - quality_breakdown: dict (current quality scores)
          - previous_economy: dict (economy report from previous iteration)
        """
        context = self.memory.get_context()
        prompt = self._build_prompt(iteration, input_data)

        try:
            response = await self._call_llm(
                prompt=prompt,
                context=context,
                temperature=0.4,  # Precise — economy needs accuracy
                max_tokens=1024,  # Reduced from 4096 — analytical output is concise
            )

            report = self._parse_report(response)
            health_score = report.get("economy_health_score", 50)

            metadata: EconomyGuardianMetadata = {
                "economy_report": report,
                "economy_health_score": health_score,
                "warnings_count": len(report.get("warnings", [])),
                "recommendations_count": len(report.get("recommendations", [])),
            }
            return AgentResult(
                agent_name=self.name,
                action="analyse_economy",
                output=json.dumps(report, indent=2),
                success=True,
                metadata=metadata,
            )

        except Exception as exc:
            logger.error("Economy Guardian failed: %s", exc)
            return AgentResult(
                agent_name=self.name,
                action="analyse_economy",
                output="",
                success=False,
                error=str(exc),
                metadata={"economy_health_score": 50},
            )

    def _build_prompt(self, iteration: int, input_data: dict[str, Any]) -> str:
        """Build the economy analysis prompt."""
        parts = [
            f"Analyse the game economy for iteration #{iteration}.\n"
        ]

        # Simulation results (economy-focused)
        sim = input_data.get("sim_aggregate", {})
        if sim:
            parts.append("## Simulation Economy Data")
            economy_keys = [
                "gold_per_hour", "xp_per_hour", "economy_inflation",
                "progression_slope", "avg_gold_earned", "avg_xp_earned",
                "avg_level", "level_variance", "difficulty_curve",
            ]
            economy_data = {k: sim.get(k, "N/A") for k in economy_keys if k in sim}
            if economy_data:
                parts.append(f"```json\n{json.dumps(economy_data, indent=2)}\n```\n")
            else:
                parts.append(f"```json\n{json.dumps(sim, indent=2, default=str)[:3000]}\n```\n")

        # Game parameters
        game_params = input_data.get("game_params", {})
        if game_params:
            parts.append("## Game Economy Parameters")
            parts.append(f"```json\n{json.dumps(game_params, indent=2)[:2000]}\n```\n")

        # Quality breakdown for context
        quality = input_data.get("quality_breakdown", {})
        if quality:
            parts.append(
                f"## Current Quality Scores\n"
                f"- Balance: {quality.get('balance', '?')}/100\n"
                f"- Fun: {quality.get('fun', '?')}/100\n"
                f"- Stability: {quality.get('stability', '?')}/100\n"
            )

        # Previous economy report for trend tracking
        prev = input_data.get("previous_economy", {})
        if prev:
            prev_score = prev.get("economy_health_score", "?")
            parts.append(
                f"## Previous Economy Health Score: {prev_score}/100\n"
            )

        parts.append(
            "Analyse the economy data above across all time horizons. "
            "Respond in the specified JSON format."
        )

        return "\n\n".join(parts)

    def _parse_report(self, response: str) -> dict[str, Any]:
        """Extract economy report JSON from LLM response."""
        return extract_json_from_response(response, fallback={
            "economy_health_score": 50,
            "assessment": response[:500],
            "time_horizons": {},
            "warnings": [],
            "recommendations": [],
            "retention_impact": "",
            "error": "Could not parse economy report",
        })
