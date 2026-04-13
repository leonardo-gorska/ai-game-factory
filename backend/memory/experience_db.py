"""
GORVAX GAME FACTORY — Experience Database
Indexes agent decisions and failures for semantic retrieval.
Built on top of VectorStore (ChromaDB).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from backend.memory.vector_store import VectorStore

logger = logging.getLogger(__name__)


class ExperienceDB:
    """
    Agent experience database.

    Indexes:
    - Decisions: {iteration, agent, action, result, score_delta}
    - Failures: {iteration, error, context, resolution}

    Allows searching for similar past experiences to
    inject as context into the LLM, improving decision-making.

    If VectorStore is in no-op mode (without ChromaDB),
    all operations return empty results gracefully.
    """

    def __init__(self, vector_store: VectorStore | None = None, namespace: str = "default") -> None:
        self._store = vector_store or VectorStore()
        self._namespace = namespace

    @property
    def is_available(self) -> bool:
        """Whether the underlying VectorStore is operational."""
        return self._store.is_available

    def get_namespace(self) -> str:
        """Return the namespace this ExperienceDB operates under."""
        return self._namespace

    def _collection(self, base_name: str) -> str:
        """Return the namespaced collection name."""
        if self._namespace == "default":
            return base_name
        return f"{self._namespace}_{base_name}"

    # ── Decisions ──────────────────────────────────────

    def store_decision(
        self,
        iteration: int,
        agent: str,
        action: str,
        result: str,
        score_delta: float = 0.0,
        metadata: dict[str, Any] | None = None,
        extra_metadata: dict[str, Any] | None = None,
    ) -> str | None:
        """
        Store a decision made by an agent.

        Args:
            iteration: Iteration number
            agent: Agent name (designer, developer, etc.)
            action: Action taken
            result: Result summary
            score_delta: Score change after the decision
            metadata: Additional data

        Returns:
            Document ID or None
        """
        text = (
            f"[Iteration {iteration}] Agent: {agent}\n"
            f"Action: {action}\n"
            f"Result: {result}\n"
            f"Score Delta: {score_delta:+.1f}"
        )

        meta = {
            "iteration": iteration,
            "agent": agent,
            "action": action,
            "score_delta": score_delta,
            "outcome": "positive" if score_delta > 0 else "negative" if score_delta < 0 else "neutral",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **(metadata or {}),
            **(extra_metadata or {}),
        }

        doc_id = f"dec_{iteration}_{agent}"

        stored_id = self._store.store(
            collection=self._collection("decisions"),
            text=text,
            metadata=meta,
            doc_id=doc_id,
        )

        if stored_id:
            logger.debug(
                "Stored decision: iter=%d agent=%s delta=%+.1f",
                iteration, agent, score_delta,
            )

        return stored_id

    # ── Failures ───────────────────────────────────────

    def store_failure(
        self,
        iteration: int,
        error: str,
        context: str = "",
        resolution: str = "",
        agent: str = "",
    ) -> str | None:
        """
        Store a failure and its resolution.

        Args:
            iteration: Iteration number
            error: Error message
            context: Context in which the error occurred
            resolution: How the error was resolved (if it was)
            agent: Agent that caused or resolved the error

        Returns:
            Document ID or None
        """
        text = (
            f"[Iteration {iteration}] Error: {error}\n"
            f"Context: {context}\n"
            f"Resolution: {resolution or 'unresolved'}"
        )

        meta = {
            "iteration": iteration,
            "error_type": error[:100],
            "agent": agent,
            "resolved": bool(resolution),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        doc_id = f"fail_{iteration}_{agent or 'system'}"

        stored_id = self._store.store(
            collection=self._collection("failures"),
            text=text,
            metadata=meta,
            doc_id=doc_id,
        )

        if stored_id:
            logger.debug(
                "Stored failure: iter=%d error=%s resolved=%s",
                iteration, error[:50], bool(resolution),
            )

        return stored_id

    # ── Retrieval ─────────────────────────────────────

    def get_similar_experiences(
        self,
        situation: str,
        top_k: int = 5,
        agent: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Search for past experiences similar to the current situation.
        Combines relevant decisions and failures.

        Args:
            situation: Description of the current situation
            top_k: Maximum number of results
            agent: Filter by specific agent (optional)

        Returns:
            List of experiences with 'type', 'text', 'relevance', 'metadata'
        """
        results: list[dict[str, Any]] = []

        # Ensure situation is a non-empty string for ChromaDB query
        if not isinstance(situation, str):
            import json as _json
            try:
                situation = _json.dumps(situation, default=str)
            except Exception:
                situation = str(situation)
        situation = situation.strip()
        if not situation:
            return results

        # Search similar decisions
        where = {"agent": agent} if agent else None
        decisions = self._store.query(
            collection=self._collection("decisions"),
            text=situation,
            top_k=top_k,
            where=where,
        )

        for d in decisions:
            results.append({
                "type": "decision",
                "text": d["document"],
                "relevance": 1.0 - d.get("distance", 0.5),
                "metadata": d.get("metadata", {}),
            })

        # Search similar failures
        failures = self._store.query(
            collection=self._collection("failures"),
            text=situation,
            top_k=max(2, top_k // 2),
            where=where,
        )

        for f in failures:
            results.append({
                "type": "failure",
                "text": f["document"],
                "relevance": 1.0 - f.get("distance", 0.5),
                "metadata": f.get("metadata", {}),
            })

        # Sort by relevance and limit
        results.sort(key=lambda x: x["relevance"], reverse=True)
        return results[:top_k]

    def get_successful_patterns(
        self,
        agent: str | None = None,
        top_k: int = 10,
    ) -> list[dict[str, Any]]:
        """
        Search for decisions with positive score_delta (success patterns).

        Args:
            agent: Filter by agent
            top_k: Number of results

        Returns:
            List of successful decisions
        """
        where_filter: dict[str, Any] = {"outcome": "positive"}
        if agent:
            where_filter["agent"] = agent

        return self._store.query(
            collection=self._collection("decisions"),
            text="successful improvement high score",
            top_k=top_k,
            where=where_filter,
        )

    def format_context(
        self,
        experiences: list[dict[str, Any]],
        max_chars: int = 2000,
    ) -> str:
        """
        Format experiences for injection into the LLM prompt.

        Args:
            experiences: List of experiences
            max_chars: Character limit

        Returns:
            Formatted string for LLM context
        """
        if not experiences:
            return ""

        parts: list[str] = ["## Relevant Past Experiences\n"]
        total_chars = len(parts[0])

        for i, exp in enumerate(experiences, 1):
            entry = (
                f"### Experience {i} ({exp['type']}, "
                f"relevance: {exp['relevance']:.0%})\n"
                f"{exp['text']}\n"
            )

            if total_chars + len(entry) > max_chars:
                break

            parts.append(entry)
            total_chars += len(entry)

        return "\n".join(parts)

    def get_stats(self) -> dict[str, Any]:
        """Experience database statistics."""
        return {
            "available": self.is_available,
            "decisions_count": self._store.count("decisions"),
            "failures_count": self._store.count("failures"),
            "vector_store": self._store.get_stats(),
        }
