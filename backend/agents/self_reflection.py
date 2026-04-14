"""
GORVAX GAME FACTORY — Self-Reflection Agent (Roadmap v2 Item 9)

Meta-analysis agent that examines historical pipeline data to identify
patterns, recurring issues, and strategic opportunities. Runs every
N iterations (default 10) and produces actionable meta-insights.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from backend.agents.result_types import SelfReflectionMetadata
from backend.agents.base_agent import BaseAgent, AgentResult
from backend.config import PROMPTS_DIR

logger = logging.getLogger(__name__)


class SelfReflectionAgent(BaseAgent):
    """
    Meta-analysis agent that reflects on the pipeline's own behavior.

    Analyzes historical iterations to detect:
    - Recurring failure patterns (loop detection)
    - Unstable areas that repeatedly regress
    - Score plateaus and suggested interventions
    - Cost efficiency trends
    - Opportunities for architecture changes
    """

    def __init__(self, interval: int = 10, **kwargs: Any) -> None:
        system_prompt = kwargs.pop("system_prompt", None)
        if not system_prompt:
            system_prompt = (PROMPTS_DIR / "self_reflection.md").read_text(
                encoding="utf-8",
            )
        super().__init__(
            name="self_reflection",
            role="Meta-Analysis & Self-Reflection",
            system_prompt=system_prompt,
            **kwargs,
        )
        self._interval = interval

    @property
    def interval(self) -> int:
        """How often (in iterations) this agent should run."""
        return self._interval

    def should_run(self, iteration: int) -> bool:
        """Return True if this agent should run at the given iteration."""
        return iteration > 0 and iteration % self._interval == 0

    async def execute(
        self,
        iteration: int,
        input_data: dict[str, Any],
    ) -> AgentResult:
        """
        Analyze historical pipeline data and produce meta-insights.

        input_data should contain:
          - iteration_history: list[dict] — all past iteration summaries
          - score_history: list[float] — composite scores per iteration
          - cost_history: list[float] — cost per iteration
          - failure_log: list[dict] — recent failures with details
          - current_score: float — latest composite score
          - total_iterations: int — how many iterations ran
        """
        context = self.memory.get_context()
        prompt = self._build_prompt(iteration, input_data)

        try:
            response = await self._call_llm(
                prompt=prompt,
                context=context,
                temperature=0.7,
                max_tokens=4096,
            )

            insights = self._parse_insights(response)

            metadata: SelfReflectionMetadata = {"insights": insights}
            return AgentResult(
                agent_name=self.name,
                action="self_reflect",
                output=json.dumps(insights, indent=2),
                success=True,
                metadata=metadata,
            )

        except Exception as exc:
            logger.error("Self-reflection failed: %s", exc)
            return AgentResult(
                agent_name=self.name,
                action="self_reflect",
                output="",
                success=False,
                error=str(exc),
            )

    def _build_prompt(
        self, iteration: int, input_data: dict[str, Any],
    ) -> str:
        parts = [
            f"Perform a meta-analysis of the pipeline after {iteration} iterations.\n",
        ]

        # Score history
        scores = input_data.get("score_history", [])
        if scores:
            recent = scores[-20:]
            parts.append("## Score History (last 20)")
            parts.append(
                ", ".join(f"#{i+max(0,len(scores)-20)}: {s:.0f}" for i, s in enumerate(recent)),
            )
            if len(scores) >= 5:
                avg_first = sum(scores[:5]) / 5
                avg_last = sum(scores[-5:]) / 5
                trend = avg_last - avg_first
                parts.append(
                    f"Trend: first 5 avg={avg_first:.1f}, last 5 avg={avg_last:.1f}, "
                    f"delta={trend:+.1f}\n",
                )

        # Cost history
        costs = input_data.get("cost_history", [])
        if costs:
            total = sum(costs)
            avg = total / len(costs)
            parts.append("## Cost Stats")
            parts.append(f"Total: ${total:.4f}, Avg/iteration: ${avg:.4f}")
            parts.append(f"Last 5: {[f'${c:.4f}' for c in costs[-5:]]}\n")

        # Failure log
        failures = input_data.get("failure_log", [])
        if failures:
            parts.append("## Recent Failures")
            for f in failures[-10:]:
                parts.append(
                    f"- Iter #{f.get('iteration', '?')}: "
                    f"{f.get('agent', 'unknown')} — {str(f.get('error', ''))[:200]}",
                )
            parts.append("")

        # Iteration history — condensed
        history = input_data.get("iteration_history", [])
        if history:
            parts.append("## Iteration Summary (last 15)")
            for h in history[-15:]:
                parts.append(
                    f"- #{h.get('iteration_number', '?')}: "
                    f"score={h.get('score', '?')}/100, "
                    f"status={h.get('status', '?')}",
                )
            parts.append("")

        # Current state
        current_score = input_data.get("current_score", 0)
        parts.append(f"## Current State")
        parts.append(f"- Current score: {current_score:.0f}/100")
        parts.append(f"- Total iterations: {input_data.get('total_iterations', iteration)}")
        parts.append("")

        parts.append(
            "Based on this data, identify:\n"
            "1. **Loop patterns**: Score oscillating in a range? Same failures repeating?\n"
            "2. **Unstable areas**: Components that keep regressing after improvements.\n"
            "3. **Plateau detection**: Is the score stuck? What intervention might help?\n"
            "4. **Cost efficiency**: Are we spending too much per score point gained?\n"
            "5. **Opportunities**: Architecture changes, agent config tweaks, or focus shifts.\n\n"
            "Respond in the specified JSON format."
        )

        return "\n\n".join(parts)

    def _parse_insights(self, response: str) -> dict[str, Any]:
        """Extract insights JSON from the LLM response."""
        from backend.utils.json_parser import extract_json_from_response

        return extract_json_from_response(response, fallback={
            "patterns": [],
            "unstable_areas": [],
            "plateau_detected": False,
            "recommendations": [],
            "risk_level": "medium",
            "summary": response[:500],
        })
