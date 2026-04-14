"""
GORVAX GAME FACTORY — Knowledge Transfer (Cross-Session Learning)

Promotes high-quality experiences from project-local namespace to a
global namespace, enabling knowledge reuse across different game projects.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

# ── Thresholds ─────────────────────────────────────────

# Minimum score_delta for an experience to be promoted to global
QUALITY_THRESHOLD = 0.7

# Maximum entries in the global namespace (FIFO eviction)
MAX_GLOBAL_ENTRIES = 1000

# Default global namespace name
GLOBAL_NAMESPACE = "global"


@dataclass
class TransferStats:
    """Statistics for knowledge transfer operations."""
    total_promoted: int = 0
    total_queries: int = 0
    global_hits: int = 0
    global_misses: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_promoted": self.total_promoted,
            "total_queries": self.total_queries,
            "global_hits": self.global_hits,
            "global_misses": self.global_misses,
            "hit_rate": (
                round(self.global_hits / self.total_queries, 3)
                if self.total_queries > 0 else 0.0
            ),
        }


class KnowledgeTransfer:
    """
    Transfers high-value experiences across project namespaces.

    Works with ExperienceDB's namespace support to promote decisions
    and failures that had significant positive impact to a global
    namespace accessible by all projects.

    Usage::

        kt = KnowledgeTransfer(experience_db_global)
        kt.promote(
            experience={"action": "add physics", "score_delta": 15},
            source_namespace="my_game",
        )
        results = kt.query_global("physics system design", top_k=3)
    """

    def __init__(self, experience_db: Any = None) -> None:
        """
        Args:
            experience_db: An ExperienceDB instance configured with
                the global namespace. If None, operates in no-op mode.
        """
        self._db = experience_db
        self._stats = TransferStats()
        self._promoted_ids: set[str] = set()

    @property
    def is_available(self) -> bool:
        """Whether the underlying ExperienceDB is functional."""
        return self._db is not None and getattr(self._db, "is_available", False)

    # ── Promote ────────────────────────────────────────

    def promote(
        self,
        experience: dict[str, Any],
        source_namespace: str,
        *,
        score_delta: float | None = None,
        genre: str = "",
    ) -> bool:
        """
        Promote a high-quality experience to the global namespace.

        Args:
            experience: The experience dict (action, result, context, etc.)
            source_namespace: Original project namespace
            score_delta: Quality improvement from this experience.
                If below QUALITY_THRESHOLD, promotion is skipped.
            genre: Game genre tag for filtering during retrieval.

        Returns:
            True if promoted, False if skipped or unavailable.
        """
        if not self.is_available:
            return False

        # Check quality threshold
        delta = score_delta if score_delta is not None else experience.get("score_delta", 0)
        if abs(delta) < QUALITY_THRESHOLD:
            logger.debug(
                "Skipping promotion: score_delta=%.2f below threshold=%.2f",
                delta, QUALITY_THRESHOLD,
            )
            return False

        # Build a unique ID to avoid duplicates
        exp_id = f"{source_namespace}:{experience.get('action', 'unknown')}:{experience.get('iteration', 0)}"
        if exp_id in self._promoted_ids:
            logger.debug("Already promoted: %s", exp_id)
            return False

        # Add metadata for global context
        enriched = {
            **experience,
            "source_namespace": source_namespace,
            "genre": genre,
            "promoted_at": datetime.now(timezone.utc).isoformat(),
        }

        try:
            # Store as a decision in the global ExperienceDB
            self._db.store_decision(
                iteration=experience.get("iteration", 0),
                agent=experience.get("agent", "pipeline"),
                action=experience.get("action", "unknown"),
                result=str(experience.get("result", "")),
                score_delta=delta,
                extra_metadata=enriched,
            )
            self._promoted_ids.add(exp_id)
            self._stats.total_promoted += 1
            logger.info(
                "🌐 Promoted experience to global: %s (delta=%.2f)",
                exp_id, delta,
            )
            return True

        except Exception as exc:
            logger.warning("Failed to promote experience: %s", exc)
            return False

    # ── Query ──────────────────────────────────────────

    def query_global(
        self,
        situation: str,
        *,
        genre_filter: str = "",
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        """
        Query the global namespace for relevant past experiences.

        Args:
            situation: Description of the current situation/problem.
            genre_filter: Optional genre to filter results.
            top_k: Maximum number of results.

        Returns:
            List of experience dicts from the global namespace.
        """
        self._stats.total_queries += 1

        if not self.is_available:
            self._stats.global_misses += 1
            return []

        try:
            results = self._db.query_decisions(
                situation=situation,
                n_results=top_k,
            )

            # Filter by genre if specified
            if genre_filter and results:
                results = [
                    r for r in results
                    if r.get("genre", "") == genre_filter
                    or not r.get("genre")
                ]

            if results:
                self._stats.global_hits += 1
                logger.debug(
                    "🌐 Global query hit: %d results for '%s'",
                    len(results), situation[:50],
                )
            else:
                self._stats.global_misses += 1

            return results

        except Exception as exc:
            logger.warning("Global query failed: %s", exc)
            self._stats.global_misses += 1
            return []

    # ── Stats ──────────────────────────────────────────

    def get_stats(self) -> dict[str, Any]:
        """Return transfer statistics."""
        return self._stats.to_dict()

    def reset_stats(self) -> None:
        """Reset statistics counters."""
        self._stats = TransferStats()
        self._promoted_ids.clear()
