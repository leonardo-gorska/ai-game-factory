"""
GORVAX GAME FACTORY — LLM Router v3
Intelligent load balancer with smart routing (cost × latency × complexity),
automatic failover, rate limit tracking, and retry logic.
"""

from __future__ import annotations

import os

import asyncio
import litellm
import logging
import random
import time
from collections import defaultdict
from dataclasses import dataclass
from enum import Enum
from typing import Any, TYPE_CHECKING

from backend.config import get_config
from backend.llm.provider import LLMProvider, LLMResponse

if TYPE_CHECKING:
    from backend.core.cost_guard import CostGuard
    from backend.core.temperature_controller import TemperatureController
    from backend.llm.cost_optimizer import CostOptimizer

logger = logging.getLogger(__name__)


# ── Smart Routing Strategy ─────────────────────────────

class RoutingMode(str, Enum):
    ROUND_ROBIN = "round_robin"
    SMART = "smart"


# Agent complexity tiers: higher = needs better model
_AGENT_COMPLEXITY: dict[str, float] = {
    "designer": 0.9,           # Creative, needs strong reasoning
    "developer": 0.8,          # Code generation, needs quality
    "critic": 0.85,            # Analysis, needs nuance
    "researcher": 0.75,        # Feature research and innovation proposals
    "economy_guardian": 0.70,  # Economy analysis, numerical reasoning
    "simulation_analyst": 0.65,# Interpret simulation data
    "tester": 0.6,             # Structured analysis
    "memory_curator": 0.55,    # Pattern recognition in memory
    "performance": 0.5,        # Pattern matching
    "builder": 0.2,            # Simple command execution
    "unknown": 0.5,
}

# Provider capability tiers: higher = more capable (base scores)
_PROVIDER_CAPABILITY: dict[str, float] = {
    "sambanova": 0.92,    # DeepSeek V3.1: best free model, great JSON + coding
    "gemini": 0.90,       # Gemini 2.0 Flash: strongest (disabled — quota 0)
    "openrouter": 0.85,   # Qwen3 Coder: good but often rate-limited
    "mistral": 0.75,      # Mistral Small 24B: solid mid-tier (paid)
    "cerebras": 0.55,     # Llama 8B: ultra-fast but small (free tier)
    "groq": 0.55,         # Llama 8B: fast but 6000 TPM limit
}

# BE-16: Minimum calls before dynamic scoring kicks in
_DYNAMIC_SCORE_MIN_CALLS = 10

# Estimated cost per 1K tokens (USD)
_PROVIDER_COST_PER_1K: dict[str, float] = {
    "gemini": 0.0001,     # Near free tier
    "groq": 0.0003,       # Budget
    "mistral": 0.002,     # Premium
    "openrouter": 0.0001, # Free tier model
}


@dataclass
class ProviderStats:
    """Tracks usage stats for a single provider."""
    total_calls: int = 0
    total_errors: int = 0
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    last_call_time: float = 0.0
    last_error_time: float = 0.0
    consecutive_errors: int = 0
    cooldown_until: float = 0.0  # Timestamp when cooldown ends
    avg_latency: float = 0.0    # Rolling average latency in seconds
    _latency_count: int = 0     # Number of latency samples


class LLMRouter:
    """
    Routes LLM requests across multiple providers with:
    - Smart routing (cost × latency × complexity)
    - Automatic failover on errors
    - Exponential backoff on rate limits
    - Usage tracking per provider
    - Cost tracking via CostGuard integration
    - A/B testing (10% of calls to alternative provider)
    """

    def __init__(
        self,
        provider: LLMProvider | None = None,
        cost_guard: CostGuard | None = None,
        routing_mode: RoutingMode = RoutingMode.SMART,
        ab_test_ratio: float = 0.0,  # Disabled to save tokens (was 0.10)
    ) -> None:
        self._provider = provider or LLMProvider()
        self._config = get_config().llm
        self._providers = self._config.available_providers()
        self._stats: dict[str, ProviderStats] = defaultdict(ProviderStats)
        self._current_index = 0
        self._max_retries = 3
        self._base_cooldown = 20.0  # seconds (was 60)
        self._rate_limit_cooldown = 30.0  # cooldown for rate limits (free-tier APIs reset ~1RPM)
        self._cost_guard = cost_guard
        self._current_agent: str = "unknown"
        self._current_iteration: int = 0
        self._temperature_override: float | None = None
        self._tier_override: str | None = None
        self._routing_mode = routing_mode
        self._ab_test_ratio = ab_test_ratio

        # Smart routing weights
        self._w_cost = 0.35
        self._w_latency = 0.25
        self._w_quality = 0.40

        # BE-16: Dynamic capability scores adjusted by real performance
        self._dynamic_capability: dict[str, float] = dict(_PROVIDER_CAPABILITY)

        # v2 Roadmap Item 11: Runtime model overrides (hot-swap)
        self._runtime_overrides: dict[str, str] = {}

        # v2 Roadmap Item 5: Ensemble router reference (set externally)
        self._ensemble_router: Any = None

        # v3 Roadmap Item 7: Dynamic Agent Temperature Controller
        self._temperature_controller: TemperatureController | None = None

        # v3 Roadmap Item 11: Cost-Aware Routing Intelligence
        self._cost_optimizer: CostOptimizer | None = None

        if not self._providers:
            logger.warning(
                "No LLM providers configured! Add API keys to .env"
            )

    def set_context(
        self,
        agent: str,
        iteration: int,
        temperature_override: float | None = None,
        tier_override: str | None = None,
    ) -> None:
        """Set the current agent and iteration for cost tracking.

        Args:
            agent: Agent name for routing and cost tracking.
            iteration: Current pipeline iteration number.
            temperature_override: If set, overrides the temperature passed
                to ``complete()`` for subsequent calls.
            tier_override: ``"default"`` or ``"premium"``. When ``"premium"``,
                the smart router will prefer higher-capability providers.
        """
        self._current_agent = agent
        self._current_iteration = iteration
        self._temperature_override = temperature_override
        self._tier_override = tier_override

    def clear_overrides(self) -> None:
        """Reset temperature and tier overrides to None."""
        self._temperature_override = None
        self._tier_override = None

    @property
    def available_providers(self) -> list[str]:
        """List of configured providers."""
        return list(self._providers)

    def get_stats(self) -> dict[str, ProviderStats]:
        """Get usage stats for all providers."""
        return dict(self._stats)

    def _get_next_provider(self) -> str | None:
        """Get the next available provider using current routing mode."""
        if self._routing_mode == RoutingMode.SMART and len(self._providers) > 1:
            chosen = self._smart_select()
            if chosen:
                return chosen

        # Fallback: round-robin
        return self._round_robin_select()

    def _round_robin_select(self) -> str | None:
        """Classic round-robin provider selection."""
        now = time.time()
        checked = 0

        while checked < len(self._providers):
            provider = self._providers[self._current_index]
            self._current_index = (self._current_index + 1) % len(self._providers)
            checked += 1

            stats = self._stats[provider]
            if stats.cooldown_until <= now:
                return provider

        # All on cooldown — return the one with earliest cooldown end
        return min(
            self._providers,
            key=lambda p: self._stats[p].cooldown_until,
        )

    # ── Runtime model overrides (Roadmap v2 Item 11) ──────

    def set_agent_override(self, agent_name: str, provider: str) -> None:
        """Set a runtime model override for an agent (hot-swap)."""
        self._runtime_overrides[agent_name] = provider
        logger.info(
            "🔄 Runtime override set: %s → %s", agent_name, provider,
        )

    def remove_agent_override(self, agent_name: str) -> None:
        """Remove a runtime model override for an agent."""
        self._runtime_overrides.pop(agent_name, None)
        logger.info("🔄 Runtime override removed: %s", agent_name)

    def get_agent_overrides(self) -> dict[str, str]:
        """Return all current runtime overrides."""
        return self._runtime_overrides.copy()

    # ── Ensemble integration (Roadmap v2 Item 5) ──────────

    def set_ensemble_router(self, ensemble_router: Any) -> None:
        """Set the ensemble router for multi-model consensus."""
        self._ensemble_router = ensemble_router
        logger.info("🎯 Ensemble router registered on LLMRouter")

    @property
    def ensemble_router(self) -> Any:
        """Return the ensemble router, or None if not set."""
        return self._ensemble_router

    # ── Dynamic Temperature (Roadmap v3 Item 7) ───────────

    def set_temperature_controller(self, controller: TemperatureController) -> None:
        """Set the dynamic temperature controller for per-agent adjustments."""
        self._temperature_controller = controller
        logger.info("🌡️ Temperature controller registered on LLMRouter")

    def set_cost_optimizer(self, optimizer: CostOptimizer) -> None:
        """Set the cost optimizer for ROI-based routing bonuses."""
        self._cost_optimizer = optimizer
        logger.info("💰 Cost optimizer registered on LLMRouter")

    def _smart_select(self) -> str | None:
        """
        Intelligent provider selection based on:
        - Agent model overrides (forced provider for critical agents)
        - Task complexity (from agent name)
        - Provider capability, cost, and latency
        - A/B testing ratio
        """
        # Check for runtime override first (hot-swap, Roadmap Item 11)
        runtime_override = self._runtime_overrides.get(self._current_agent)
        if runtime_override and runtime_override in self._providers:
            now_rt = time.time()
            if self._stats[runtime_override].cooldown_until <= now_rt:
                logger.info(
                    "🔄 Runtime override: %s → %s (hot-swap)",
                    self._current_agent, runtime_override,
                )
                return runtime_override
            else:
                logger.warning(
                    "Runtime override provider %s on cooldown for %s, falling back",
                    runtime_override, self._current_agent,
                )

        # Check for forced provider override (critical agents)
        override = self._config.get_agent_override(self._current_agent)
        if override and override in self._providers:
            now = time.time()
            if self._stats[override].cooldown_until <= now:
                logger.info(
                    "🎯 Agent override: %s → %s (bypassing smart routing)",
                    self._current_agent, override,
                )
                return override
            else:
                logger.warning(
                    "Override provider %s on cooldown for %s, falling back to smart routing",
                    override, self._current_agent,
                )

        now = time.time()
        available = [
            p for p in self._providers
            if self._stats[p].cooldown_until <= now
        ]
        if not available:
            return None

        # Get task complexity (boosted for premium tier override)
        complexity = _AGENT_COMPLEXITY.get(self._current_agent, 0.5)
        if self._tier_override == "premium":
            complexity = max(complexity, 0.95)

        # Score each available provider
        scored: list[tuple[str, float]] = []
        for provider in available:
            score = self._score_provider(provider, complexity)
            scored.append((provider, score))

        scored.sort(key=lambda x: x[1], reverse=True)
        best_provider = scored[0][0]

        # A/B testing: X% chance to pick a random alternative
        if (
            len(scored) > 1
            and random.random() < self._ab_test_ratio
        ):
            alt_provider = random.choice([
                p for p, _ in scored[1:]
            ])
            logger.debug(
                "A/B test: using %s instead of %s for %s",
                alt_provider, best_provider, self._current_agent,
            )
            return alt_provider

        logger.debug(
            "Smart route: %s → %s (complexity=%.2f, score=%.3f)",
            self._current_agent, best_provider, complexity, scored[0][1],
        )
        return best_provider

    def _score_provider(self, provider: str, task_complexity: float) -> float:
        """
        Score a provider for the current task.

        Score = w_quality * quality_match
              + w_cost * cost_efficiency
              + w_latency * speed_score

        For high-complexity tasks, quality_match weighs more.
        For low-complexity tasks, cost_efficiency weighs more.
        """
        stats = self._stats[provider]
        # BE-16: Use dynamic capability score (adjusted by real performance)
        capability = self._dynamic_capability.get(provider, 0.5)
        cost_per_1k = _PROVIDER_COST_PER_1K.get(provider, 0.001)

        # Quality match: how well capability matches task complexity
        # High-complexity + high-capability = good match
        quality_match = 1.0 - abs(capability - task_complexity)

        # Cost efficiency: inverse of cost (normalized 0-1)
        max_cost = max(_PROVIDER_COST_PER_1K.values()) or 0.01
        cost_efficiency = 1.0 - (cost_per_1k / max_cost)

        # Speed score: based on actual measured latency
        if stats.avg_latency > 0:
            # Lower latency = higher score (cap at 10s)
            speed_score = max(0.0, 1.0 - (stats.avg_latency / 10.0))
        else:
            speed_score = 0.5  # Unknown = neutral

        # Adjust weights based on complexity
        # Simple tasks → favor cost; Complex tasks → favor quality
        w_quality = self._w_quality * (0.5 + task_complexity)
        w_cost = self._w_cost * (1.5 - task_complexity)
        w_latency = self._w_latency
        w_total = w_quality + w_cost + w_latency

        score = (
            w_quality * quality_match
            + w_cost * cost_efficiency
            + w_latency * speed_score
        ) / w_total

        # Bonus for high success rate
        if stats.total_calls > 5:
            success_rate = 1.0 - (stats.total_errors / stats.total_calls)
            score *= (0.8 + 0.2 * success_rate)

        # v3 Item 11: Cost-Aware Routing bonus from ROI history
        if self._cost_optimizer is not None:
            routing_bonus = self._cost_optimizer.get_routing_bonus(
                self._current_agent, provider,
            )
            score += routing_bonus

        return score

    def _update_dynamic_scores(self) -> None:
        """
        BE-16: Update dynamic capability scores based on real performance.
        Blends the base capability with the observed success rate.
        """
        for provider in self._providers:
            stats = self._stats[provider]
            if stats.total_calls < _DYNAMIC_SCORE_MIN_CALLS:
                continue
            base = _PROVIDER_CAPABILITY.get(provider, 0.5)
            success_rate = 1.0 - (stats.total_errors / stats.total_calls)
            # Blend: 60% base + 40% real performance
            self._dynamic_capability[provider] = round(
                0.6 * base + 0.4 * success_rate, 3
            )

    def get_routing_info(self) -> dict[str, object]:
        """Get current routing configuration and stats."""
        return {
            "mode": self._routing_mode.value,
            "ab_test_ratio": self._ab_test_ratio,
            "weights": {
                "cost": self._w_cost,
                "latency": self._w_latency,
                "quality": self._w_quality,
            },
            "agent_complexity": dict(_AGENT_COMPLEXITY),
            "provider_capability": dict(self._dynamic_capability),
        }

    def _apply_cooldown(self, provider: str) -> None:
        """Apply exponential backoff cooldown to a provider."""
        stats = self._stats[provider]
        stats.consecutive_errors += 1
        stats.last_error_time = time.time()

        # Exponential backoff: 20s, 40s, 80s, max 120s
        cooldown = min(
            self._base_cooldown * (2 ** (stats.consecutive_errors - 1)),
            120.0,
        )
        stats.cooldown_until = time.time() + cooldown

        logger.warning(
            "Provider %s on cooldown for %.0fs (consecutive errors: %d)",
            provider,
            cooldown,
            stats.consecutive_errors,
        )

    def _record_success(self, provider: str, response: LLMResponse, latency: float = 0.0) -> None:
        """Record a successful call and track costs."""
        stats = self._stats[provider]
        stats.total_calls += 1
        total_tokens = response.usage.get("total_tokens", 0)
        stats.total_tokens += total_tokens
        stats.last_call_time = time.time()
        stats.consecutive_errors = 0  # Reset on success

        # Track rolling average latency
        if latency > 0:
            stats._latency_count += 1
            stats.avg_latency += (latency - stats.avg_latency) / stats._latency_count

        # Cost tracking
        if self._cost_guard:
            input_tokens = response.usage.get("prompt_tokens", 0)
            output_tokens = response.usage.get("completion_tokens", 0)
            entry = self._cost_guard.record(
                agent=self._current_agent,
                provider=provider,
                tokens_input=input_tokens,
                tokens_output=output_tokens,
                iteration=self._current_iteration,
            )
            stats.total_cost_usd += entry.estimated_cost_usd

        # BE-16: Update dynamic scores after each success
        self._update_dynamic_scores()

        # v3 Item 11: Record call for cost optimizer
        if self._cost_optimizer is not None:
            self._cost_optimizer.record_call(
                agent=self._current_agent,
                provider=provider,
                cost_usd=stats.total_cost_usd,
                latency=latency,
                tokens=total_tokens,
            )

    async def complete(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        json_mode: bool = False,
        preferred_provider: str | None = None,
    ) -> LLMResponse:
        """
        Send a completion request with automatic provider rotation and failover.

        Args:
            messages: Chat messages in OpenAI format
            temperature: Sampling temperature
            max_tokens: Maximum tokens
            json_mode: Request JSON output
            preferred_provider: Optional preferred provider to try first

        Returns:
            LLMResponse from whichever provider succeeds

        Raises:
            RuntimeError: If all providers fail
        """
        if not self._providers:
            raise RuntimeError(
                "No LLM providers configured. Add API keys to .env file."
            )

        # ── v2 Roadmap Item 5: Ensemble auto-dispatch ─────
        if (
            self._ensemble_router is not None
            and self._ensemble_router.should_ensemble(
                self._current_agent, self._current_iteration
            )
        ):
            logger.info(
                "🎯 Ensemble mode for agent=%s iter=%d",
                self._current_agent, self._current_iteration,
            )
            result = await self._ensemble_router.consensus(
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                json_mode=json_mode,
            )
            return result.response

        # ── Pre-call cost prediction ──────────────────
        if self._cost_guard:
            from backend.llm.cost_predictor import CostPredictor

            _predictor = CostPredictor()
            _remaining = (
                self._cost_guard.budget.max_total_usd
                - self._cost_guard._total_cost
            )
            _prediction = _predictor.check(
                provider=self._get_next_provider() or "unknown",
                messages=messages,
                max_tokens=max_tokens,
                budget_remaining=_remaining,
            )
            if _prediction.warning:
                logger.warning("💰 %s", _prediction.warning)

        # Build provider order: preferred first, then round-robin
        providers_to_try: list[str] = []
        if preferred_provider and preferred_provider in self._providers:
            providers_to_try.append(preferred_provider)

        # Always add the smart-selected provider first
        smart_pick = self._get_next_provider()
        if smart_pick and smart_pick not in providers_to_try:
            providers_to_try.append(smart_pick)

        # Then add ALL remaining providers as fallbacks
        for p in self._providers:
            if p not in providers_to_try:
                providers_to_try.append(p)

        last_error: Exception | None = None

        # Global exhaustion check: if ALL providers are on cooldown, wait for soonest
        now = time.time()
        all_on_cooldown = all(
            self._stats[p].cooldown_until > now for p in providers_to_try
        )
        if all_on_cooldown:
            soonest = min(self._stats[p].cooldown_until for p in providers_to_try)
            wait_all = soonest - now
            if wait_all > 0:
                logger.warning(
                    "⚠️ All %d providers exhausted! Waiting %.0fs for soonest recovery...",
                    len(providers_to_try), wait_all,
                )
                await asyncio.sleep(min(wait_all, 60.0))  # Cap at 60s

        for provider in providers_to_try:
            # Wait for cooldown if necessary
            stats = self._stats[provider]
            now = time.time()
            if stats.cooldown_until > now:
                wait_time = stats.cooldown_until - now
                if wait_time <= 35.0:  # Wait up to 35s for rate-limited free tiers
                    logger.info("Waiting %.1fs for %s cooldown...", wait_time, provider)
                    await asyncio.sleep(wait_time)
                else:
                    logger.debug("Skipping %s (cooldown %.0fs)", provider, wait_time)
                    continue

            try:
                # SEC-06: Truncate prompt/response content in production logs
                _is_prod = os.getenv("GORVAX_ENV", "development").lower() == "production"
                if not _is_prod:
                    _preview = str(messages[-1].get("content", ""))[:100] if messages else ""
                    logger.debug(
                        "LLM request to %s: %s...",
                        provider, _preview,
                    )

                # Apply temperature override if set via set_context
                effective_temp = self._temperature_override if self._temperature_override is not None else temperature

                # v3 Item 7: Dynamic temperature adjustment (if no explicit override)
                if (
                    self._temperature_override is None
                    and self._temperature_controller is not None
                ):
                    effective_temp = self._temperature_controller.get_temperature(
                        self._current_agent, effective_temp,
                    )

                t_start = time.monotonic()
                response = await self._provider.complete(
                    messages=messages,
                    provider=provider,
                    temperature=effective_temp,
                    max_tokens=max_tokens,
                    json_mode=json_mode,
                )
                call_latency = time.monotonic() - t_start
                self._record_success(provider, response, latency=call_latency)

                if not _is_prod:
                    logger.debug(
                        "LLM response from %s: %s...",
                        provider, response.content[:100],
                    )

                return response

            except Exception as exc:
                last_error = exc
                stats.total_errors += 1
                err_str = str(exc).lower()

                # Classify error type
                is_rate_limit = any(k in err_str for k in [
                    "429", "402", "rate_limit", "resource_exhausted",
                    "quota", "too many requests",
                    "credits", "afford",
                ])
                is_context_window = any(k in err_str for k in [
                    "context_length", "context window", "token limit",
                    "maximum context", "too long", "max_tokens",
                    "input is too long", "exceeds the model",
                ])

                if is_rate_limit and not is_context_window:
                    # True rate limit: cooldown and move to next provider
                    stats.cooldown_until = time.time() + self._rate_limit_cooldown
                    logger.info(
                        "Provider %s rate-limited, will retry in %.0fs",
                        provider, self._rate_limit_cooldown,
                    )
                elif is_context_window:
                    # Context window exceeded: long cooldown, try smaller fallback models
                    stats.cooldown_until = time.time() + 60.0
                    logger.warning(
                        "Provider %s context window exceeded, cooldown 60s. Trying fallbacks...",
                        provider,
                    )
                    fallback_models = self._config.get_fallback_models(provider)
                    for fb_model in fallback_models:
                        try:
                            logger.info(
                                "🔄 Trying fallback model %s for provider %s...",
                                fb_model, provider,
                            )
                            fb_kwargs: dict[str, Any] = {
                                "model": fb_model,
                                "messages": messages,
                                "temperature": temperature,
                                "max_tokens": max_tokens,
                                "timeout": 60.0,
                                "max_retries": 0,
                            }
                            t_fb = time.monotonic()
                            fb_resp = await litellm.acompletion(**fb_kwargs)
                            fb_latency = time.monotonic() - t_fb

                            content = fb_resp.choices[0].message.content or ""
                            usage = {}
                            if fb_resp.usage:
                                usage = {
                                    "prompt_tokens": fb_resp.usage.prompt_tokens or 0,
                                    "completion_tokens": fb_resp.usage.completion_tokens or 0,
                                    "total_tokens": fb_resp.usage.total_tokens or 0,
                                }
                            response = LLMResponse(
                                content=content,
                                provider=provider,
                                model=fb_model,
                                usage=usage,
                                latency_ms=fb_latency * 1000,
                            )
                            self._record_success(provider, response, latency=fb_latency)
                            logger.info(
                                "✅ Fallback model %s succeeded for provider %s",
                                fb_model, provider,
                            )
                            return response
                        except Exception as fb_exc:
                            logger.warning(
                                "Fallback model %s also failed: %s",
                                fb_model, str(fb_exc)[:150],
                            )
                else:
                    # Other errors: try fallback models, then apply exponential backoff
                    fallback_models = self._config.get_fallback_models(provider)
                    for fb_model in fallback_models:
                        try:
                            logger.info(
                                "🔄 Trying fallback model %s for provider %s...",
                                fb_model, provider,
                            )
                            fb_kwargs = {
                                "model": fb_model,
                                "messages": messages,
                                "temperature": temperature,
                                "max_tokens": max_tokens,
                                "timeout": 60.0,
                                "max_retries": 0,
                            }
                            t_fb = time.monotonic()
                            fb_resp = await litellm.acompletion(**fb_kwargs)
                            fb_latency = time.monotonic() - t_fb

                            content = fb_resp.choices[0].message.content or ""
                            usage = {}
                            if fb_resp.usage:
                                usage = {
                                    "prompt_tokens": fb_resp.usage.prompt_tokens or 0,
                                    "completion_tokens": fb_resp.usage.completion_tokens or 0,
                                    "total_tokens": fb_resp.usage.total_tokens or 0,
                                }
                            response = LLMResponse(
                                content=content,
                                provider=provider,
                                model=fb_model,
                                usage=usage,
                                latency_ms=fb_latency * 1000,
                            )
                            self._record_success(provider, response, latency=fb_latency)
                            logger.info(
                                "✅ Fallback model %s succeeded for provider %s",
                                fb_model, provider,
                            )
                            return response
                        except Exception as fb_exc:
                            logger.warning(
                                "Fallback model %s also failed: %s",
                                fb_model, str(fb_exc)[:150],
                            )
                    self._apply_cooldown(provider)
                logger.warning(
                    "Provider %s failed: %s — trying next...",
                    provider,
                    str(exc)[:200],
                )

        raise RuntimeError(
            f"All LLM providers failed. Last error: {last_error}"
        )

    async def complete_text(
        self,
        prompt: str,
        system_prompt: str = "",
        temperature: float = 0.7,
        max_tokens: int = 4096,
        preferred_provider: str | None = None,
    ) -> str:
        """
        Convenience method: send a text prompt, get a text response,
        with automatic provider rotation.
        """
        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        response = await self.complete(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            preferred_provider=preferred_provider,
        )
        return response.content
