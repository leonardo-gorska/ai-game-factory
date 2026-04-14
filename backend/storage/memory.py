"""
GORVAX GAME FACTORY — Agent Memory
Manages short-term and long-term memory for AI agents,
keeping context within token limits.
"""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class MemoryEntry:
    """A single memory entry."""
    role: str  # "designer", "developer", "tester", "critic"
    action: str  # What was done
    content: str  # The actual content/output
    iteration: int
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    importance: int = 5  # 1-10 scale, higher = more important

    def to_text(self, max_length: int = 500) -> str:
        """Convert to a text summary for context."""
        text = f"[Iter {self.iteration}] {self.role}: {self.action}"
        if self.content:
            content_preview = self.content[:max_length]
            if len(self.content) > max_length:
                content_preview += "..."
            text += f"\n{content_preview}"
        return text


class AgentMemory:
    """
    Memory system for an AI agent.
    Keeps a rolling window of recent memories and important milestones.
    """

    def __init__(
        self,
        agent_name: str,
        max_short_term: int = 30,   # P7: increased from 10
        max_long_term: int = 100,   # P7: increased from 50
    ) -> None:
        self.agent_name = agent_name
        self._max_short_term = max_short_term
        self._max_long_term = max_long_term
        self._short_term: list[MemoryEntry] = []
        self._long_term: list[MemoryEntry] = []
        self._facts: dict[str, str] = {}  # key-value facts
        self._lock = threading.Lock()

    def add(
        self,
        action: str,
        content: str,
        iteration: int,
        importance: int = 5,
    ) -> None:
        """Add a new memory entry (thread-safe)."""
        entry = MemoryEntry(
            role=self.agent_name,
            action=action,
            content=content,
            iteration=iteration,
            importance=importance,
        )
        with self._lock:
            self._short_term.append(entry)

            # Promote to long-term if important
            if importance >= 7:
                self._long_term.append(entry)

            # Trim short-term memory
            if len(self._short_term) > self._max_short_term:
                removed = self._short_term.pop(0)
                # Keep in long-term if somewhat important
                if removed.importance >= 5 and removed not in self._long_term:
                    self._long_term.append(removed)

            # Trim long-term memory (keep most important)
            if len(self._long_term) > self._max_long_term:
                self._long_term.sort(key=lambda m: m.importance, reverse=True)
                self._long_term = self._long_term[: self._max_long_term]

    def set_fact(self, key: str, value: str) -> None:
        """Store a persistent fact (e.g., 'current_game_genre': 'idle RPG')."""
        self._facts[key] = value

    def get_fact(self, key: str) -> str | None:
        """Retrieve a persistent fact."""
        return self._facts.get(key)

    def get_context(self, max_entries: int = 8) -> str:
        """
        Build a context string for the agent's LLM prompt.
        Combines recent memories + important long-term memories.
        """
        sections: list[str] = []

        # Facts
        if self._facts:
            facts_text = "\n".join(f"- {k}: {v}" for k, v in self._facts.items())
            sections.append(f"## Key Facts\n{facts_text}")

        # Recent actions (short-term)
        if self._short_term:
            recent = self._short_term[-max_entries:]
            recent_text = "\n\n".join(e.to_text(300) for e in recent)
            sections.append(f"## Recent Actions\n{recent_text}")

        # Important past events (long-term)
        important = [
            e for e in self._long_term
            if e not in self._short_term[-max_entries:]
        ]
        if important:
            important_sorted = sorted(important, key=lambda m: m.importance, reverse=True)
            top = important_sorted[:5]
            important_text = "\n\n".join(e.to_text(200) for e in top)
            sections.append(f"## Important Past Events\n{important_text}")

        return "\n\n".join(sections)

    def get_last_output(self) -> str:
        """Get the content of the most recent memory entry."""
        if self._short_term:
            return self._short_term[-1].content
        return ""

    def clear(self) -> None:
        """Clear all memories (keeps facts)."""
        self._short_term.clear()
        self._long_term.clear()

    def to_dict(self) -> dict[str, Any]:
        """Serialize memory state for persistence."""
        return {
            "agent_name": self.agent_name,
            "facts": self._facts,
            "short_term_count": len(self._short_term),
            "long_term_count": len(self._long_term),
        }

    # ── P7: Disk Persistence ──────────────────────────

    def save_to_disk(self, directory: Any) -> None:
        """Persist memory state to disk (thread-safe)."""
        from pathlib import Path
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        filepath = directory / f"{self.agent_name}_memory.json"
        with self._lock:
            data = {
                "agent_name": self.agent_name,
                "facts": self._facts,
                "short_term": [
                    {
                        "role": e.role, "action": e.action,
                        "content": e.content[:2000],
                        "iteration": e.iteration,
                        "timestamp": e.timestamp,
                        "importance": e.importance,
                    }
                    for e in self._short_term
                ],
                "long_term": [
                    {
                        "role": e.role, "action": e.action,
                        "content": e.content[:2000],
                        "iteration": e.iteration,
                        "timestamp": e.timestamp,
                        "importance": e.importance,
                    }
                    for e in self._long_term
                ],
            }
        filepath.write_text(json.dumps(data, indent=2), encoding="utf-8")
        logger.debug("Saved memory for %s to %s", self.agent_name, filepath)

    @staticmethod
    def _validate_entry(data: Any) -> bool:
        """Validate a memory entry dict before deserialization."""
        if not isinstance(data, dict):
            return False
        required = {"role": str, "action": str, "content": str, "iteration": int}
        for key, expected_type in required.items():
            if key not in data or not isinstance(data[key], expected_type):
                return False
        # Optional fields
        if "importance" in data and not isinstance(data["importance"], int):
            return False
        if "timestamp" in data and not isinstance(data["timestamp"], str):
            return False
        return True

    def load_from_disk(self, directory: Any) -> None:
        """Load memory state from disk (thread-safe, with validation)."""
        from pathlib import Path
        directory = Path(directory)
        filepath = directory / f"{self.agent_name}_memory.json"
        if not filepath.exists():
            return
        try:
            data = json.loads(filepath.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                logger.warning("Invalid memory file format for %s (not a dict)", self.agent_name)
                return

            with self._lock:
                facts = data.get("facts", {})
                if isinstance(facts, dict):
                    self._facts = {str(k): v for k, v in facts.items()}
                else:
                    logger.warning("Invalid facts format for %s, skipping", self.agent_name)

                skipped = 0
                for entry_data in data.get("short_term", []):
                    if self._validate_entry(entry_data):
                        self._short_term.append(MemoryEntry(**entry_data))
                    else:
                        skipped += 1
                for entry_data in data.get("long_term", []):
                    if self._validate_entry(entry_data):
                        self._long_term.append(MemoryEntry(**entry_data))
                    else:
                        skipped += 1

            if skipped:
                logger.warning("Skipped %d invalid memory entries for %s", skipped, self.agent_name)
            logger.info(
                "Loaded memory for %s: %d short, %d long",
                self.agent_name, len(self._short_term), len(self._long_term),
            )
        except (json.JSONDecodeError, TypeError) as exc:
            logger.warning("Corrupted memory file for %s: %s", self.agent_name, exc)
        except Exception as exc:
            logger.warning("Failed to load memory for %s: %s", self.agent_name, exc)

