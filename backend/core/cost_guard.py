"""
GORVAX GAME FACTORY — Cost Guard v2
Intelligent cost control. Monitors spending per agent,
per iteration, and per hour. Can pause the pipeline if budget is exceeded.
v2: Dynamic per-agent token budgets with auto-rebalancing.
"""

from __future__ import annotations

import bisect
import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class CostEntry:
    """Individual cost record."""
    agent: str
    provider: str
    tokens_input: int = 0
    tokens_output: int = 0
    estimated_cost_usd: float = 0.0
    iteration: int = 0
    timestamp: float = field(default_factory=time.time)


@dataclass
class CostBudget:
    """Budget configuration."""
    max_per_hour_usd: float = 2.00
    max_per_iteration_usd: float = 0.10
    max_total_usd: float = 50.00
    warning_threshold: float = 0.80
    # v2: Default per-agent token limit per iteration
    default_agent_tokens_per_iter: int = 8000
    total_token_pool_per_iter: int = 50000  # shared pool for all agents


# Estimated cost per 1M tokens (input/output) per provider
# Based on free tiers and cheapest plans
COST_PER_MILLION_TOKENS: dict[str, dict[str, float]] = {
    "gemini": {"input": 0.001, "output": 0.001},      # Free tier (symbolic cost for functional budget)
    "groq": {"input": 0.001, "output": 0.001},         # Free tier (symbolic cost for functional budget)
    "mistral": {"input": 0.25, "output": 0.25},        # Very cheap
    "openrouter": {"input": 0.10, "output": 0.10},     # Varies by model
}


class CostGuard:
    """
    Cost monitor with budget enforcement.
    Tracks cost per agent, per iteration, and per hour.
    Can block execution if budget is exceeded.
    """

    MAX_ENTRIES = 500  # BE-20: Sliding window to prevent unbounded growth
    MAX_ITERATIONS_STATS = 50  # PERF-05: Limit by_iteration in stats

    def __init__(self, budget: CostBudget | None = None) -> None:
        self.budget = budget or CostBudget()
        self._entries: list[CostEntry] = []
        self._total_cost: float = 0.0
        self._alerts: list[str] = []
        # v2: Per-agent token budgets
        self._agent_token_budgets: dict[str, int] = {}
        self._agent_usage_history: dict[str, list[int]] = {}
        # PERF-01: Incremental accumulators (O(1) lookups)
        self._total_by_agent: dict[str, float] = {}
        self._total_by_provider: dict[str, float] = {}
        self._total_by_iteration: dict[int, float] = {}
        self._total_tokens: int = 0
        # M1: Sorted timestamps + costs for O(log n) hourly cost
        self._ts_costs: list[tuple[float, float]] = []  # (timestamp, cost)
        # M2: Incremental per-(agent, iteration) token accumulator
        self._agent_iter_tokens: dict[tuple[str, int], int] = {}

    def record(
        self,
        agent: str,
        provider: str,
        tokens_input: int,
        tokens_output: int,
        iteration: int,
    ) -> CostEntry:
        """
        Record an LLM call and calculate estimated cost.
        """
        rates = COST_PER_MILLION_TOKENS.get(provider, {"input": 0.1, "output": 0.1})
        cost = (
            (tokens_input / 1_000_000) * rates["input"]
            + (tokens_output / 1_000_000) * rates["output"]
        )

        entry = CostEntry(
            agent=agent,
            provider=provider,
            tokens_input=tokens_input,
            tokens_output=tokens_output,
            estimated_cost_usd=cost,
            iteration=iteration,
        )

        self._entries.append(entry)
        # BE-20: Sliding window — keep only last MAX_ENTRIES
        if len(self._entries) > self.MAX_ENTRIES:
            self._entries = self._entries[-self.MAX_ENTRIES:]
        self._total_cost += cost

        # PERF-01: Update incremental accumulators
        self._total_by_agent[agent] = self._total_by_agent.get(agent, 0) + cost
        self._total_by_provider[provider] = self._total_by_provider.get(provider, 0) + cost
        self._total_by_iteration[iteration] = self._total_by_iteration.get(iteration, 0) + cost
        self._total_tokens += tokens_input + tokens_output

        # M1: Append to sorted timestamp-cost list
        self._ts_costs.append((entry.timestamp, cost))
        # M2: Accumulate per-(agent, iteration) tokens
        key = (agent, iteration)
        self._agent_iter_tokens[key] = (
            self._agent_iter_tokens.get(key, 0) + tokens_input + tokens_output
        )

        return entry

    def check_budget(self) -> tuple[bool, str]:
        """
        Check if the budget is OK.

        Returns:
            (can_continue, reason)
        """
        # Check total budget
        if self._total_cost >= self.budget.max_total_usd:
            reason = (
                f"💀 Total budget exhausted: ${self._total_cost:.4f} "
                f">= ${self.budget.max_total_usd:.2f}"
            )
            logger.warning(reason)
            return False, reason

        # Check hourly rate
        hourly = self._cost_last_hour()
        if hourly >= self.budget.max_per_hour_usd:
            reason = (
                f"⚠️ Hourly budget exceeded: ${hourly:.4f}/hr "
                f">= ${self.budget.max_per_hour_usd:.2f}/hr"
            )
            logger.warning(reason)
            return False, reason

        # Warning threshold
        usage_pct = self._total_cost / max(self.budget.max_total_usd, 0.01)
        if usage_pct >= self.budget.warning_threshold:
            alert = (
                f"⚠️ Budget at {usage_pct:.0%}: "
                f"${self._total_cost:.4f} / ${self.budget.max_total_usd:.2f}"
            )
            if alert not in self._alerts:
                self._alerts.append(alert)
                logger.warning(alert)

        return True, "ok"

    def check_iteration_budget(self, iteration: int) -> tuple[bool, str]:
        """Check if the current iteration is still within budget."""
        # PERF-01: Use incremental accumulator instead of iterating
        iter_cost = self._total_by_iteration.get(iteration, 0)

        if iter_cost >= self.budget.max_per_iteration_usd:
            reason = (
                f"Iteration #{iteration} budget exceeded: "
                f"${iter_cost:.4f} >= ${self.budget.max_per_iteration_usd:.2f}"
            )
            logger.warning(reason)
            return False, reason

        return True, "ok"

    def get_roi_score(self, quality_improvement: float) -> float:
        """
        Calculate ROI: quality improvement per dollar spent.
        Returns a normalized score (0-100).

        Negative ROI → early stop recommended.
        """
        if self._total_cost == 0:
            return 100.0  # No cost = infinite ROI

        roi = quality_improvement / self._total_cost

        # Normalize: ROI of 100 points per $1 = score 80
        return min(100.0, roi * 0.8)

    def recommend_provider(self, available: list[str]) -> str:
        """
        Recommend the cheapest provider among available ones.
        """
        costs = {
            p: sum(COST_PER_MILLION_TOKENS.get(p, {}).values())
            for p in available
        }
        if not available:
            return "unknown"
        return min(costs, key=costs.get) if costs else available[0]

    def _cost_last_hour(self) -> float:
        """Cost in the last hour (O(log n) via bisect)."""
        cutoff = time.time() - 3600
        # M1: Binary search on sorted timestamps
        idx = bisect.bisect_left(self._ts_costs, (cutoff, 0.0))
        return sum(cost for _, cost in self._ts_costs[idx:])

    def get_stats(self) -> dict[str, Any]:
        """Cost statistics for the dashboard."""
        # PERF-01: Use incremental accumulators instead of iterating
        by_iteration = self._total_by_iteration
        n_iterations = max(len(by_iteration), 1)

        return {
            "total_cost_usd": round(self._total_cost, 6),
            "total_calls": len(self._entries),
            "total_tokens": self._total_tokens,
            "cost_last_hour": round(self._cost_last_hour(), 6),
            "budget_remaining_usd": round(
                self.budget.max_total_usd - self._total_cost, 4
            ),
            "budget_usage_pct": round(
                self._total_cost / max(self.budget.max_total_usd, 0.01) * 100, 1
            ),
            "by_agent": {k: round(v, 6) for k, v in self._total_by_agent.items()},
            "by_provider": {k: round(v, 6) for k, v in self._total_by_provider.items()},
            # PERF-05: Only return last N iterations to avoid unbounded growth
            "by_iteration": {
                k: round(v, 6)
                for k, v in sorted(by_iteration.items())[-self.MAX_ITERATIONS_STATS:]
            },
            "avg_cost_per_iteration": round(
                self._total_cost / n_iterations, 6
            ),
            "alerts": self._alerts[-5:],
            # v2: Agent token budgets
            "agent_token_budgets": dict(self._agent_token_budgets),
        }

    # ── v2: Dynamic Token Budget Methods ───────────

    def get_agent_token_budget(self, agent: str) -> int:
        """
        v2: Get the current token budget for an agent.
        Returns the dynamic allocation, or the default if not yet set.
        """
        if agent not in self._agent_token_budgets:
            self._agent_token_budgets[agent] = (
                self.budget.default_agent_tokens_per_iter
            )
        return self._agent_token_budgets[agent]

    def check_agent_token_budget(
        self, agent: str, iteration: int,
    ) -> tuple[bool, int]:
        """
        v2: Check if agent has remaining token budget for this iteration.
        M2: Uses incremental accumulator for O(1) lookup.

        Returns:
            (can_continue, remaining_tokens)
        """
        budget = self.get_agent_token_budget(agent)
        used = self._agent_iter_tokens.get((agent, iteration), 0)
        remaining = budget - used
        return remaining > 0, max(0, remaining)

    def rebalance_agent_budgets(self) -> None:
        """
        v2: Dynamically rebalance token budgets based on usage history.
        Agents that consistently under-use their budget donate tokens
        to agents that need more. Called at iteration boundaries.
        """
        if not self._agent_usage_history:
            return

        pool = self.budget.total_token_pool_per_iter
        agents = list(self._agent_usage_history.keys())
        if not agents:
            return

        # Calculate average usage per agent (last 5 iterations)
        avg_usage: dict[str, float] = {}
        for agent, history in self._agent_usage_history.items():
            recent = history[-5:] if history else [0]
            avg_usage[agent] = sum(recent) / len(recent)

        total_avg = sum(avg_usage.values())
        if total_avg == 0:
            # Equal distribution
            per_agent = pool // len(agents)
            for agent in agents:
                self._agent_token_budgets[agent] = per_agent
            return

        # Proportional allocation with floor
        floor = self.budget.default_agent_tokens_per_iter // 2
        for agent in agents:
            ratio = avg_usage[agent] / total_avg
            allocation = int(pool * ratio)
            self._agent_token_budgets[agent] = max(floor, allocation)

        logger.info(
            "\u2699\ufe0f Token budgets rebalanced: %s",
            {k: v for k, v in self._agent_token_budgets.items()},
        )

    def record_agent_usage(self, agent: str, tokens_used: int) -> None:
        """
        v2: Record an agent's token usage for rebalancing.
        Called at the end of each agent execution.
        """
        if agent not in self._agent_usage_history:
            self._agent_usage_history[agent] = []
        self._agent_usage_history[agent].append(tokens_used)
        # Keep only last 20 entries
        if len(self._agent_usage_history[agent]) > 20:
            self._agent_usage_history[agent] = (
                self._agent_usage_history[agent][-20:]
            )
