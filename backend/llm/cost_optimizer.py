"""
GORVAX GAME FACTORY — Cost-Aware Routing Intelligence

Tracks ROI (quality / cost) per agent×provider pair and provides
routing bonuses to the LLM Router's scoring function.  Agents that
consistently get better results from a specific provider will be
automatically routed there.

Roadmap v3 Item #11.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ── Data Classes ──────────────────────────────────────

@dataclass
class CallRecord:
    """Single LLM call record for ROI tracking."""

    agent: str
    provider: str
    cost_usd: float
    quality_delta: float  # Score change attributed to this call
    latency: float  # seconds
    tokens: int
    timestamp: float = field(default_factory=time.time)


@dataclass
class AgentProviderROI:
    """Accumulated ROI stats for an agent×provider pair."""

    total_calls: int = 0
    total_cost_usd: float = 0.0
    total_quality: float = 0.0
    total_tokens: int = 0
    total_latency: float = 0.0
    last_call: float = 0.0

    @property
    def avg_cost(self) -> float:
        return self.total_cost_usd / max(self.total_calls, 1)

    @property
    def avg_quality(self) -> float:
        return self.total_quality / max(self.total_calls, 1)

    @property
    def avg_latency(self) -> float:
        return self.total_latency / max(self.total_calls, 1)

    @property
    def roi(self) -> float:
        """ROI = total quality gained / total cost spent.

        If cost is near zero (free tier), use token count as proxy.
        Higher is better.
        """
        if self.total_cost_usd > 0.0001:
            return self.total_quality / self.total_cost_usd
        # Free tier: use tokens as denominator (normalized per 100K tokens)
        token_cost_proxy = self.total_tokens / 100_000.0
        return self.total_quality / max(token_cost_proxy, 0.01)


# ── Constants ─────────────────────────────────────────

# Minimum calls before ROI-based routing kicks in
MIN_CALLS_FOR_BONUS = 5

# Maximum routing bonus that can be added to the score
MAX_ROUTING_BONUS = 0.30

# Maximum records to keep in memory (prune oldest)
MAX_RECORDS = 5000


class CostOptimizer:
    """Tracks ROI per agent×provider and provides routing bonuses.

    Usage::

        optimizer = CostOptimizer()
        optimizer.record_call("developer", "sambanova", 0.001, 5.0, 2.1, 1500)

        bonus = optimizer.get_routing_bonus("developer", "sambanova")
        # → 0.0 to 0.30 based on historical ROI
    """

    def __init__(self) -> None:
        self._records: list[CallRecord] = []
        self._roi_cache: dict[tuple[str, str], AgentProviderROI] = {}
        self._dirty: bool = False

    # ── Recording ─────────────────────────────────────

    def record_call(
        self,
        agent: str,
        provider: str,
        cost_usd: float,
        quality_delta: float = 0.0,
        latency: float = 0.0,
        tokens: int = 0,
    ) -> None:
        """Record an LLM call for ROI tracking.

        Args:
            agent: Agent name (e.g. "developer", "tester").
            provider: Provider name (e.g. "sambanova", "gemini").
            cost_usd: Estimated cost of the call in USD.
            quality_delta: Quality score change attributed to this call.
            latency: Call latency in seconds.
            tokens: Total tokens used.
        """
        record = CallRecord(
            agent=agent,
            provider=provider,
            cost_usd=cost_usd,
            quality_delta=quality_delta,
            latency=latency,
            tokens=tokens,
        )
        self._records.append(record)

        # Update ROI cache incrementally
        key = (agent, provider)
        roi = self._roi_cache.get(key)
        if roi is None:
            roi = AgentProviderROI()
            self._roi_cache[key] = roi

        roi.total_calls += 1
        roi.total_cost_usd += cost_usd
        roi.total_quality += quality_delta
        roi.total_tokens += tokens
        roi.total_latency += latency
        roi.last_call = record.timestamp

        # Prune if too many records
        if len(self._records) > MAX_RECORDS:
            self._prune_oldest()

        self._dirty = True

    def _prune_oldest(self) -> None:
        """Remove oldest half of records and rebuild cache."""
        cutoff = len(self._records) // 2
        self._records = self._records[cutoff:]
        self._rebuild_cache()

    def _rebuild_cache(self) -> None:
        """Rebuild ROI cache from records."""
        self._roi_cache.clear()
        for record in self._records:
            key = (record.agent, record.provider)
            roi = self._roi_cache.get(key)
            if roi is None:
                roi = AgentProviderROI()
                self._roi_cache[key] = roi
            roi.total_calls += 1
            roi.total_cost_usd += record.cost_usd
            roi.total_quality += record.quality_delta
            roi.total_tokens += record.tokens
            roi.total_latency += record.latency
            roi.last_call = record.timestamp

    # ── Query API ─────────────────────────────────────

    def get_roi(self, agent: str, provider: str) -> float:
        """Get ROI for an agent×provider pair.

        Returns 0.0 if insufficient data.
        """
        roi = self._roi_cache.get((agent, provider))
        if roi is None or roi.total_calls < MIN_CALLS_FOR_BONUS:
            return 0.0
        return roi.roi

    def get_best_provider(self, agent: str) -> str | None:
        """Get the provider with best ROI for a given agent.

        Returns None if insufficient data for any provider.
        """
        best_provider: str | None = None
        best_roi = 0.0

        for (a, p), roi in self._roi_cache.items():
            if a != agent or roi.total_calls < MIN_CALLS_FOR_BONUS:
                continue
            current_roi = roi.roi
            if current_roi > best_roi:
                best_roi = current_roi
                best_provider = p

        return best_provider

    def get_routing_bonus(self, agent: str, provider: str) -> float:
        """Get routing bonus for _score_provider (0.0 to MAX_ROUTING_BONUS).

        The bonus is relative: highest ROI provider for this agent gets
        the full bonus, others get proportionally less.
        """
        roi = self._roi_cache.get((agent, provider))
        if roi is None or roi.total_calls < MIN_CALLS_FOR_BONUS:
            return 0.0

        # Gather all providers for this agent
        agent_rois: list[tuple[str, float]] = []
        for (a, p), r in self._roi_cache.items():
            if a == agent and r.total_calls >= MIN_CALLS_FOR_BONUS:
                agent_rois.append((p, r.roi))

        if not agent_rois:
            return 0.0

        max_roi = max(r for _, r in agent_rois)
        if max_roi <= 0:
            return 0.0

        # Normalize: best provider gets MAX_ROUTING_BONUS
        current_roi = roi.roi
        relative = current_roi / max_roi
        return round(relative * MAX_ROUTING_BONUS, 4)

    def get_agent_stats(self, agent: str) -> dict[str, Any]:
        """Get stats for all providers used by an agent."""
        result: dict[str, Any] = {}
        for (a, p), roi in self._roi_cache.items():
            if a != agent:
                continue
            result[p] = {
                "calls": roi.total_calls,
                "total_cost": round(roi.total_cost_usd, 6),
                "avg_quality": round(roi.avg_quality, 2),
                "avg_cost": round(roi.avg_cost, 6),
                "avg_latency": round(roi.avg_latency, 2),
                "roi": round(roi.roi, 2),
            }
        return result

    def get_stats(self) -> dict[str, Any]:
        """Get global statistics."""
        total_calls = sum(r.total_calls for r in self._roi_cache.values())
        total_cost = sum(r.total_cost_usd for r in self._roi_cache.values())
        agents = set(a for a, _ in self._roi_cache.keys())
        providers = set(p for _, p in self._roi_cache.keys())

        return {
            "total_records": len(self._records),
            "total_calls": total_calls,
            "total_cost_usd": round(total_cost, 6),
            "unique_agents": len(agents),
            "unique_providers": len(providers),
            "pairs_tracked": len(self._roi_cache),
        }
