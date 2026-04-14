"""
GORVAX GAME FACTORY — Prompt Optimizer (Roadmap v3 Item #3)

Adaptive Prompt Tuning: registra resultados de cada chamada LLM,
correlaciona configurações (temperatura, prompt variant) com qualidade,
e sugere automaticamente as melhores configurações por agente.

Impacto esperado: ~15% menos iterações desperdiçadas.
"""

from __future__ import annotations

import hashlib
import json
import logging
import random
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.config import ITERATIONS_DIR

logger = logging.getLogger(__name__)

# ── Persistence path ────────────────────────────────────
_TUNING_FILE = ITERATIONS_DIR / "prompt_tuning.json"

# ── Constants ───────────────────────────────────────────
DEFAULT_TEMPERATURE = 0.7
EXPLORATION_RATIO = 0.20       # 20% of suggestions are explorations
TEMPERATURE_STEP = 0.1         # step size for temperature exploration
MIN_TEMPERATURE = 0.1
MAX_TEMPERATURE = 1.5
MIN_RECORDS_FOR_SUGGESTION = 3 # minimum records before making suggestions
TEMPERATURE_BUCKET_SIZE = 0.1  # bucket width for temperature grouping


@dataclass
class PromptRecord:
    """Single record of a prompt call result."""
    agent: str
    prompt_hash: str
    temperature: float
    quality_delta: float
    tokens_used: int
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PromptRecord:
        return cls(
            agent=data["agent"],
            prompt_hash=data["prompt_hash"],
            temperature=data["temperature"],
            quality_delta=data["quality_delta"],
            tokens_used=data["tokens_used"],
            timestamp=data.get("timestamp", ""),
        )


@dataclass
class PromptSuggestion:
    """Suggested configuration for a prompt call."""
    temperature: float = DEFAULT_TEMPERATURE
    variant_id: str = "default"
    is_exploration: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def compute_prompt_hash(prompt_text: str) -> str:
    """Compute a short hash of prompt text for tracking."""
    return hashlib.sha256(prompt_text.encode("utf-8")).hexdigest()[:12]


class PromptOptimizer:
    """
    Adaptive Prompt Tuning engine.

    Records prompt call results and correlates them to find the best
    configuration (temperature, variant) per agent. Uses A/B testing
    to balance exploitation (best known config) with exploration
    (random temperature variations).

    Usage:
        optimizer = PromptOptimizer()
        optimizer.record("developer", "abc123", 0.7, quality_delta=+5.2, tokens_used=1200)
        suggestion = optimizer.suggest_variant("developer")
        best = optimizer.get_best_config("developer")
    """

    MAX_RECORDS_PER_AGENT = 200

    def __init__(self) -> None:
        self._records: dict[str, list[PromptRecord]] = defaultdict(list)
        self._load()

    # ── Record ────────────────────────────────────────────

    def record(
        self,
        agent: str,
        prompt_hash: str,
        temperature: float,
        quality_delta: float,
        tokens_used: int = 0,
    ) -> PromptRecord:
        """
        Record the result of a prompt call.

        Args:
            agent: Agent name (e.g. "developer", "designer").
            prompt_hash: Hash of the prompt template used.
            temperature: LLM temperature used.
            quality_delta: Change in quality score after this call.
            tokens_used: Number of tokens consumed.

        Returns:
            The created PromptRecord.
        """
        rec = PromptRecord(
            agent=agent,
            prompt_hash=prompt_hash,
            temperature=temperature,
            quality_delta=quality_delta,
            tokens_used=tokens_used,
        )
        self._records[agent].append(rec)

        # Enforce cap per agent
        if len(self._records[agent]) > self.MAX_RECORDS_PER_AGENT:
            self._records[agent] = self._records[agent][-self.MAX_RECORDS_PER_AGENT:]

        self._save()

        logger.debug(
            "📊 PromptOptimizer: recorded %s temp=%.2f Δq=%.2f",
            agent, temperature, quality_delta,
        )
        return rec

    # ── Query ─────────────────────────────────────────────

    def get_best_config(self, agent: str) -> PromptSuggestion:
        """
        Get the best known configuration for an agent.

        Analyzes historical records to find the temperature bucket
        with the highest average quality_delta.

        Returns:
            PromptSuggestion with the best temperature found,
            or defaults if not enough data.
        """
        records = self._records.get(agent, [])
        if len(records) < MIN_RECORDS_FOR_SUGGESTION:
            return PromptSuggestion()

        # Group by temperature bucket
        buckets: dict[float, list[float]] = defaultdict(list)
        for rec in records:
            bucket = round(
                round(rec.temperature / TEMPERATURE_BUCKET_SIZE) * TEMPERATURE_BUCKET_SIZE,
                2,
            )
            buckets[bucket].append(rec.quality_delta)

        # Find bucket with highest average quality_delta
        best_bucket = DEFAULT_TEMPERATURE
        best_avg = float("-inf")
        for bucket, deltas in buckets.items():
            avg = sum(deltas) / len(deltas)
            if avg > best_avg:
                best_avg = avg
                best_bucket = bucket

        return PromptSuggestion(
            temperature=best_bucket,
            variant_id="optimized",
            is_exploration=False,
        )

    def suggest_variant(self, agent: str) -> PromptSuggestion:
        """
        Suggest a configuration using A/B test logic.

        80% of the time: use the best known config (exploitation).
        20% of the time: try a random temperature variation (exploration).

        Returns:
            PromptSuggestion with the suggested configuration.
        """
        best = self.get_best_config(agent)

        # Exploration: random temperature variation
        if random.random() < EXPLORATION_RATIO:
            delta = random.choice([-TEMPERATURE_STEP, TEMPERATURE_STEP])
            new_temp = round(
                max(MIN_TEMPERATURE, min(MAX_TEMPERATURE, best.temperature + delta)),
                2,
            )
            return PromptSuggestion(
                temperature=new_temp,
                variant_id="exploration",
                is_exploration=True,
            )

        return best

    def get_stats(self, agent: str | None = None) -> dict[str, Any]:
        """
        Get performance statistics.

        Args:
            agent: If provided, stats for that agent only.
                   If None, stats for all agents.

        Returns:
            Dict with record counts, avg quality_delta, best temperature, etc.
        """
        if agent:
            return self._agent_stats(agent)

        all_stats: dict[str, Any] = {
            "total_records": sum(len(r) for r in self._records.values()),
            "agents": {},
        }
        for agent_name in sorted(self._records.keys()):
            all_stats["agents"][agent_name] = self._agent_stats(agent_name)
        return all_stats

    def _agent_stats(self, agent: str) -> dict[str, Any]:
        """Compute stats for a single agent."""
        records = self._records.get(agent, [])
        if not records:
            return {
                "total_records": 0,
                "avg_quality_delta": 0.0,
                "best_temperature": DEFAULT_TEMPERATURE,
            }

        deltas = [r.quality_delta for r in records]
        best = self.get_best_config(agent)
        tokens = [r.tokens_used for r in records]

        return {
            "total_records": len(records),
            "avg_quality_delta": round(sum(deltas) / len(deltas), 3),
            "best_temperature": best.temperature,
            "avg_tokens": round(sum(tokens) / len(tokens)) if tokens else 0,
            "unique_prompts": len(set(r.prompt_hash for r in records)),
        }

    # ── Persistence ───────────────────────────────────────

    def _save(self) -> None:
        """Persist records to JSON file."""
        try:
            data: dict[str, list[dict[str, Any]]] = {}
            for agent, records in self._records.items():
                data[agent] = [r.to_dict() for r in records]
            _TUNING_FILE.write_text(
                json.dumps(data, indent=2, default=str),
                encoding="utf-8",
            )
        except Exception as exc:
            logger.warning("Failed to persist prompt tuning data: %s", exc)

    def _load(self) -> None:
        """Load records from JSON file on startup."""
        if not _TUNING_FILE.exists():
            return
        try:
            raw = json.loads(_TUNING_FILE.read_text(encoding="utf-8"))
            for agent, records in raw.items():
                self._records[agent] = [
                    PromptRecord.from_dict(r) for r in records
                ]
            logger.info(
                "📂 PromptOptimizer: loaded %d records across %d agents",
                sum(len(r) for r in self._records.values()),
                len(self._records),
            )
        except Exception as exc:
            logger.warning("Failed to load prompt tuning data: %s", exc)
