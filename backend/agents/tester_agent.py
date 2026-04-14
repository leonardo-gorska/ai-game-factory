"""
GORVAX GAME FACTORY — Tester Agent
Evaluates game builds for quality, bugs, balance, and player experience.
"""

from __future__ import annotations

import json
from backend.utils.json_parser import extract_json_from_response
import logging
from typing import Any

from backend.agents.result_types import TesterMetadata

from backend.agents.base_agent import BaseAgent, AgentResult
from backend.config import PROMPTS_DIR

logger = logging.getLogger(__name__)


class TesterAgent(BaseAgent):
    """
    The Game Tester agent. Analyzes game code and build output
    to evaluate quality across multiple dimensions.
    """

    def __init__(self, **kwargs: Any) -> None:
        system_prompt = kwargs.pop("system_prompt", None)
        if not system_prompt:
            system_prompt = (PROMPTS_DIR / "tester.md").read_text(encoding="utf-8")
        super().__init__(
            name="tester",
            role="Game Tester",
            system_prompt=system_prompt,
            **kwargs,
        )

    async def execute(
        self,
        iteration: int,
        input_data: dict[str, Any],
    ) -> AgentResult:
        """
        Evaluate the current game build.

        input_data should contain:
          - game_files: dict[str, str] (current game source files)
          - build_output: str (output from npm run build)
          - build_success: bool
          - gdd_update: dict (what was supposed to be implemented)
          - code_changes: dict (what the developer actually changed)
        """
        context = self.memory.get_context()
        prompt = self._build_prompt(iteration, input_data)

        try:
            response = await self._call_llm(
                prompt=prompt,
                context=context,
                temperature=0.5,
                max_tokens=1024,  # Reduced from 4096 — analytical output is concise
            )

            test_report = self._parse_test_report(response)

            metadata: TesterMetadata = {
                "test_report": test_report,
                "score": test_report.get("score", 0),
            }
            return AgentResult(
                agent_name=self.name,
                action="test_game",
                output=json.dumps(test_report, indent=2),
                success=True,
                metadata=metadata,
            )

        except Exception as exc:
            logger.error("Tester failed: %s", exc)
            return AgentResult(
                agent_name=self.name,
                action="test_game",
                output="",
                success=False,
                error=str(exc),
            )

    def _build_prompt(self, iteration: int, input_data: dict[str, Any]) -> str:
        parts = [f"Evaluate the game build for iteration #{iteration}.\n"]

        # Build status
        build_success = input_data.get("build_success", False)
        build_output = input_data.get("build_output", "")
        parts.append(f"## Build Status: {'✅ SUCCESS' if build_success else '❌ FAILED'}")
        if build_output:
            parts.append(f"Build output:\n```\n{build_output[:2000]}\n```\n")

        # GDD update (what was supposed to be implemented)
        gdd = input_data.get("gdd_update", {})
        if gdd:
            gdd_text = json.dumps(gdd, indent=2) if isinstance(gdd, dict) else str(gdd)
            parts.append(f"## Design Changes Requested\n```json\n{gdd_text[:2000]}\n```\n")

        # Code changes (what was actually implemented)
        code_changes = input_data.get("code_changes", {})
        if code_changes:
            summary = code_changes.get("summary", "")
            files = code_changes.get("files", [])
            parts.append(f"## Code Changes\nSummary: {summary}")
            parts.append(f"Files modified: {len(files)}\n")

        # Game source files
        game_files = input_data.get("game_files", {})
        if game_files:
            files_text = []
            for path, content in game_files.items():
                truncated = content[:2000] + "..." if len(content) > 2000 else content
                files_text.append(f"### {path}\n```javascript\n{truncated}\n```")
            parts.append(f"## Current Game Source Code\n{''.join(files_text)}\n")

        # Simulation data (from PlaytestSimulator)
        sim_data = input_data.get("simulation_data", {})
        if sim_data:
            parts.append("## Playtest Simulation Data")
            parts.append(f"- Total runs: {sim_data.get('runs', 0)}")
            parts.append(f"- Crash rate: {sim_data.get('crash_rate', 0):.1%}")
            parts.append(f"- Avg final level: {sim_data.get('avg_level', 0):.1f}")
            parts.append(f"- Gold per hour: {sim_data.get('avg_gold_per_hour', 0):.0f}")
            parts.append(f"- Economy inflation: {sim_data.get('economy_inflation', 0):.4f}")
            parts.append(f"- Progression slope: {sim_data.get('progression_slope', 0):.2f} levels/hr")
            parts.append(f"- Engagement rate: {sim_data.get('engagement_rate', 0):.0f}%")
            parts.append(f"- Stuck rate: {sim_data.get('stuck_rate', 0):.1%}\n")

        # v3 Item 10: Automated Regression Suite results
        regression_result = input_data.get("regression_result", None)
        if regression_result and isinstance(regression_result, dict):
            parts.append("## 📋 Regression Test Results")
            parts.append(f"- Passed: {regression_result.get('passed', 0)}")
            parts.append(f"- Failed: {regression_result.get('failed', 0)}")
            parts.append(f"- Status: {'✅ PASSING' if regression_result.get('is_passing') else '❌ REGRESSIONS DETECTED'}")
            errors = regression_result.get("errors", [])
            if errors:
                parts.append("Failures:")
                for err in errors[:10]:
                    parts.append(f"  - {err}")
            parts.append("")

        parts.append(
            "Analyze everything above INCLUDING the simulation data and provide "
            "your test report in the specified JSON format with scores for each "
            "dimension. Pay special attention to economy balance (inflation, "
            "progression slope) and crash/stuck rates from the simulation."
        )

        return "\n\n".join(parts)

    def _parse_test_report(self, response: str) -> dict[str, Any]:
        """Extract test report JSON from the LLM response."""
        return extract_json_from_response(response, fallback={
            "score": 0,
            "summary": response[:500],
            "critical_bugs": ["Could not parse test report"],
            "raw_response": response,
        })
