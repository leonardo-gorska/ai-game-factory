"""
Tests for LLMRouter — complexity mapping, initialization, and stats.
"""

import pytest

from backend.llm.router import LLMRouter, _AGENT_COMPLEXITY


# ── Complexity Mapping ────────────────────────────

class TestComplexityMapping:
    def test_all_known_agents_have_complexity(self):
        """All agents used in the pipeline should have a complexity score."""
        expected_agents = [
            "designer", "developer", "critic", "tester",
            "performance", "builder", "researcher",
            "simulation_analyst", "economy_guardian", "memory_curator",
        ]
        for agent in expected_agents:
            assert agent in _AGENT_COMPLEXITY, (
                f"Agent '{agent}' missing from _AGENT_COMPLEXITY"
            )

    def test_complexity_values_in_range(self):
        """All complexity values should be between 0.0 and 1.0."""
        for agent, score in _AGENT_COMPLEXITY.items():
            assert 0.0 <= score <= 1.0, (
                f"Agent '{agent}' has complexity {score} outside [0, 1]"
            )

    def test_designer_is_high_complexity(self):
        """Designer is a creative task, should be high complexity."""
        assert _AGENT_COMPLEXITY["designer"] >= 0.8

    def test_builder_is_low_complexity(self):
        """Builder just runs npm, should be low complexity."""
        assert _AGENT_COMPLEXITY["builder"] <= 0.3

    def test_unknown_fallback_exists(self):
        """There should be a fallback for unknown agents."""
        assert "unknown" in _AGENT_COMPLEXITY


# ── Router Initialization ─────────────────────────

class TestRouterInit:
    def test_router_creates_without_error(self):
        """Router should instantiate even without API keys (graceful degradation)."""
        router = LLMRouter()
        assert router is not None

    def test_available_providers_is_list(self):
        """available_providers should return a list."""
        router = LLMRouter()
        providers = router.available_providers
        assert isinstance(providers, list)

    def test_get_stats_returns_dict(self):
        """get_stats should return a dict even with no calls made."""
        router = LLMRouter()
        stats = router.get_stats()
        assert isinstance(stats, dict)

    def test_routing_info_returns_dict(self):
        """get_routing_info should return a dict."""
        router = LLMRouter()
        info = router.get_routing_info()
        assert isinstance(info, dict)


# ── Context Overrides ─────────────────────────────

class TestRouterOverrides:
    def test_set_context_with_overrides(self):
        """set_context should store temperature and tier overrides."""
        router = LLMRouter()
        router.set_context("developer", 1, temperature_override=0.3, tier_override="premium")
        assert router._temperature_override == 0.3
        assert router._tier_override == "premium"

    def test_set_context_without_overrides(self):
        """set_context without overrides should leave them as None."""
        router = LLMRouter()
        router.set_context("developer", 1)
        assert router._temperature_override is None
        assert router._tier_override is None

    def test_clear_overrides(self):
        """clear_overrides should reset both to None."""
        router = LLMRouter()
        router.set_context("developer", 1, temperature_override=0.5, tier_override="premium")
        router.clear_overrides()
        assert router._temperature_override is None
        assert router._tier_override is None

    def test_overrides_init_none(self):
        """Overrides should be None after initialization."""
        router = LLMRouter()
        assert router._temperature_override is None
        assert router._tier_override is None
