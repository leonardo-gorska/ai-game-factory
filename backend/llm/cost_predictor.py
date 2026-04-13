"""
GORVAX GAME FACTORY — LLM Cost Predictor
Estimates the cost of an LLM call *before* it is made, so the pipeline
can log a warning when predicted spend exceeds the remaining budget.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from backend.core.cost_guard import COST_PER_MILLION_TOKENS

logger = logging.getLogger(__name__)

# Fallback pricing for unknown providers (USD per 1M tokens)
_FALLBACK_RATE: dict[str, float] = {"input": 0.10, "output": 0.10}


@dataclass
class CostPrediction:
    """Result of a pre-call cost estimation."""

    estimated_input_tokens: int
    estimated_output_tokens: int
    estimated_cost_usd: float
    budget_remaining_usd: float
    over_budget: bool
    warning: str | None


class CostPredictor:
    """Estimates LLM call cost before execution.

    Token estimation uses the chars/4 heuristic (roughly matching
    byte-pair-encoding for English/code text). Cost is looked up
    from the same pricing table used by ``CostGuard``.
    """

    # ── Token estimation ──────────────────────────────

    @staticmethod
    def estimate_tokens(
        messages: list[dict[str, str]],
        max_tokens: int = 4096,
    ) -> tuple[int, int]:
        """Estimate input and output token counts.

        Args:
            messages: Chat messages in OpenAI format.
            max_tokens: Maximum tokens the model is allowed to generate.

        Returns:
            ``(estimated_input_tokens, estimated_output_tokens)``
        """
        total_chars = sum(len(m.get("content", "")) for m in messages)
        est_input = max(1, total_chars // 4)
        # Output is bounded by max_tokens; assume ~half utilisation
        est_output = max(1, max_tokens // 2)
        return est_input, est_output

    # ── Cost computation ──────────────────────────────

    @staticmethod
    def estimate_cost(
        provider: str,
        est_input: int,
        est_output: int,
    ) -> float:
        """Compute estimated USD cost for the given token counts.

        Uses the ``COST_PER_MILLION_TOKENS`` table from ``cost_guard``.
        Falls back to a conservative default for unknown providers.
        """
        rates = COST_PER_MILLION_TOKENS.get(provider, _FALLBACK_RATE)
        cost = (
            (est_input / 1_000_000) * rates["input"]
            + (est_output / 1_000_000) * rates["output"]
        )
        return cost

    # ── Orchestration ─────────────────────────────────

    def check(
        self,
        provider: str,
        messages: list[dict[str, str]],
        max_tokens: int,
        budget_remaining: float,
    ) -> CostPrediction:
        """Run full pre-call estimation and budget comparison.

        Args:
            provider: Name of the target LLM provider.
            messages: Chat messages to be sent.
            max_tokens: Max output tokens for the call.
            budget_remaining: Remaining USD budget from ``CostGuard``.

        Returns:
            A ``CostPrediction`` with the estimation result and
            an optional human-readable warning string.
        """
        est_input, est_output = self.estimate_tokens(messages, max_tokens)
        est_cost = self.estimate_cost(provider, est_input, est_output)

        over = est_cost > budget_remaining
        warning: str | None = None
        if over:
            warning = (
                f"Predicted call cost ${est_cost:.6f} exceeds remaining "
                f"budget ${budget_remaining:.4f} "
                f"(provider={provider}, ~{est_input}+{est_output} tokens)"
            )

        return CostPrediction(
            estimated_input_tokens=est_input,
            estimated_output_tokens=est_output,
            estimated_cost_usd=est_cost,
            budget_remaining_usd=budget_remaining,
            over_budget=over,
            warning=warning,
        )
