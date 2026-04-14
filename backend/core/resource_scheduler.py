"""
GORVAX GAME FACTORY — Resource Scheduler (v3 Roadmap Item 17)

Distributes LLM budget credits among multiple concurrent pipelines
based on priority weighting. Ensures fair resource allocation and
prevents any single pipeline from monopolizing LLM calls.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class GameAllocation:
    """Budget allocation tracking for a single game."""
    game_id: str
    priority: int = 5            # 0 = highest priority, 10 = lowest
    allocated_usd: float = 0.0
    used_usd: float = 0.0

    @property
    def remaining_usd(self) -> float:
        return max(0.0, self.allocated_usd - self.used_usd)

    @property
    def usage_pct(self) -> float:
        if self.allocated_usd <= 0:
            return 0.0
        return round(self.used_usd / self.allocated_usd * 100, 1)

    def to_dict(self) -> dict[str, Any]:
        return {
            "game_id": self.game_id,
            "priority": self.priority,
            "allocated_usd": round(self.allocated_usd, 6),
            "used_usd": round(self.used_usd, 6),
            "remaining_usd": round(self.remaining_usd, 6),
            "usage_pct": self.usage_pct,
        }


class ResourceScheduler:
    """Distributes LLM budget among multiple games.

    Budget is divided proportionally to each game's weight, which is
    inversely proportional to its priority value (lower priority number
    = higher weight = more budget).

    Usage::

        scheduler = ResourceScheduler(total_budget_usd=10.0)
        scheduler.register("game_a", priority=1)
        scheduler.register("game_b", priority=5)
        scheduler.rebalance()
        # game_a gets 5/6 of budget, game_b gets 1/6

    Thread-safety: all mutating operations are protected by a lock.
    """

    def __init__(self, total_budget_usd: float = 10.0) -> None:
        self._total_budget = total_budget_usd
        self._allocations: dict[str, GameAllocation] = {}
        self._lock = threading.Lock()

    @property
    def total_budget(self) -> float:
        return self._total_budget

    def set_total_budget(self, budget_usd: float) -> None:
        """Update the total budget and rebalance."""
        with self._lock:
            self._total_budget = max(0.0, budget_usd)
        self.rebalance()

    def register(self, game_id: str, priority: int = 5) -> GameAllocation:
        """Register a game for resource allocation."""
        with self._lock:
            if game_id in self._allocations:
                self._allocations[game_id].priority = priority
                return self._allocations[game_id]
            alloc = GameAllocation(game_id=game_id, priority=priority)
            self._allocations[game_id] = alloc
        self.rebalance()
        logger.info("ResourceScheduler: registered game '%s' (priority=%d)", game_id, priority)
        return alloc

    def unregister(self, game_id: str) -> bool:
        """Remove a game and redistribute its budget."""
        with self._lock:
            if game_id not in self._allocations:
                return False
            del self._allocations[game_id]
        self.rebalance()
        logger.info("ResourceScheduler: unregistered game '%s'", game_id)
        return True

    def _weight(self, priority: int) -> float:
        """Convert priority to weight (lower priority = higher weight)."""
        # Priority 0 → weight 11, priority 10 → weight 1
        return float(max(1, 11 - priority))

    def rebalance(self) -> None:
        """Redistribute budget among all registered games proportionally."""
        with self._lock:
            if not self._allocations:
                return

            total_weight = sum(
                self._weight(a.priority) for a in self._allocations.values()
            )
            if total_weight <= 0:
                total_weight = 1.0

            for alloc in self._allocations.values():
                weight = self._weight(alloc.priority)
                alloc.allocated_usd = self._total_budget * (weight / total_weight)

    def allocate(self, game_id: str, priority: int = 5) -> float:
        """Get or create allocation for a game and return its budget."""
        alloc = self.register(game_id, priority)
        return alloc.allocated_usd

    def get_allocation(self, game_id: str) -> float:
        """Get current allocation for a game (0.0 if not registered)."""
        with self._lock:
            alloc = self._allocations.get(game_id)
            return alloc.allocated_usd if alloc else 0.0

    def record_usage(self, game_id: str, cost_usd: float) -> None:
        """Record LLM usage for a game."""
        with self._lock:
            alloc = self._allocations.get(game_id)
            if alloc:
                alloc.used_usd += cost_usd

    def get_remaining(self, game_id: str) -> float:
        """Get remaining budget for a game."""
        with self._lock:
            alloc = self._allocations.get(game_id)
            return alloc.remaining_usd if alloc else 0.0

    def is_over_budget(self, game_id: str) -> bool:
        """Check if a game has exceeded its allocation."""
        with self._lock:
            alloc = self._allocations.get(game_id)
            if not alloc:
                return False
            return alloc.used_usd > alloc.allocated_usd

    def get_stats(self) -> dict[str, Any]:
        """Return full allocation stats for all games."""
        with self._lock:
            total_used = sum(a.used_usd for a in self._allocations.values())
            return {
                "total_budget_usd": round(self._total_budget, 6),
                "total_used_usd": round(total_used, 6),
                "total_remaining_usd": round(self._total_budget - total_used, 6),
                "game_count": len(self._allocations),
                "games": {
                    gid: alloc.to_dict()
                    for gid, alloc in self._allocations.items()
                },
            }
