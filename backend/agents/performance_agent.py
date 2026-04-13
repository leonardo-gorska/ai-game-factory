"""
GORVAX GAME FACTORY — Performance Agent (Phase 3)
5th agent: analyzes game code for performance issues including
bundle size, game loops, memory leaks, load time, and rendering.
"""

from __future__ import annotations

import json
from backend.utils.json_parser import extract_json_from_response
import logging
from typing import Any

from backend.agents.result_types import PerformanceMetadata

from backend.agents.base_agent import BaseAgent, AgentResult
from backend.config import PROMPTS_DIR, GAME_DIR

logger = logging.getLogger(__name__)


class PerformanceAgent(BaseAgent):
    """
    The Performance Analyst agent. Evaluates the game's code and
    build output for performance issues and optimization opportunities.

    Analyzes:
    - Bundle size (from build output)
    - Game loop quality (rAF vs setInterval)
    - Memory management (leaks, cleanup)
    - Load time estimation
    - Rendering efficiency
    """

    def __init__(self, **kwargs: Any) -> None:
        system_prompt = kwargs.pop("system_prompt", None)
        if not system_prompt:
            prompt_path = PROMPTS_DIR / "performance.md"
            system_prompt = prompt_path.read_text(encoding="utf-8") if prompt_path.exists() else ""
        super().__init__(
            name="performance",
            role="Performance Analyst",
            system_prompt=system_prompt,
            **kwargs,
        )

    async def execute(
        self,
        iteration: int,
        input_data: dict[str, Any],
    ) -> AgentResult:
        """
        Analyze the current game build for performance issues.

        input_data should contain:
          - game_files: dict[str, str] (current game source files)
          - build_output: str (output from npm run build)
          - build_success: bool
          - gdd_update: dict (current GDD state)
        """
        context = self.memory.get_context()
        prompt = self._build_prompt(iteration, input_data)

        try:
            response = await self._call_llm(
                prompt=prompt,
                context=context,
                temperature=0.4,  # Lower temp for analytical precision
                max_tokens=1024,  # Reduced from 4096 — analytical output is concise
            )

            report = self._parse_report(response)
            perf_score = report.get("performance_score", 50)

            metadata: PerformanceMetadata = {
                "performance_report": report,
                "performance_score": perf_score,
                "optimizations_count": len(report.get("optimizations", [])),
            }
            return AgentResult(
                agent_name=self.name,
                action="analyze_performance",
                output=json.dumps(report, indent=2),
                success=True,
                metadata=metadata,
            )

        except Exception as exc:
            logger.error("Performance Agent failed: %s", exc)
            return AgentResult(
                agent_name=self.name,
                action="analyze_performance",
                output="",
                success=False,
                error=str(exc),
                metadata={"performance_score": 50},  # Neutral on failure
            )

    def _build_prompt(self, iteration: int, input_data: dict[str, Any]) -> str:
        """Build the analysis prompt with game code and build info."""
        parts = [
            f"Analyze the game performance for iteration #{iteration}.\n"
        ]

        # Build output
        build_success = input_data.get("build_success", False)
        build_output = input_data.get("build_output", "")
        parts.append(
            f"## Build Status: {'✅ SUCCESS' if build_success else '❌ FAILED'}"
        )
        if build_output:
            parts.append(f"Build output:\n```\n{build_output[:3000]}\n```\n")

        # GDD context — what the game is supposed to do
        gdd = input_data.get("gdd_update", {})
        if gdd:
            gdd_text = json.dumps(gdd, indent=2) if isinstance(gdd, dict) else str(gdd)
            parts.append(
                f"## Game Design (Context)\n```json\n{gdd_text[:1500]}\n```\n"
            )

        # Game source files — the main code to analyze
        game_files = input_data.get("game_files", {})
        if game_files:
            parts.append("## Game Source Code")
            total_chars = 0
            for path, content in game_files.items():
                if total_chars > 15000:
                    parts.append(f"\n### {path}\n*(truncated — {len(content)} chars)*")
                    continue
                truncated = content[:4000] + "..." if len(content) > 4000 else content
                parts.append(f"\n### {path}\n```javascript\n{truncated}\n```")
                total_chars += len(truncated)
        else:
            # Try to read game files directly
            src_files = self._read_game_files()
            if src_files:
                parts.append("## Game Source Code (from disk)")
                total_chars = 0
                for path, content in src_files.items():
                    if total_chars > 15000:
                        parts.append(f"\n### {path}\n*(truncated)*")
                        continue
                    truncated = content[:4000] + "..." if len(content) > 4000 else content
                    parts.append(f"\n### {path}\n```javascript\n{truncated}\n```")
                    total_chars += len(truncated)

        parts.append(
            "\nAnalyze the code above for performance issues. "
            "Return your findings in the specified JSON format. "
            "Focus on practical issues that affect gameplay."
        )

        return "\n\n".join(parts)

    def _read_game_files(self) -> dict[str, str]:
        """Read game source files from disk as fallback."""
        files: dict[str, str] = {}
        src_dir = GAME_DIR / "src"
        if not src_dir.exists():
            return files

        for ext in ("*.js", "*.ts", "*.jsx", "*.tsx"):
            for file_path in src_dir.rglob(ext):
                try:
                    rel_path = file_path.relative_to(GAME_DIR)
                    files[str(rel_path)] = file_path.read_text(encoding="utf-8")
                except Exception:
                    continue

        return files

    def _parse_report(self, response: str) -> dict[str, Any]:
        """Extract performance report JSON from LLM response."""
        return extract_json_from_response(response, fallback={
            "performance_score": 50,
            "summary": response[:500],
            "optimizations": [],
            "error": "Could not parse performance report",
            "raw_response": response[:1000],
        })
