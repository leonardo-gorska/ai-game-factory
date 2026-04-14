"""
GORVAX GAME FACTORY — Chat Message Store
In-memory ring buffer for agent chat messages.
Provides humanized, real-time messages about what each agent is doing.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


# Agent identity for the chat UI
AGENT_PROFILES: dict[str, dict[str, str]] = {
    "researcher":       {"emoji": "🔬", "color": "#8b5cf6", "label": "Researcher"},
    "designer":         {"emoji": "🎨", "color": "#ec4899", "label": "Designer"},
    "developer":        {"emoji": "💻", "color": "#3b82f6", "label": "Developer"},
    "builder":          {"emoji": "🔨", "color": "#f59e0b", "label": "Builder"},
    "performance":      {"emoji": "⚡", "color": "#10b981", "label": "Performance"},
    "headless_tester":  {"emoji": "🖥️", "color": "#6366f1", "label": "Headless Tester"},
    "simulator":        {"emoji": "🎮", "color": "#14b8a6", "label": "Simulator"},
    "exploit_detector": {"emoji": "🛡️", "color": "#ef4444", "label": "Exploit Detector"},
    "sim_analyst":      {"emoji": "📊", "color": "#0ea5e9", "label": "Sim Analyst"},
    "economy":          {"emoji": "💰", "color": "#eab308", "label": "Economy Guardian"},
    "tester":           {"emoji": "🧪", "color": "#a855f7", "label": "Tester"},
    "critic":           {"emoji": "📝", "color": "#f97316", "label": "Critic"},
    "novelty":          {"emoji": "✨", "color": "#06b6d4", "label": "Novelty Engine"},
    "quality":          {"emoji": "📈", "color": "#22c55e", "label": "Quality Engine"},
    "stagnation":       {"emoji": "🔄", "color": "#64748b", "label": "Stagnation Guard"},
    "memory_curator":   {"emoji": "🧠", "color": "#d946ef", "label": "Memory Curator"},
    "pipeline":         {"emoji": "🏭", "color": "#94a3b8", "label": "Pipeline"},
    "system":           {"emoji": "⚙️", "color": "#475569", "label": "Sistema"},
    "terminal":         {"emoji": "🖥️", "color": "#22d3ee", "label": "Terminal"},
}


@dataclass
class ChatMessage:
    """A single chat message from an agent."""
    id: int
    agent: str
    message: str
    iteration: int
    timestamp: float
    type: str = "chat"  # chat, thinking, error, success, system
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        profile = AGENT_PROFILES.get(self.agent, AGENT_PROFILES["system"])
        return {
            "id": self.id,
            "agent": self.agent,
            "emoji": profile["emoji"],
            "color": profile["color"],
            "label": profile["label"],
            "message": self.message,
            "iteration": self.iteration,
            "timestamp": self.timestamp,
            "type": self.type,
            "metadata": self.metadata,
        }


class ChatStore:
    """Thread-safe in-memory ring buffer for chat messages."""

    MAX_MESSAGES = 500

    def __init__(self) -> None:
        self._messages: list[ChatMessage] = []
        self._next_id = 1

    def add(
        self,
        agent: str,
        message: str,
        iteration: int = 0,
        msg_type: str = "chat",
        metadata: dict[str, Any] | None = None,
    ) -> ChatMessage:
        """Add a chat message and return it."""
        msg = ChatMessage(
            id=self._next_id,
            agent=agent,
            message=message,
            iteration=iteration,
            timestamp=time.time(),
            type=msg_type,
            metadata=metadata or {},
        )
        self._next_id += 1
        self._messages.append(msg)

        # Ring buffer: trim oldest
        if len(self._messages) > self.MAX_MESSAGES:
            self._messages = self._messages[-self.MAX_MESSAGES:]

        return msg

    def get_recent(self, limit: int = 100, after_id: int = 0) -> list[dict[str, Any]]:
        """Get recent messages, optionally after a given ID."""
        filtered = [m for m in self._messages if m.id > after_id]
        return [m.to_dict() for m in filtered[-limit:]]

    def get_all(self) -> list[dict[str, Any]]:
        """Get all stored messages."""
        return [m.to_dict() for m in self._messages]


# Singleton
_chat_store: ChatStore | None = None


def get_chat_store() -> ChatStore:
    """Get the global chat store singleton."""
    global _chat_store
    if _chat_store is None:
        _chat_store = ChatStore()
    return _chat_store
