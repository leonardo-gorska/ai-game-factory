"""
GORVAX GAME FACTORY — Critic Agent
Strategic analysis, priority setting, and project management.
"""

from __future__ import annotations

import json
from backend.utils.json_parser import extract_json_from_response
import logging
from typing import Any

from backend.agents.result_types import CriticMetadata

from backend.agents.base_agent import BaseAgent, AgentResult
from backend.config import PROMPTS_DIR

logger = logging.getLogger(__name__)


class CriticAgent(BaseAgent):
    """
    The Game Critic / Project Manager agent.
    Analyzes test results, sets priorities, and guides the next iteration.
    """

    def __init__(self, **kwargs: Any) -> None:
        system_prompt = kwargs.pop("system_prompt", None)
        if not system_prompt:
            system_prompt = (PROMPTS_DIR / "critic.md").read_text(encoding="utf-8")
        super().__init__(
            name="critic",
            role="Game Critic & PM",
            system_prompt=system_prompt,
            **kwargs,
        )

    async def execute(
        self,
        iteration: int,
        input_data: dict[str, Any],
    ) -> AgentResult:
        """
        Analyze results and produce guidance for the next iteration.

        input_data should contain:
          - test_report: dict (from Tester agent)
          - gdd_update: dict (current GDD state)
          - iteration_history: list[dict] (recent iteration summaries)
        """
        context = self.memory.get_context()
        prompt = self._build_prompt(iteration, input_data)

        try:
            response = await self._call_llm(
                prompt=prompt,
                context=context,
                temperature=0.6,
                max_tokens=4096,
            )

            feedback = self._parse_feedback(response)

            metadata: CriticMetadata = {"feedback": feedback}
            return AgentResult(
                agent_name=self.name,
                action="analyze_and_plan",
                output=json.dumps(feedback, indent=2),
                success=True,
                metadata=metadata,
            )

        except Exception as exc:
            logger.error("Critic failed: %s", exc)
            return AgentResult(
                agent_name=self.name,
                action="analyze_and_plan",
                output="",
                success=False,
                error=str(exc),
            )

    def _build_prompt(self, iteration: int, input_data: dict[str, Any]) -> str:
        parts = [f"Analyze the results of iteration #{iteration} and plan the next steps.\n"]

        # Test report
        test_report = input_data.get("test_report", {})
        if test_report:
            report_text = (
                json.dumps(test_report, indent=2)
                if isinstance(test_report, dict)
                else str(test_report)
            )
            parts.append(f"## Test Report\n```json\n{report_text[:3000]}\n```\n")

        # Quality breakdown (from Quality Engine)
        quality = input_data.get("quality_breakdown", {})
        if isinstance(quality, dict) and quality:
            parts.append("## Quality Engine Breakdown")
            parts.append(f"- **Composite Score**: {quality.get('composite', 0):.1f}/100")
            parts.append(f"- Fun: {quality.get('fun', 0):.0f}")
            parts.append(f"- Stability: {quality.get('stability', 0):.0f}")
            parts.append(f"- Performance: {quality.get('performance', 0):.0f}")
            parts.append(f"- Balance: {quality.get('balance', 0):.0f}")
            parts.append(f"- Novelty: {quality.get('novelty', 0):.0f}")
            parts.append(f"- Regression Penalty: -{quality.get('regression_penalty', 0):.0f}\n")

        # Diff risk analysis
        diff_risk = input_data.get("diff_risk", {})
        if isinstance(diff_risk, dict) and diff_risk:
            parts.append("## Diff Risk Analysis")
            parts.append(f"- Risk Level: **{diff_risk.get('risk_level', 'unknown')}**")
            parts.append(f"- Risk Score: {diff_risk.get('risk_score', 0):.0f}/100")
            parts.append(f"- Lines changed: +{diff_risk.get('lines_added', 0)}/-{diff_risk.get('lines_removed', 0)}")
            crit = diff_risk.get("critical_files_touched", [])
            if crit:
                parts.append(f"- Critical files touched: {', '.join(crit)}")
            risky = diff_risk.get("risky_patterns_found", [])
            if risky:
                parts.append(f"- ⚠️ Risky patterns: {', '.join(risky[:5])}")
            parts.append("")

        # Simulation summary
        sim = input_data.get("simulation_summary", {})
        if isinstance(sim, dict) and sim:
            parts.append("## Simulation Summary")
            parts.append(f"- Avg level: {sim.get('avg_level', 0):.1f}")
            parts.append(f"- Crash rate: {sim.get('crash_rate', 0):.1%}")
            parts.append(f"- Economy inflation: {sim.get('economy_inflation', 0):.4f}")
            parts.append(f"- Progression slope: {sim.get('progression_slope', 0):.2f} levels/hr\n")

        # Cost stats
        cost = input_data.get("cost_stats", {})
        if isinstance(cost, dict) and cost:
            parts.append("## Cost Report")
            parts.append(f"- Total spent: ${cost.get('total_cost_usd', 0):.4f}")
            parts.append(f"- Budget remaining: ${cost.get('budget_remaining_usd', 0):.2f}")
            parts.append(f"- Budget usage: {cost.get('budget_usage_pct', 0):.0f}%\n")

        # Current GDD
        gdd = input_data.get("gdd_update", {})
        if gdd:
            gdd_text = json.dumps(gdd, indent=2) if isinstance(gdd, dict) else str(gdd)
            parts.append(f"## Current GDD\n```json\n{gdd_text[:2000]}\n```\n")

        # P8: Implementation visibility — what files exist and what developer did
        impl_files = input_data.get("implemented_files", [])
        if impl_files:
            parts.append("## Implemented Files")
            parts.append(f"Files in game/src/: {', '.join(str(f) for f in impl_files[:30])}\n")

        dev_summary = input_data.get("developer_summary", "")
        if dev_summary:
            parts.append(f"## Developer Summary\n{str(dev_summary)[:1500]}\n")

        build_out = input_data.get("build_output", "")
        if build_out and build_out != "Build OK":
            parts.append(f"## Build Issues\n```\n{str(build_out)[:1000]}\n```\n")

        # v3 Item #13: GDD Drift Alerts
        drift_alerts = input_data.get("gdd_drift_alerts", [])
        if drift_alerts:
            parts.append("## ⚠️ GDD Drift Alerts")
            for alert in drift_alerts[:5]:
                if isinstance(alert, dict):
                    parts.append(f"- **{alert.get('severity', 'info').upper()}**: {alert.get('message', '')}")
                else:
                    parts.append(f"- {alert}")
            parts.append("")

        gdd_evolution = input_data.get("gdd_evolution_summary", "")
        if gdd_evolution:
            parts.append(gdd_evolution)
            parts.append("")

        # Iteration history
        history = input_data.get("iteration_history", [])
        if history:
            history_text = []
            for h in history[-5:]:
                if isinstance(h, dict):
                    history_text.append(
                        f"- Iter {h.get('iteration_number', '?')}: "
                        f"Score {h.get('score', '?')}/100 — {h.get('status', 'unknown')}"
                    )
                else:
                    history_text.append(f"- {h}")
            parts.append(f"## Recent Iteration History\n{''.join(history_text)}\n")

        parts.append(
            f"This is iteration {iteration}. "
            "Based on the quality breakdown, diff risk, simulation data, and cost report, "
            "provide your strategic analysis. Focus on which quality dimensions need "
            "the most improvement and whether the current approach is cost-effective. "
            "Give specific instructions for the Designer in the specified JSON format."
        )

        return "\n\n".join(parts)

    def _parse_feedback(self, response: str) -> dict[str, Any]:
        """Extract feedback JSON from the LLM response."""
        return extract_json_from_response(response, fallback={
            "analysis": response[:500],
            "priorities": [],
            "designer_instructions": "Continue improving the game based on previous feedback.",
            "mood": "cautious",
        })
