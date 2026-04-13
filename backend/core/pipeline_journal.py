"""
GORVAX GAME FACTORY — Pipeline Journal (Replay & Debug Mode)

Serializes every step of every iteration so the pipeline can be replayed
offline without spending LLM tokens.  Useful for debugging, A/B comparison,
and understanding pipeline behavior.

Roadmap v3 Item #12.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ── Data Classes ──────────────────────────────────────

@dataclass
class StepEntry:
    """Single step within an iteration."""

    step_name: str
    input_summary: dict[str, Any] = field(default_factory=dict)
    output_summary: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    prompt: str = ""
    response: str = ""
    duration_ms: float = 0.0
    timestamp: float = field(default_factory=time.time)


@dataclass
class IterationEntry:
    """Full snapshot of one pipeline iteration."""

    iteration: int = 0
    steps: list[StepEntry] = field(default_factory=list)
    final_score: float = 0.0
    start_time: float = field(default_factory=time.time)
    end_time: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def duration_ms(self) -> float:
        if self.end_time > 0:
            return (self.end_time - self.start_time) * 1000
        return 0.0

    @property
    def step_count(self) -> int:
        return len(self.steps)

    def to_dict(self) -> dict[str, Any]:
        return {
            "iteration": self.iteration,
            "final_score": self.final_score,
            "duration_ms": round(self.duration_ms, 1),
            "step_count": self.step_count,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "metadata": self.metadata,
            "steps": [asdict(s) for s in self.steps],
        }


class PipelineJournal:
    """Records and replays pipeline iterations.

    Usage::

        journal = PipelineJournal(Path("game_output/journal"))

        journal.start_iteration(1)
        journal.record_step("develop", input_data, output_data)
        journal.record_step("build", input_data, output_data)
        journal.end_iteration(1, final_score=72.0)

        # Later: replay without LLM
        entry = journal.get_iteration(1)
        for step in entry.steps:
            print(step.step_name, step.output_summary)
    """

    def __init__(
        self,
        journal_dir: Path | str | None = None,
        enabled: bool = True,
        max_prompt_chars: int = 5000,
        max_response_chars: int = 5000,
    ) -> None:
        self._enabled = enabled
        self._max_prompt_chars = max_prompt_chars
        self._max_response_chars = max_response_chars

        # Storage
        self._iterations: dict[int, IterationEntry] = {}
        self._current: IterationEntry | None = None

        # Persistence
        self._journal_dir: Path | None = None
        if journal_dir is not None:
            self._journal_dir = Path(journal_dir)
            self._journal_dir.mkdir(parents=True, exist_ok=True)
            self._load_index()

    # ── Properties ────────────────────────────────────

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = value
        logger.info("📓 Journal %s", "enabled" if value else "disabled")

    @property
    def total_iterations(self) -> int:
        return len(self._iterations)

    # ── Recording API ─────────────────────────────────

    def start_iteration(self, iteration: int) -> None:
        """Begin recording a new iteration."""
        if not self._enabled:
            return

        entry = IterationEntry(iteration=iteration)
        self._current = entry
        logger.debug("📓 Journal: started iteration %d", iteration)

    def record_step(
        self,
        step_name: str,
        input_data: dict[str, Any] | None = None,
        output_data: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        prompt: str = "",
        response: str = "",
        duration_ms: float = 0.0,
    ) -> None:
        """Record a single step within the current iteration."""
        if not self._enabled or self._current is None:
            return

        # Summarize input/output to avoid huge payloads
        input_summary = self._summarize(input_data) if input_data else {}
        output_summary = self._summarize(output_data) if output_data else {}

        step = StepEntry(
            step_name=step_name,
            input_summary=input_summary,
            output_summary=output_summary,
            metadata=metadata or {},
            prompt=prompt[:self._max_prompt_chars] if prompt else "",
            response=response[:self._max_response_chars] if response else "",
            duration_ms=duration_ms,
        )
        self._current.steps.append(step)
        logger.debug(
            "📓 Journal: recorded step '%s' (iteration %d)",
            step_name, self._current.iteration,
        )

    def record_llm_call(
        self,
        agent_name: str,
        prompt: str,
        response: str,
        duration_ms: float = 0.0,
    ) -> None:
        """Record an LLM call within the current iteration (called from BaseAgent)."""
        if not self._enabled or self._current is None:
            return

        step = StepEntry(
            step_name=f"llm:{agent_name}",
            prompt=prompt[:self._max_prompt_chars],
            response=response[:self._max_response_chars],
            duration_ms=duration_ms,
            metadata={"type": "llm_call", "agent": agent_name},
        )
        self._current.steps.append(step)

    def end_iteration(
        self,
        iteration: int,
        final_score: float = 0.0,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Finalize the current iteration recording."""
        if not self._enabled or self._current is None:
            return

        self._current.final_score = final_score
        self._current.end_time = time.time()
        if metadata:
            self._current.metadata.update(metadata)

        self._iterations[iteration] = self._current
        self._current = None

        # Persist to disk
        self._save_iteration(iteration)

        logger.info(
            "📓 Journal: iteration %d saved (score=%.1f, steps=%d)",
            iteration, final_score,
            self._iterations[iteration].step_count,
        )

    # ── Query / Replay API ────────────────────────────

    def get_iteration(self, iteration: int) -> IterationEntry | None:
        """Retrieve a recorded iteration."""
        entry = self._iterations.get(iteration)
        if entry is None and self._journal_dir:
            entry = self._load_iteration(iteration)
        return entry

    def replay(self, iteration: int) -> dict[str, Any]:
        """Replay an iteration: return cached outputs without LLM calls.

        Returns a dict mapping step_name → output_summary for each step.
        """
        entry = self.get_iteration(iteration)
        if entry is None:
            return {"error": f"Iteration {iteration} not found in journal"}

        result: dict[str, Any] = {
            "iteration": iteration,
            "final_score": entry.final_score,
            "duration_ms": entry.duration_ms,
            "steps": {},
        }
        for step in entry.steps:
            result["steps"][step.step_name] = {
                "output": step.output_summary,
                "response": step.response,
                "duration_ms": step.duration_ms,
            }
        return result

    def list_iterations(self) -> list[dict[str, Any]]:
        """List all recorded iterations with summary info."""
        result = []
        for iteration, entry in sorted(self._iterations.items()):
            result.append({
                "iteration": iteration,
                "final_score": entry.final_score,
                "step_count": entry.step_count,
                "duration_ms": round(entry.duration_ms, 1),
            })
        return result

    def get_stats(self) -> dict[str, Any]:
        """Get journal statistics."""
        total_steps = sum(e.step_count for e in self._iterations.values())
        return {
            "enabled": self._enabled,
            "total_iterations": len(self._iterations),
            "total_steps": total_steps,
            "has_persistence": self._journal_dir is not None,
        }

    # ── Persistence ───────────────────────────────────

    def _save_iteration(self, iteration: int) -> None:
        """Save an iteration to disk as JSON."""
        if self._journal_dir is None:
            return

        entry = self._iterations.get(iteration)
        if entry is None:
            return

        path = self._journal_dir / f"iteration_{iteration:04d}.json"
        try:
            path.write_text(
                json.dumps(entry.to_dict(), indent=2, default=str),
                encoding="utf-8",
            )
        except Exception as exc:
            logger.warning("📓 Journal save failed: %s", exc)

        # Update index
        self._save_index()

    def _load_iteration(self, iteration: int) -> IterationEntry | None:
        """Load an iteration from disk."""
        if self._journal_dir is None:
            return None

        path = self._journal_dir / f"iteration_{iteration:04d}.json"
        if not path.exists():
            return None

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            steps = [
                StepEntry(**{k: v for k, v in s.items() if k in StepEntry.__dataclass_fields__})
                for s in data.get("steps", [])
            ]
            entry = IterationEntry(
                iteration=data["iteration"],
                steps=steps,
                final_score=data.get("final_score", 0.0),
                start_time=data.get("start_time", 0.0),
                end_time=data.get("end_time", 0.0),
                metadata=data.get("metadata", {}),
            )
            self._iterations[iteration] = entry
            return entry
        except Exception as exc:
            logger.warning("📓 Journal load failed for iteration %d: %s", iteration, exc)
            return None

    def _save_index(self) -> None:
        """Save index of all iterations."""
        if self._journal_dir is None:
            return
        index = {
            "iterations": sorted(self._iterations.keys()),
            "total": len(self._iterations),
        }
        try:
            path = self._journal_dir / "index.json"
            path.write_text(
                json.dumps(index, indent=2),
                encoding="utf-8",
            )
        except Exception as exc:
            logger.warning("📓 Journal index save failed: %s", exc)

    def _load_index(self) -> None:
        """Load index from disk."""
        if self._journal_dir is None:
            return
        path = self._journal_dir / "index.json"
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            # Don't load iterations eagerly — they'll be loaded on demand
            logger.debug(
                "📓 Journal index loaded: %d iterations available",
                data.get("total", 0),
            )
        except Exception as exc:
            logger.warning("📓 Journal index load failed: %s", exc)

    # ── Helpers ───────────────────────────────────────

    @staticmethod
    def _summarize(data: dict[str, Any], max_str_len: int = 500) -> dict[str, Any]:
        """Create a compact summary of a data dict.

        Truncates strings and replaces large nested structures
        with type/length indicators.
        """
        summary: dict[str, Any] = {}
        for key, value in data.items():
            if key.startswith("_"):
                continue  # Skip private keys
            if isinstance(value, str):
                summary[key] = value[:max_str_len] if len(value) > max_str_len else value
            elif isinstance(value, (int, float, bool)):
                summary[key] = value
            elif isinstance(value, list):
                summary[key] = f"[list: {len(value)} items]"
            elif isinstance(value, dict):
                summary[key] = f"[dict: {len(value)} keys]"
            else:
                summary[key] = f"[{type(value).__name__}]"
        return summary
