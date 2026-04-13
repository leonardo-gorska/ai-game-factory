"""
GORVAX GAME FACTORY — Memory Curator Agent
Periodically reviews and consolidates the team's collective
memory (VectorStore/ExperienceDB), generating meta-insights.
"""

from __future__ import annotations

import json
from backend.utils.json_parser import extract_json_from_response
import logging
from typing import Any

from backend.agents.result_types import MemoryCuratorMetadata

from backend.agents.base_agent import BaseAgent, AgentResult
from backend.config import PROMPTS_DIR

logger = logging.getLogger(__name__)


class MemoryCuratorAgent(BaseAgent):
    """
    The Memory Curator agent. Periodically reviews the ExperienceDB,
    consolidates redundant entries, and generates meta-insights.

    Runs at the END of the iteration loop, every N iterations (default: 5).
    """

    DEFAULT_INTERVAL = 5  # Run every N iterations

    def __init__(self, *, interval: int = DEFAULT_INTERVAL, **kwargs: Any) -> None:
        system_prompt = kwargs.pop("system_prompt", None)
        if not system_prompt:
            prompt_path = PROMPTS_DIR / "memory_curator.md"
            system_prompt = (
                prompt_path.read_text(encoding="utf-8") if prompt_path.exists() else ""
            )
        super().__init__(
            name="memory_curator",
            role="Memory Curator",
            system_prompt=system_prompt,
            **kwargs,
        )
        self.interval = interval

    def should_run(self, iteration: int) -> bool:
        """Check if the curator should run this iteration."""
        return iteration > 0 and iteration % self.interval == 0

    async def execute(
        self,
        iteration: int,
        input_data: dict[str, Any],
    ) -> AgentResult:
        """
        Curate the team's memory, consolidate and generate meta-insights.

        input_data may contain:
          - experience_stats: dict (from ExperienceDB.get_stats())
          - recent_decisions: list[dict] (recent decision entries)
          - recent_failures: list[dict] (recent failure entries)
          - quality_history: list[dict] (quality breakdowns)
        """
        context = self.memory.get_context()
        prompt = self._build_prompt(iteration, input_data)

        try:
            response = await self._call_llm(
                prompt=prompt,
                context=context,
                temperature=0.5,  # Analytical — moderate creativity
                max_tokens=1024,  # Reduced from 4096 — analytical output is concise
            )

            report = self._parse_report(response)

            metadata: MemoryCuratorMetadata = {
                "curation_report": report,
                "winning_patterns": len(report.get("winning_patterns", [])),
                "anti_patterns": len(report.get("anti_patterns", [])),
                "meta_insights": len(report.get("meta_insights", [])),
                "memory_status": report.get("memory_health", {}).get(
                    "status", "unknown"
                ),
            }
            return AgentResult(
                agent_name=self.name,
                action="curate_memory",
                output=json.dumps(report, indent=2),
                success=True,
                metadata=metadata,
            )

        except Exception as exc:
            logger.error("Memory Curator failed: %s", exc)
            return AgentResult(
                agent_name=self.name,
                action="curate_memory",
                output="",
                success=False,
                error=str(exc),
            )

    def _build_prompt(self, iteration: int, input_data: dict[str, Any]) -> str:
        """Build the curation prompt with memory context."""
        parts = [
            f"Curate the team's memory at iteration #{iteration}.\n"
        ]

        # Experience stats
        stats = input_data.get("experience_stats", {})
        if stats:
            parts.append("## Experience Database Stats")
            parts.append(f"```json\n{json.dumps(stats, indent=2, default=str)}\n```\n")

        # Recent decisions
        decisions = input_data.get("recent_decisions", [])
        if decisions:
            parts.append(f"## Recent Decisions ({len(decisions)} entries)")
            for d in decisions[:10]:
                if isinstance(d, dict):
                    parts.append(
                        f"- [{d.get('agent', '?')}] {d.get('action', '?')}: "
                        f"score_delta={d.get('score_delta', '?')}"
                    )
            parts.append("")

        # Recent failures
        failures = input_data.get("recent_failures", [])
        if failures:
            parts.append(f"## Recent Failures ({len(failures)} entries)")
            for f in failures[:5]:
                if isinstance(f, dict):
                    parts.append(
                        f"- {f.get('error', '?')[:100]} "
                        f"(resolution: {f.get('resolution', 'none')[:80]})"
                    )
            parts.append("")

        # Quality history for pattern detection
        quality_history = input_data.get("quality_history", [])
        if quality_history:
            parts.append(f"## Quality Trend ({len(quality_history)} iterations)")
            scores = [q.get("composite", 0) for q in quality_history[-10:]]
            parts.append(f"Last 10 scores: {scores}\n")

        parts.append(
            "Review the data above, identify patterns, and suggest consolidation. "
            "Respond in the specified JSON format."
        )

        return "\n\n".join(parts)

    def _parse_report(self, response: str) -> dict[str, Any]:
        """Extract curation report JSON from LLM response."""
        return extract_json_from_response(response, fallback={
            "summary": response[:500],
            "winning_patterns": [],
            "anti_patterns": [],
            "meta_insights": [],
            "redundant_entries": 0,
            "consolidated_entries": 0,
            "memory_health": {"status": "unknown"},
            "error": "Could not parse curation report",
        })
