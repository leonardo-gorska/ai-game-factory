"""
GORVAX GAME FACTORY — Agent Confidence Scoring (Roadmap v3 Item #14)

Agents declare confidence (0–100) in their own output. Low confidence
triggers intelligent retries with adjusted temperature or a higher-tier
model, improving overall pipeline quality without manual intervention.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# ── Pattern for extracting confidence from JSON responses ──

_CONFIDENCE_PATTERN = re.compile(
    r'"confidence"\s*:\s*(\d{1,3})', re.IGNORECASE,
)


# ── Data classes ──────────────────────────────────────


@dataclass
class ConfidenceRecord:
    """Record of a single agent confidence measurement."""

    agent: str
    iteration: int
    confidence: int
    retried: bool = False
    original_confidence: int = -1  # -1 means no retry (first attempt)

    @property
    def improved(self) -> bool:
        """Did the retry produce higher confidence?"""
        return self.retried and self.confidence > self.original_confidence


# ── Confidence Scorer ─────────────────────────────────


class ConfidenceScorer:
    """Extracts and tracks agent confidence scores.

    When an agent reports low confidence, suggests retry parameters
    (lower temperature, higher-tier model) to improve output quality.
    """

    def __init__(
        self,
        retry_threshold: int = 40,
        max_retries: int = 1,
    ) -> None:
        self._history: dict[str, list[ConfidenceRecord]] = {}
        self._retry_threshold = retry_threshold
        self._max_retries = max_retries
        # Track retries in current iteration to respect max_retries
        self._current_retries: dict[str, int] = {}

    # ── Extraction ────────────────────────────────────

    @staticmethod
    def extract_confidence(response_text: str) -> int:
        """Extract confidence value (0–100) from an LLM response.

        Looks for `"confidence": N` in the response text.
        Returns -1 if not found or invalid.
        """
        if not response_text:
            return -1

        match = _CONFIDENCE_PATTERN.search(response_text)
        if not match:
            return -1

        try:
            value = int(match.group(1))
            return max(0, min(100, value))
        except (ValueError, IndexError):
            return -1

    # ── Retry Logic ───────────────────────────────────

    def should_retry(self, agent: str, confidence: int) -> bool:
        """Determine if the agent should retry based on confidence.

        Returns True if confidence is below threshold and max retries
        haven't been reached for this agent in the current iteration.
        """
        if confidence < 0:
            return False  # No confidence extracted, can't retry
        if confidence >= self._retry_threshold:
            return False

        retries_used = self._current_retries.get(agent, 0)
        return retries_used < self._max_retries

    def suggest_retry_params(
        self, agent: str, confidence: int,
    ) -> dict[str, Any]:
        """Suggest adjusted parameters for a retry.

        Logic:
        - confidence < 40: lower temperature (more deterministic)
        - confidence < 25: also escalate to high tier
        """
        params: dict[str, Any] = {}

        if confidence < self._retry_threshold:
            # More deterministic with lower temperature
            params["temperature"] = max(0.1, 0.7 * 0.7)  # ~0.49

        if confidence < 25:
            # Escalate to a higher-tier model
            params["tier_override"] = "high"
            params["temperature"] = max(0.1, 0.7 * 0.5)  # ~0.35

        return params

    # ── Recording ─────────────────────────────────────

    def record(
        self,
        agent: str,
        iteration: int,
        confidence: int,
        retried: bool = False,
        original_confidence: int = -1,
    ) -> None:
        """Record a confidence measurement."""
        record = ConfidenceRecord(
            agent=agent,
            iteration=iteration,
            confidence=confidence,
            retried=retried,
            original_confidence=original_confidence,
        )

        if agent not in self._history:
            self._history[agent] = []
        self._history[agent].append(record)

        # Track retries
        if retried:
            self._current_retries[agent] = (
                self._current_retries.get(agent, 0) + 1
            )

        logger.debug(
            "Confidence recorded: %s iter #%d → %d%s",
            agent, iteration, confidence,
            " (retry)" if retried else "",
        )

    def reset_iteration_retries(self) -> None:
        """Reset per-iteration retry counters. Call at iteration start."""
        self._current_retries.clear()

    # ── Stats ─────────────────────────────────────────

    def get_agent_stats(self, agent: str) -> dict[str, Any]:
        """Get confidence statistics for a specific agent."""
        records = self._history.get(agent, [])
        if not records:
            return {
                "agent": agent,
                "total_records": 0,
                "avg_confidence": 0.0,
                "retry_count": 0,
                "retry_improvement_rate": 0.0,
            }

        confidences = [r.confidence for r in records if r.confidence >= 0]
        retries = [r for r in records if r.retried]
        improvements = [r for r in retries if r.improved]

        avg_conf = sum(confidences) / len(confidences) if confidences else 0.0

        return {
            "agent": agent,
            "total_records": len(records),
            "avg_confidence": round(avg_conf, 1),
            "min_confidence": min(confidences) if confidences else 0,
            "max_confidence": max(confidences) if confidences else 0,
            "retry_count": len(retries),
            "retry_improvement_rate": (
                len(improvements) / len(retries) if retries else 0.0
            ),
        }

    def get_stats(self) -> dict[str, Any]:
        """Get global confidence statistics."""
        all_records: list[ConfidenceRecord] = []
        for records in self._history.values():
            all_records.extend(records)

        if not all_records:
            return {
                "total_records": 0,
                "agents_tracked": 0,
                "global_avg_confidence": 0.0,
                "total_retries": 0,
                "total_improvements": 0,
            }

        confidences = [r.confidence for r in all_records if r.confidence >= 0]
        retries = [r for r in all_records if r.retried]
        improvements = [r for r in retries if r.improved]

        return {
            "total_records": len(all_records),
            "agents_tracked": len(self._history),
            "global_avg_confidence": (
                round(sum(confidences) / len(confidences), 1)
                if confidences else 0.0
            ),
            "total_retries": len(retries),
            "total_improvements": len(improvements),
            "retry_threshold": self._retry_threshold,
            "max_retries_per_agent": self._max_retries,
        }

    def get_low_confidence_agents(
        self, last_n: int = 10,
    ) -> list[dict[str, Any]]:
        """Get agents with consistently low confidence.

        Returns agents whose average confidence over the last N records
        is below the retry threshold.
        """
        low: list[dict[str, Any]] = []

        for agent, records in self._history.items():
            recent = records[-last_n:] if len(records) > last_n else records
            confidences = [r.confidence for r in recent if r.confidence >= 0]
            if not confidences:
                continue
            avg = sum(confidences) / len(confidences)
            if avg < self._retry_threshold:
                low.append({
                    "agent": agent,
                    "avg_confidence": round(avg, 1),
                    "sample_size": len(confidences),
                })

        return sorted(low, key=lambda x: x["avg_confidence"])
