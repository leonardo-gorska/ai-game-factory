"""
GORVAX GAME FACTORY — LLM Provider
Unified wrapper around LiteLLM for multi-provider LLM access.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

import litellm

from backend.config import get_config, LLMConfig

logger = logging.getLogger(__name__)

# Suppress LiteLLM's verbose logging
litellm.suppress_debug_info = True


@dataclass
class LLMResponse:
    """Structured response from an LLM call."""
    content: str
    provider: str
    model: str
    usage: dict[str, int] = field(default_factory=dict)
    latency_ms: float = 0.0


class LLMProvider:
    """
    Wrapper around LiteLLM that handles authentication,
    retries, and structured responses for any supported provider.
    """

    def __init__(self, config: LLMConfig | None = None) -> None:
        self._config = config or get_config().llm
        self._setup_api_keys()

    def _setup_api_keys(self) -> None:
        """Set API keys as environment variables for LiteLLM."""
        import os
        if self._config.gemini_api_key:
            os.environ["GEMINI_API_KEY"] = self._config.gemini_api_key
        if self._config.sambanova_api_key:
            os.environ["SAMBANOVA_API_KEY"] = self._config.sambanova_api_key
        if self._config.cerebras_api_key:
            os.environ["CEREBRAS_API_KEY"] = self._config.cerebras_api_key
        if self._config.groq_api_key:
            os.environ["GROQ_API_KEY"] = self._config.groq_api_key
        if self._config.mistral_api_key:
            os.environ["MISTRAL_API_KEY"] = self._config.mistral_api_key
        if self._config.openrouter_api_key:
            os.environ["OPENROUTER_API_KEY"] = self._config.openrouter_api_key

    @staticmethod
    def _sanitize_text(text: str) -> str:
        """Remove surrogate characters that break UTF-8 encoding for LLM APIs."""
        # encode to utf-8 replacing surrogates, then decode back
        return text.encode("utf-8", errors="surrogatepass").decode(
            "utf-8", errors="replace"
        )

    def _sanitize_messages(
        self, messages: list[dict[str, str]]
    ) -> list[dict[str, str]]:
        """Sanitize all message content to avoid encoding errors."""
        clean: list[dict[str, str]] = []
        for msg in messages:
            clean.append({
                k: self._sanitize_text(v) if isinstance(v, str) else v
                for k, v in msg.items()
            })
        return clean

    async def complete(
        self,
        messages: list[dict[str, str]],
        provider: str = "gemini",
        temperature: float = 0.7,
        max_tokens: int = 4096,
        json_mode: bool = False,
        timeout: float = 60.0,
    ) -> LLMResponse:
        """
        Send a completion request to the specified LLM provider.

        Args:
            messages: Chat messages in OpenAI format [{"role": ..., "content": ...}]
            provider: Which provider to use ("gemini", "groq", "mistral", "openrouter")
            temperature: Sampling temperature (0.0 - 1.0)
            max_tokens: Maximum tokens in the response
            json_mode: If True, request JSON output format

        Returns:
            LLMResponse with the completion content and metadata
        """
        model = self._config.get_model(provider)

        # Sanitize messages to prevent surrogate encoding errors
        safe_messages = self._sanitize_messages(messages)

        kwargs: dict[str, Any] = {
            "model": model,
            "messages": safe_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "timeout": timeout,  # Prevent infinite hangs on slow providers
            "max_retries": 0,   # Disable OpenAI SDK internal retries (num_retries only controls LiteLLM)
        }

        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        start = time.perf_counter()

        try:
            response = await litellm.acompletion(**kwargs)
            latency_ms = (time.perf_counter() - start) * 1000

            content = response.choices[0].message.content or ""
            usage = {}
            if response.usage:
                usage = {
                    "prompt_tokens": response.usage.prompt_tokens or 0,
                    "completion_tokens": response.usage.completion_tokens or 0,
                    "total_tokens": response.usage.total_tokens or 0,
                }

            logger.info(
                "LLM call OK | provider=%s model=%s tokens=%d latency=%.0fms",
                provider,
                model,
                usage.get("total_tokens", 0),
                latency_ms,
            )

            return LLMResponse(
                content=content,
                provider=provider,
                model=model,
                usage=usage,
                latency_ms=latency_ms,
            )

        except Exception as exc:
            latency_ms = (time.perf_counter() - start) * 1000
            logger.error(
                "LLM call FAILED | provider=%s model=%s error=%s latency=%.0fms",
                provider,
                model,
                str(exc),
                latency_ms,
            )
            raise

    async def complete_text(
        self,
        prompt: str,
        system_prompt: str = "",
        provider: str = "gemini",
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> str:
        """
        Convenience method: send a text prompt and get a text response.

        Args:
            prompt: The user prompt
            system_prompt: Optional system prompt
            provider: Which provider to use
            temperature: Sampling temperature
            max_tokens: Maximum tokens

        Returns:
            The completion text content
        """
        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        response = await self.complete(
            messages=messages,
            provider=provider,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response.content
