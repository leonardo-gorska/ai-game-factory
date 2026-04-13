"""
GORVAX GAME FACTORY — Base Agent
Abstract base class for all AI agents with memory, event emission,
context management, and structured LLM interaction.
"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Awaitable

from backend.llm.router import LLMRouter
from backend.storage.memory import AgentMemory
from backend.storage.database import Database

logger = logging.getLogger(__name__)

# Type for event callbacks
EventCallback = Callable[[dict[str, Any]], Awaitable[None]]


@dataclass
class AgentResult:
    """Structured result from an agent execution."""
    agent_name: str
    action: str
    output: str
    success: bool = True
    error: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    tokens_used: int = 0
    latency_ms: float = 0.0
    provider: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_name": self.agent_name,
            "action": self.action,
            "output": self.output[:500],  # Truncated for events
            "success": self.success,
            "error": self.error,
            "tokens_used": self.tokens_used,
            "latency_ms": self.latency_ms,
            "provider": self.provider,
            "timestamp": self.timestamp,
        }


class BaseAgent(ABC):
    """
    Abstract base class for AI agents.

    Each agent has:
    - A name and role description
    - Memory (short-term + long-term)
    - Access to the LLM router
    - Event emission for real-time dashboard updates
    - Database logging
    """

    def __init__(
        self,
        name: str,
        role: str,
        llm_router: LLMRouter,
        database: Database,
        system_prompt: str = "",
        experience_db: Any = None,
        context_manager: Any = None,
    ) -> None:
        self.name = name
        self.role = role
        self.llm_router = llm_router
        self.database = database
        self.system_prompt = system_prompt
        self.experience_db = experience_db  # v3: Vector Memory
        self.context_manager = context_manager  # v3 Item #4: Smart Context
        self.memory = AgentMemory(agent_name=name)
        self._event_callbacks: list[EventCallback] = []
        self._is_busy = False
        self.journal: Any = None  # v3 Item #12: PipelineJournal (set externally)
        self.confidence_scorer: Any = None  # v3 Item #14: ConfidenceScorer (set externally)

    @property
    def is_busy(self) -> bool:
        return self._is_busy

    def on_event(self, callback: EventCallback) -> None:
        """Register a callback for agent events (used by WebSocket)."""
        self._event_callbacks.append(callback)

    async def _emit_event(self, event_type: str, data: dict[str, Any]) -> None:
        """Emit an event to all registered callbacks."""
        event = {
            "type": event_type,
            "agent": self.name,
            "data": data,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        for callback in self._event_callbacks:
            try:
                await callback(event)
            except Exception as exc:
                logger.warning("Event callback error: %s", exc)

    def clone(self) -> "BaseAgent":
        """Create a shallow clone with independent memory for forked tasks.

        The clone shares the LLM router and database but gets its own
        memory instance to avoid cross-contamination between forks.
        """
        import copy
        new_agent = copy.copy(self)
        # Create a fresh memory instance instead of deepcopy to avoid
        # pickle errors with non-serializable objects (_thread.lock in ChromaDB)
        new_agent.memory = AgentMemory(agent_name=self.name)
        new_agent._event_callbacks = list(self._event_callbacks)
        # Share journal and confidence scorer with clone
        new_agent.journal = self.journal
        new_agent.confidence_scorer = self.confidence_scorer
        return new_agent

    async def _call_llm(
        self,
        prompt: str,
        context: str = "",
        temperature: float = 0.7,
        max_tokens: int = 4096,
        json_mode: bool = False,
    ) -> str:
        """
        Call the LLM with the agent's system prompt and context.
        If experience_db is available, auto-injects relevant past experiences.
        Returns the response text.
        """
        # Build full system prompt
        full_system = self.system_prompt

        # v3 Item #4: Smart Context — filter by relevance if available
        if context and self.context_manager and hasattr(self.context_manager, 'select_context'):
            try:
                filtered = self.context_manager.select_context(
                    task_description=prompt[:500],
                    available_context={"context": context},
                )
                context = filtered.get("context", context)
            except Exception as exc:
                logger.debug("Context manager filtering failed: %s", exc)

        if context:
            full_system += f"\n\n## Context from Memory\n{context}"

        # v3: Auto-inject past experiences from Vector Memory
        if self.experience_db and hasattr(self.experience_db, 'is_available') and self.experience_db.is_available:
            try:
                experiences = self.experience_db.get_similar_experiences(
                    situation=prompt[:500],
                    top_k=3,
                    agent=self.name,
                )
                if experiences:
                    exp_context = self.experience_db.format_context(
                        experiences, max_chars=1500
                    )
                    full_system += f"\n\n{exp_context}"
            except Exception as exc:
                logger.debug("Experience retrieval failed: %s", exc)

        messages: list[dict[str, str]] = [
            {"role": "system", "content": full_system},
            {"role": "user", "content": prompt},
        ]

        response = await self.llm_router.complete(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            json_mode=json_mode,
        )

        # v3 Item #12: Record LLM call in journal
        if self.journal is not None and hasattr(self.journal, 'record_llm_call'):
            try:
                self.journal.record_llm_call(
                    agent_name=self.name,
                    prompt=prompt[:2000],
                    response=response.content[:2000],
                )
            except Exception:
                pass  # Journal errors must never break agent flow

        return response.content

    async def _call_llm_with_confidence(
        self,
        prompt: str,
        iteration: int = 0,
        context: str = "",
        temperature: float = 0.7,
        max_tokens: int = 4096,
        json_mode: bool = False,
    ) -> str:
        """Call LLM with automatic confidence scoring and retry.

        v3 Item #14: Extracts confidence from the response, and if below
        threshold, retries with adjusted parameters (lower temp or higher
        tier model).
        """
        response = await self._call_llm(
            prompt=prompt,
            context=context,
            temperature=temperature,
            max_tokens=max_tokens,
            json_mode=json_mode,
        )

        if self.confidence_scorer is None:
            return response

        try:
            confidence = self.confidence_scorer.extract_confidence(response)
            if confidence < 0:
                return response  # No confidence found, skip

            self.confidence_scorer.record(
                agent=self.name,
                iteration=iteration,
                confidence=confidence,
            )

            if self.confidence_scorer.should_retry(self.name, confidence):
                retry_params = self.confidence_scorer.suggest_retry_params(
                    self.name, confidence,
                )
                logger.info(
                    "🔄 %s confidence=%d < threshold, retrying with %s",
                    self.name, confidence, retry_params,
                )

                retry_response = await self._call_llm(
                    prompt=prompt,
                    context=context,
                    temperature=retry_params.get("temperature", temperature),
                    max_tokens=max_tokens,
                    json_mode=json_mode,
                )

                retry_confidence = self.confidence_scorer.extract_confidence(
                    retry_response,
                )
                self.confidence_scorer.record(
                    agent=self.name,
                    iteration=iteration,
                    confidence=max(retry_confidence, 0),
                    retried=True,
                    original_confidence=confidence,
                )

                # Use retry if it produced higher confidence
                if retry_confidence > confidence:
                    return retry_response

        except Exception as exc:
            logger.debug("Confidence scoring failed: %s", exc)

        return response

    async def _call_llm_with_history(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> str:
        """Call the LLM with a custom message history."""
        response = await self.llm_router.complete(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response.content

    @abstractmethod
    async def execute(
        self,
        iteration: int,
        input_data: dict[str, Any],
    ) -> AgentResult:
        """
        Execute the agent's main task for one iteration.

        Args:
            iteration: Current iteration number
            input_data: Data from previous agents or the pipeline

        Returns:
            AgentResult with the output and metadata
        """
        ...

    async def run(
        self,
        iteration: int,
        input_data: dict[str, Any],
    ) -> AgentResult:
        """
        Run the agent with proper lifecycle management.
        Handles status updates, error catching, and logging.
        """
        self._is_busy = True
        await self._emit_event("agent_start", {
            "iteration": iteration,
            "action": f"{self.name} starting work...",
        })

        try:
            result = await self.execute(iteration, input_data)

            # Store in memory
            importance = 8 if result.success else 6
            self.memory.add(
                action=result.action,
                content=result.output[:2000],
                iteration=iteration,
                importance=importance,
            )

            # Log to database
            await self.database.log_agent_action(
                iteration_number=iteration,
                agent_name=self.name,
                action=result.action,
                input_summary=json.dumps(input_data)[:500] if input_data else "",
                output_summary=result.output[:500],
                tokens_used=result.tokens_used,
                latency_ms=result.latency_ms,
                provider=result.provider,
            )

            await self._emit_event("agent_complete", result.to_dict())
            return result

        except Exception as exc:
            error_result = AgentResult(
                agent_name=self.name,
                action="error",
                output="",
                success=False,
                error=str(exc),
            )
            await self._emit_event("agent_error", error_result.to_dict())
            logger.error("Agent %s failed: %s", self.name, exc)
            return error_result

        finally:
            self._is_busy = False
