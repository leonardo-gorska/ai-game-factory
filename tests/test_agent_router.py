"""Tests for backend.core.agent_router"""

import pytest
from backend.core.agent_router import (
    AgentRouter,
    RoutingDecision,
    ALL_AGENTS,
    ALWAYS_RUN,
    CHANGE_TYPE_AGENTS,
)


class TestFullSweep:
    def test_iteration_1_always_full_sweep(self):
        router = AgentRouter()
        decision = router.select_agents(iteration=1)
        assert decision.is_full_sweep is True
        assert decision.agents_to_run == ALL_AGENTS

    def test_full_sweep_every_5_iterations(self):
        router = AgentRouter(full_sweep_interval=5)
        for it in [5, 10, 15, 20]:
            decision = router.select_agents(iteration=it)
            assert decision.is_full_sweep is True
            assert decision.agents_to_run == ALL_AGENTS

    def test_custom_sweep_interval(self):
        router = AgentRouter(full_sweep_interval=3)
        d3 = router.select_agents(iteration=3)
        d4 = router.select_agents(iteration=4)
        assert d3.is_full_sweep is True
        assert d4.is_full_sweep is False


class TestFileClassification:
    def test_combat_files_trigger_combat_agents(self):
        router = AgentRouter()
        decision = router.select_agents(
            changed_files={"src/combat_system.js": "..."},
            iteration=2,
        )
        assert "exploit_detector" in decision.agents_to_run
        assert "tester" in decision.agents_to_run

    def test_economy_files_trigger_economy_agents(self):
        router = AgentRouter()
        decision = router.select_agents(
            changed_files={"src/shop.js": "..."},
            iteration=2,
        )
        assert "economy_guardian" in decision.agents_to_run
        assert "simulation_analyst" in decision.agents_to_run

    def test_ui_files_trigger_ui_agents(self):
        router = AgentRouter()
        decision = router.select_agents(
            changed_files={"src/hud.js": "..."},
            iteration=2,
        )
        assert "tester" in decision.agents_to_run
        assert "performance" in decision.agents_to_run

    def test_unrelated_files_only_baseline(self):
        router = AgentRouter()
        decision = router.select_agents(
            changed_files={"src/readme.js": "..."},
            iteration=2,
        )
        # No keyword match → baseline only
        assert decision.agents_to_run == ALWAYS_RUN

    def test_multiple_change_types(self):
        router = AgentRouter()
        decision = router.select_agents(
            changed_files={
                "src/combat.js": "...",
                "src/shop.js": "...",
            },
            iteration=2,
        )
        assert "exploit_detector" in decision.agents_to_run
        assert "economy_guardian" in decision.agents_to_run
        assert "combat" in decision.change_types_detected
        assert "economy" in decision.change_types_detected


class TestGDDClassification:
    def test_combat_gdd_section(self):
        router = AgentRouter()
        decision = router.select_agents(
            gdd_changes={"combat_system": {"damage": 10}},
            iteration=2,
        )
        assert "combat" in decision.change_types_detected
        assert "exploit_detector" in decision.agents_to_run

    def test_economy_gdd_section(self):
        router = AgentRouter()
        decision = router.select_agents(
            gdd_changes={"economy": {"gold_rate": 5}},
            iteration=2,
        )
        assert "economy" in decision.change_types_detected
        assert "economy_guardian" in decision.agents_to_run

    def test_progression_gdd_section(self):
        router = AgentRouter()
        decision = router.select_agents(
            gdd_changes={"progression": {"xp_curve": []}},
            iteration=2,
        )
        assert "balance" in decision.change_types_detected


class TestNoChanges:
    def test_no_files_no_gdd_baseline_only(self):
        router = AgentRouter()
        decision = router.select_agents(iteration=2)
        assert decision.agents_to_run == ALWAYS_RUN
        assert decision.skipped_agents == ALL_AGENTS - ALWAYS_RUN

    def test_empty_dicts_baseline_only(self):
        router = AgentRouter()
        decision = router.select_agents(
            changed_files={},
            gdd_changes={},
            iteration=2,
        )
        assert decision.agents_to_run == ALWAYS_RUN


class TestSkippedAgents:
    def test_skipped_agents_is_complement(self):
        router = AgentRouter()
        decision = router.select_agents(
            changed_files={"src/combat.js": "..."},
            iteration=2,
        )
        assert decision.agents_to_run | decision.skipped_agents == ALL_AGENTS
        assert decision.agents_to_run & decision.skipped_agents == set()


class TestRoutingDecision:
    def test_to_dict_keys(self):
        decision = RoutingDecision(
            agents_to_run={"tester"},
            skipped_agents={"performance"},
            change_types_detected={"combat"},
            reason="test",
        )
        d = decision.to_dict()
        assert "agents_to_run" in d
        assert "skipped_agents" in d
        assert "change_types" in d
        assert "is_full_sweep" in d
        assert "reason" in d
        assert d["agents_to_run"] == ["tester"]
        assert d["skipped_agents"] == ["performance"]
