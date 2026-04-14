"""
GORVAX GAME FACTORY — Multi-Model Consensus (Roadmap v2 Item 5)

Consults 2+ LLM providers in parallel and merges their responses to
increase reliability and reduce single-model hallucinations/biases.

Only used for high-impact agents (designer, critic) and only every
N iterations to control cost.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from backend.llm.router import LLMRouter

from backend.llm.provider import LLMResponse

logger = logging.getLogger(__name__)

# Default agents that benefit from multi-model consensus
_DEFAULT_ENSEMBLE_AGENTS: set[str] = {"designer", "critic"}


@dataclass
class EnsembleResult:
    """Result of an ensemble consensus call."""

    response: LLMResponse
    n_models_queried: int
    n_models_succeeded: int
    providers_used: list[str] = field(default_factory=list)
    merge_strategy: str = ""
    total_tokens: int = 0
    total_latency_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "n_models_queried": self.n_models_queried,
            "n_models_succeeded": self.n_models_succeeded,
            "providers_used": self.providers_used,
            "merge_strategy": self.merge_strategy,
            "total_tokens": self.total_tokens,
            "total_latency_ms": self.total_latency_ms,
        }


class EnsembleRouter:
    """
    Multi-Model Consensus router.

    Dispatches the same LLM request to multiple providers in parallel
    and merges their responses to produce a more reliable result.

    Cost note: ensemble multiplies cost by n_models. Use sparingly
    for high-impact decisions only.
    """

    def __init__(
        self,
        router: LLMRouter,
        ensemble_agents: set[str] | None = None,
        interval: int = 999,  # Effectively disabled to save tokens (was 3)
        n_models: int = 2,
    ) -> None:
        """
        Args:
            router: The main LLMRouter to dispatch calls through.
            ensemble_agents: Set of agent names that should use ensemble.
                Defaults to {"designer", "critic"}.
            interval: Use ensemble every N iterations (default: 3).
            n_models: Number of models to query in parallel (default: 2).
        """
        self._router = router
        self._ensemble_agents = ensemble_agents or set(_DEFAULT_ENSEMBLE_AGENTS)
        self._interval = interval
        self._n_models = max(2, n_models)
        self._total_ensemble_calls = 0
        self._total_tokens_saved = 0  # Estimated tokens saved by avoiding bad iterations
        self._in_consensus = False  # Reentrant guard to prevent recursion

    @property
    def ensemble_agents(self) -> set[str]:
        """Set of agent names that use ensemble."""
        return self._ensemble_agents.copy()

    @property
    def interval(self) -> int:
        """How often (in iterations) ensemble is used."""
        return self._interval

    @property
    def n_models(self) -> int:
        """Number of models queried per ensemble call."""
        return self._n_models

    @property
    def stats(self) -> dict[str, Any]:
        """Ensemble usage statistics."""
        return {
            "total_ensemble_calls": self._total_ensemble_calls,
            "ensemble_agents": sorted(self._ensemble_agents),
            "interval": self._interval,
            "n_models": self._n_models,
        }

    def should_ensemble(self, agent: str, iteration: int) -> bool:
        """
        Check if ensemble should be used for this agent at this iteration.

        Returns True if:
        - The agent is in the ensemble agents set
        - The iteration is a multiple of the interval
        - There are at least 2 providers available
        """
        if agent not in self._ensemble_agents:
            return False
        if iteration <= 0:
            return False
        if iteration % self._interval != 0:
            return False
        if len(self._router.available_providers) < 2:
            return False
        if self._in_consensus:
            return False  # Prevent recursion
        return True

    def _select_diverse_providers(self, n: int) -> list[str]:
        """
        Select N diverse providers from the available pool.

        Prioritizes providers that are not on cooldown and have
        different capability tiers for maximum diversity.

        Args:
            n: Number of providers to select.

        Returns:
            List of provider names, up to min(n, available).
        """
        available = self._router.available_providers
        if not available:
            return []

        # Cap at number of available providers
        n = min(n, len(available))

        # Use the router's stats to exclude providers on cooldown
        import time as _time
        now = _time.time()
        stats = self._router.get_stats()

        # Separate into available and on-cooldown
        ready = []
        on_cooldown = []
        for p in available:
            if p in stats and stats[p].cooldown_until > now:
                on_cooldown.append(p)
            else:
                ready.append(p)

        # If we have enough ready providers, use them
        if len(ready) >= n:
            # Return first N ready providers (router already orders by capability)
            return ready[:n]

        # Otherwise, include some on-cooldown providers as fallback
        result = list(ready)
        for p in on_cooldown:
            if len(result) >= n:
                break
            result.append(p)

        return result[:n]

    async def consensus(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        json_mode: bool = False,
        n_models: int | None = None,
    ) -> EnsembleResult:
        """
        Send the same request to N providers in parallel and merge responses.

        Args:
            messages: Chat messages in OpenAI format.
            temperature: Sampling temperature.
            max_tokens: Maximum tokens per response.
            json_mode: Request JSON output format.
            n_models: Override the default number of models.

        Returns:
            EnsembleResult with the merged response and metadata.
        """
        n = n_models or self._n_models
        providers = self._select_diverse_providers(n)

        if len(providers) < 2:
            # Fallback: single model call (no consensus possible)
            logger.warning(
                "Ensemble: only %d provider(s) available, falling back to single model",
                len(providers),
            )
            response = await self._router.complete(
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                json_mode=json_mode,
            )
            return EnsembleResult(
                response=response,
                n_models_queried=1,
                n_models_succeeded=1,
                providers_used=[response.provider],
                merge_strategy="single_fallback",
                total_tokens=response.usage.get("total_tokens", 0),
                total_latency_ms=response.latency_ms,
            )

        # Dispatch to all providers in parallel
        t_start = time.monotonic()

        # Set reentrant guard to prevent router.complete() from
        # recursively dispatching back to ensemble
        self._in_consensus = True
        try:
            tasks = [
                self._router.complete(
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    json_mode=json_mode,
                    preferred_provider=p,
                )
                for p in providers
            ]

            # Gather with return_exceptions to handle partial failures
            results = await asyncio.gather(*tasks, return_exceptions=True)
        finally:
            self._in_consensus = False

        total_latency = (time.monotonic() - t_start) * 1000

        # Separate successes from failures
        responses: list[LLMResponse] = []
        used_providers: list[str] = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.warning(
                    "Ensemble: provider %s failed: %s",
                    providers[i], str(result)[:200],
                )
            else:
                responses.append(result)
                used_providers.append(providers[i])

        if not responses:
            raise RuntimeError(
                f"Ensemble: all {len(providers)} providers failed"
            )

        if len(responses) == 1:
            # Only one succeeded — use it directly
            logger.info(
                "Ensemble: only 1/%d providers succeeded, using single response",
                len(providers),
            )
            merged = responses[0]
            strategy = "single_survivor"
        else:
            # Merge multiple responses
            merged, strategy = self._merge_responses(responses, json_mode)

        # Compute total tokens
        total_tokens = sum(
            r.usage.get("total_tokens", 0) for r in responses
        )

        self._total_ensemble_calls += 1

        logger.info(
            "🎯 Ensemble consensus: %d/%d providers, strategy=%s, tokens=%d",
            len(responses), len(providers), strategy, total_tokens,
        )

        return EnsembleResult(
            response=merged,
            n_models_queried=len(providers),
            n_models_succeeded=len(responses),
            providers_used=used_providers,
            merge_strategy=strategy,
            total_tokens=total_tokens,
            total_latency_ms=total_latency,
        )

    def _merge_responses(
        self,
        responses: list[LLMResponse],
        json_mode: bool = False,
    ) -> tuple[LLMResponse, str]:
        """
        Merge multiple LLM responses into a single best response.

        Strategies:
        - JSON mode: parse both, merge fields with consensus
        - Text mode: pick the longest/most complete response

        Returns:
            Tuple of (merged LLMResponse, strategy name).
        """
        if json_mode:
            return self._merge_json_responses(responses)
        return self._merge_text_responses(responses)

    def _merge_json_responses(
        self,
        responses: list[LLMResponse],
    ) -> tuple[LLMResponse, str]:
        """
        Merge JSON responses by parsing and combining fields.

        Strategy: try to parse all responses as JSON. For each field,
        if values agree → keep the consensus value. If they disagree →
        keep the value from the response with highest total tokens
        (proxy for more detailed/thorough response).

        Falls back to text merge if JSON parsing fails.
        """
        from backend.utils.json_parser import extract_json_from_response

        parsed: list[tuple[dict[str, Any], LLMResponse]] = []
        for resp in responses:
            try:
                data = extract_json_from_response(resp.content, fallback=None)
                if data is not None and isinstance(data, dict):
                    parsed.append((data, resp))
            except Exception:
                pass

        if len(parsed) < 2:
            # Could not parse enough JSON responses — fall back to text merge
            return self._merge_text_responses(responses)

        # Start with the most detailed response (highest token count)
        parsed.sort(
            key=lambda x: x[1].usage.get("total_tokens", 0),
            reverse=True,
        )
        base_data, base_resp = parsed[0]

        # Merge fields from other responses
        for other_data, _ in parsed[1:]:
            for key, value in other_data.items():
                if key not in base_data:
                    # New field from another model — include it
                    base_data[key] = value

        # Build merged content
        merged_content = json.dumps(base_data, indent=2, ensure_ascii=False)
        merged_usage = self._combine_usage(responses)

        merged = LLMResponse(
            content=merged_content,
            provider=f"ensemble({','.join(r.provider for r in responses)})",
            model=f"ensemble({','.join(r.model for r in responses)})",
            usage=merged_usage,
            latency_ms=max(r.latency_ms for r in responses),
        )
        return merged, "json_merge"

    def _merge_text_responses(
        self,
        responses: list[LLMResponse],
    ) -> tuple[LLMResponse, str]:
        """
        Merge text responses by selecting the most complete one.

        Strategy: pick the response with the most content (longest),
        as a proxy for thoroughness and completeness.
        """
        # Sort by content length (descending) — longest = most thorough
        sorted_responses = sorted(
            responses,
            key=lambda r: len(r.content),
            reverse=True,
        )

        best = sorted_responses[0]
        merged_usage = self._combine_usage(responses)

        merged = LLMResponse(
            content=best.content,
            provider=f"ensemble({','.join(r.provider for r in responses)})",
            model=f"ensemble({','.join(r.model for r in responses)})",
            usage=merged_usage,
            latency_ms=max(r.latency_ms for r in responses),
        )
        return merged, "text_longest"

    @staticmethod
    def _combine_usage(responses: list[LLMResponse]) -> dict[str, int]:
        """Combine usage stats from multiple responses (sum all tokens)."""
        combined: dict[str, int] = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }
        for r in responses:
            combined["prompt_tokens"] += r.usage.get("prompt_tokens", 0)
            combined["completion_tokens"] += r.usage.get("completion_tokens", 0)
            combined["total_tokens"] += r.usage.get("total_tokens", 0)
        return combined
