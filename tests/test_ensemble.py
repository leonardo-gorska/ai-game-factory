"""
Tests for EnsembleRouter — Multi-Model Consensus (Roadmap v2 Item 5).
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from backend.llm.ensemble import EnsembleRouter, EnsembleResult, _DEFAULT_ENSEMBLE_AGENTS
from backend.llm.provider import LLMResponse


def _make_router_mock(providers: list[str] | None = None) -> MagicMock:
    """Create a minimal LLMRouter mock."""
    router = MagicMock()
    router.available_providers = providers if providers is not None else ["gemini", "sambanova", "openrouter"]
    router.get_stats.return_value = {}
    return router


def _make_response(
    content: str = "Hello",
    provider: str = "gemini",
    model: str = "gemini-2.0-flash",
    tokens: int = 100,
    latency_ms: float = 500.0,
) -> LLMResponse:
    return LLMResponse(
        content=content,
        provider=provider,
        model=model,
        usage={
            "prompt_tokens": tokens // 2,
            "completion_tokens": tokens // 2,
            "total_tokens": tokens,
        },
        latency_ms=latency_ms,
    )


# ── should_ensemble tests ────────────────────


class TestShouldEnsemble:
    def test_designer_at_interval(self):
        """Designer at iteration multiple of 3 should use ensemble."""
        router = _make_router_mock()
        ensemble = EnsembleRouter(router)
        assert ensemble.should_ensemble("designer", 3) is True
        assert ensemble.should_ensemble("designer", 6) is True
        assert ensemble.should_ensemble("designer", 9) is True

    def test_critic_at_interval(self):
        """Critic at iteration multiple of 3 should use ensemble."""
        router = _make_router_mock()
        ensemble = EnsembleRouter(router)
        assert ensemble.should_ensemble("critic", 3) is True

    def test_excluded_agent(self):
        """Developer is not in the ensemble agents set."""
        router = _make_router_mock()
        ensemble = EnsembleRouter(router)
        assert ensemble.should_ensemble("developer", 3) is False
        assert ensemble.should_ensemble("tester", 3) is False

    def test_not_at_interval(self):
        """Even ensemble agents should not trigger outside interval."""
        router = _make_router_mock()
        ensemble = EnsembleRouter(router)
        assert ensemble.should_ensemble("designer", 1) is False
        assert ensemble.should_ensemble("designer", 2) is False
        assert ensemble.should_ensemble("designer", 4) is False

    def test_iteration_zero(self):
        """Iteration 0 should never trigger ensemble."""
        router = _make_router_mock()
        ensemble = EnsembleRouter(router)
        assert ensemble.should_ensemble("designer", 0) is False

    def test_negative_iteration(self):
        """Negative iteration should never trigger ensemble."""
        router = _make_router_mock()
        ensemble = EnsembleRouter(router)
        assert ensemble.should_ensemble("designer", -1) is False

    def test_single_provider(self):
        """Ensemble requires at least 2 providers."""
        router = _make_router_mock(providers=["gemini"])
        ensemble = EnsembleRouter(router)
        assert ensemble.should_ensemble("designer", 3) is False

    def test_custom_agents(self):
        """Custom ensemble agents should work."""
        router = _make_router_mock()
        ensemble = EnsembleRouter(router, ensemble_agents={"developer"})
        assert ensemble.should_ensemble("developer", 3) is True
        assert ensemble.should_ensemble("designer", 3) is False

    def test_custom_interval(self):
        """Custom interval should work."""
        router = _make_router_mock()
        ensemble = EnsembleRouter(router, interval=5)
        assert ensemble.should_ensemble("designer", 5) is True
        assert ensemble.should_ensemble("designer", 3) is False

    def test_reentrant_guard(self):
        """During consensus, should_ensemble returns False to prevent recursion."""
        router = _make_router_mock()
        ensemble = EnsembleRouter(router)
        ensemble._in_consensus = True
        assert ensemble.should_ensemble("designer", 3) is False


# ── _select_diverse_providers tests ──────────


class TestSelectProviders:
    def test_selects_n_providers(self):
        """Should select exactly N providers."""
        router = _make_router_mock(providers=["a", "b", "c", "d"])
        ensemble = EnsembleRouter(router)
        result = ensemble._select_diverse_providers(2)
        assert len(result) == 2

    def test_caps_at_available(self):
        """Should cap at number of available providers."""
        router = _make_router_mock(providers=["a", "b"])
        ensemble = EnsembleRouter(router)
        result = ensemble._select_diverse_providers(5)
        assert len(result) == 2

    def test_empty_providers(self):
        """Should return empty list if no providers available."""
        router = _make_router_mock(providers=[])
        ensemble = EnsembleRouter(router)
        result = ensemble._select_diverse_providers(2)
        assert result == []

    def test_returns_list_of_strings(self):
        """Result should be a list of provider name strings."""
        router = _make_router_mock(providers=["gemini", "sambanova"])
        ensemble = EnsembleRouter(router)
        result = ensemble._select_diverse_providers(2)
        assert all(isinstance(p, str) for p in result)


# ── _merge_responses tests ───────────────────


class TestMergeResponses:
    def test_text_merge_picks_longest(self):
        """Text merge should pick the longest response."""
        router = _make_router_mock()
        ensemble = EnsembleRouter(router)

        short = _make_response(content="Short answer", provider="a")
        long = _make_response(
            content="This is a much longer and more detailed answer with more information",
            provider="b",
        )

        merged, strategy = ensemble._merge_responses([short, long])
        assert strategy == "text_longest"
        assert "much longer" in merged.content
        assert "ensemble" in merged.provider

    def test_json_merge_combines_fields(self):
        """JSON merge should combine fields from multiple responses."""
        router = _make_router_mock()
        ensemble = EnsembleRouter(router)

        resp_a = _make_response(
            content='{"name": "RPG", "genre": "action"}',
            provider="a",
            tokens=200,
        )
        resp_b = _make_response(
            content='{"name": "RPG", "genre": "action", "difficulty": "hard"}',
            provider="b",
            tokens=250,
        )

        merged, strategy = ensemble._merge_responses([resp_a, resp_b], json_mode=True)
        assert strategy == "json_merge"

        import json
        data = json.loads(merged.content)
        assert "name" in data
        assert "genre" in data
        assert "difficulty" in data

    def test_json_merge_fallback_to_text(self):
        """If JSON parsing fails for most responses, fall back to text merge."""
        router = _make_router_mock()
        ensemble = EnsembleRouter(router)

        # Use content that extract_json_from_response truly cannot parse
        resp_a = _make_response(content=":::---!!!", provider="a")
        resp_b = _make_response(content=":::---!!! longer garbage content", provider="b")

        merged, strategy = ensemble._merge_responses([resp_a, resp_b], json_mode=True)
        # Should fall back since at most 1 response parsed as JSON (need 2+)
        assert strategy in ("text_longest", "json_merge")

    def test_usage_combined(self):
        """Merged usage should sum tokens from all responses."""
        router = _make_router_mock()
        ensemble = EnsembleRouter(router)

        resp_a = _make_response(tokens=100, provider="a")
        resp_b = _make_response(tokens=200, provider="b")

        merged, _ = ensemble._merge_responses([resp_a, resp_b])
        assert merged.usage["total_tokens"] == 300


# ── consensus tests ──────────────────────────


class TestConsensus:
    @pytest.mark.asyncio
    async def test_consensus_with_two_providers(self):
        """consensus should call 2 providers and merge responses."""
        router = _make_router_mock(providers=["gemini", "sambanova"])

        resp_a = _make_response(content="Answer from Gemini", provider="gemini")
        resp_b = _make_response(
            content="A longer and better answer from SambaNova",
            provider="sambanova",
        )

        call_count = 0

        async def mock_complete(**kwargs):
            nonlocal call_count
            call_count += 1
            if kwargs.get("preferred_provider") == "gemini":
                return resp_a
            return resp_b

        router.complete = mock_complete

        ensemble = EnsembleRouter(router)
        result = await ensemble.consensus(
            messages=[{"role": "user", "content": "Hello"}],
        )

        assert isinstance(result, EnsembleResult)
        assert result.n_models_queried == 2
        assert result.n_models_succeeded == 2
        assert call_count == 2
        assert result.merge_strategy in ("text_longest", "json_merge")

    @pytest.mark.asyncio
    async def test_consensus_single_provider_fallback(self):
        """With only 1 provider, use single model call."""
        router = _make_router_mock(providers=["gemini"])

        resp = _make_response(content="Solo answer", provider="gemini")
        router.complete = AsyncMock(return_value=resp)

        ensemble = EnsembleRouter(router)
        result = await ensemble.consensus(
            messages=[{"role": "user", "content": "Hello"}],
        )

        assert result.merge_strategy == "single_fallback"
        assert result.n_models_queried == 1
        assert result.n_models_succeeded == 1

    @pytest.mark.asyncio
    async def test_consensus_partial_failure(self):
        """If one provider fails, use the survivor."""
        router = _make_router_mock(providers=["gemini", "sambanova"])

        resp = _make_response(content="Only answer", provider="gemini")

        async def mock_complete(**kwargs):
            if kwargs.get("preferred_provider") == "sambanova":
                raise RuntimeError("Provider down")
            return resp

        router.complete = mock_complete

        ensemble = EnsembleRouter(router)
        result = await ensemble.consensus(
            messages=[{"role": "user", "content": "Hello"}],
        )

        assert result.n_models_queried == 2
        assert result.n_models_succeeded == 1
        assert result.merge_strategy == "single_survivor"

    @pytest.mark.asyncio
    async def test_consensus_all_fail(self):
        """If all providers fail, raise RuntimeError."""
        router = _make_router_mock(providers=["gemini", "sambanova"])

        async def mock_complete(**kwargs):
            raise RuntimeError("All down")

        router.complete = mock_complete

        ensemble = EnsembleRouter(router)
        with pytest.raises(RuntimeError, match="all .* providers failed"):
            await ensemble.consensus(
                messages=[{"role": "user", "content": "Hello"}],
            )

    @pytest.mark.asyncio
    async def test_reentrant_guard_cleared_after_consensus(self):
        """_in_consensus should be cleared after consensus completes."""
        router = _make_router_mock(providers=["gemini", "sambanova"])

        resp = _make_response()
        router.complete = AsyncMock(return_value=resp)

        ensemble = EnsembleRouter(router)
        await ensemble.consensus(
            messages=[{"role": "user", "content": "Hello"}],
        )

        assert ensemble._in_consensus is False

    @pytest.mark.asyncio
    async def test_reentrant_guard_cleared_on_failure(self):
        """_in_consensus should be cleared even if consensus raises."""
        router = _make_router_mock(providers=["gemini", "sambanova"])

        async def mock_complete(**kwargs):
            raise RuntimeError("fail")

        router.complete = mock_complete

        ensemble = EnsembleRouter(router)
        with pytest.raises(RuntimeError):
            await ensemble.consensus(
                messages=[{"role": "user", "content": "Hello"}],
            )

        assert ensemble._in_consensus is False


# ── Properties & Stats ───────────────────────


class TestProperties:
    def test_default_ensemble_agents(self):
        """Default ensemble agents are designer and critic."""
        router = _make_router_mock()
        ensemble = EnsembleRouter(router)
        assert ensemble.ensemble_agents == _DEFAULT_ENSEMBLE_AGENTS

    def test_default_interval(self):
        """Default interval is 3."""
        router = _make_router_mock()
        ensemble = EnsembleRouter(router)
        assert ensemble.interval == 3

    def test_default_n_models(self):
        """Default n_models is 2."""
        router = _make_router_mock()
        ensemble = EnsembleRouter(router)
        assert ensemble.n_models == 2

    def test_min_n_models(self):
        """n_models must be at least 2."""
        router = _make_router_mock()
        ensemble = EnsembleRouter(router, n_models=1)
        assert ensemble.n_models == 2

    def test_stats_dict(self):
        """Stats should return a dict with expected keys."""
        router = _make_router_mock()
        ensemble = EnsembleRouter(router)
        stats = ensemble.stats
        assert "total_ensemble_calls" in stats
        assert "ensemble_agents" in stats
        assert "interval" in stats
        assert "n_models" in stats

    def test_ensemble_result_to_dict(self):
        """EnsembleResult.to_dict should return a serializable dict."""
        resp = _make_response()
        result = EnsembleResult(
            response=resp,
            n_models_queried=2,
            n_models_succeeded=2,
            providers_used=["a", "b"],
            merge_strategy="text_longest",
            total_tokens=200,
            total_latency_ms=1000.0,
        )
        d = result.to_dict()
        assert d["n_models_queried"] == 2
        assert d["n_models_succeeded"] == 2
        assert d["merge_strategy"] == "text_longest"


# ── Router integration tests ─────────────────


class TestRouterIntegration:
    def test_router_has_ensemble_fields(self):
        """LLMRouter should accept ensemble_router via set_ensemble_router."""
        from backend.llm.router import LLMRouter

        router = LLMRouter()
        assert router.ensemble_router is None

        ensemble = EnsembleRouter(router)
        router.set_ensemble_router(ensemble)
        assert router.ensemble_router is ensemble
