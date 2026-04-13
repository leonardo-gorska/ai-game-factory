"""
Tests for backend.agents.goal_setter_agent — Autonomous Goal Setting (Roadmap v3 Item #15)
"""

import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from backend.agents.goal_setter_agent import GoalSetterAgent


# ─── Helpers ──────────────────────────────────────────

def _make_agent(**overrides):
    """Build a GoalSetterAgent with mocked LLM dependencies."""
    kwargs = {
        "llm_router": MagicMock(),
        "database": MagicMock(),
        "system_prompt": "test prompt",
    }
    kwargs.update(overrides)
    return GoalSetterAgent(**kwargs)


def _sample_goals(n: int = 3) -> dict:
    return {
        "goals": [
            {
                "id": f"goal_{i+1}",
                "priority": i + 1,
                "area": ["stability", "fun", "balance"][i % 3],
                "description": f"Improve dimension {i+1}",
                "success_criteria": f"Score > {50 + i*10}",
            }
            for i in range(n)
        ],
        "focus_summary": "Focus on weakest dimensions",
    }


# ─── Reevaluation Logic ──────────────────────────────

class TestShouldReevaluate:
    def test_first_iteration(self):
        agent = _make_agent()
        assert agent.should_reevaluate(1, 50.0) is True

    def test_no_previous_goals(self):
        agent = _make_agent()
        assert agent.should_reevaluate(3, 50.0) is True

    def test_interval_elapsed(self):
        agent = _make_agent(reevaluate_interval=5)
        agent._last_goals = {"goals": []}
        agent._last_eval_iteration = 1
        agent._last_score = 60.0
        # 5 iters passed → reevaluate
        assert agent.should_reevaluate(6, 60.0) is True

    def test_interval_not_elapsed(self):
        agent = _make_agent(reevaluate_interval=5)
        agent._last_goals = {"goals": []}
        agent._last_eval_iteration = 1
        agent._last_score = 60.0
        # Only 2 iters passed → no reevaluate
        assert agent.should_reevaluate(3, 60.0) is False

    def test_score_drop_triggers(self):
        agent = _make_agent(score_drop_threshold=15)
        agent._last_goals = {"goals": []}
        agent._last_eval_iteration = 1
        agent._last_score = 70.0
        # Score dropped 20 pts → reevaluate
        assert agent.should_reevaluate(2, 50.0) is True

    def test_score_increase_no_trigger(self):
        agent = _make_agent(score_drop_threshold=15)
        agent._last_goals = {"goals": []}
        agent._last_eval_iteration = 1
        agent._last_score = 50.0
        # Score went UP → no reevaluate
        assert agent.should_reevaluate(2, 65.0) is False

    def test_small_score_drop_no_trigger(self):
        agent = _make_agent(score_drop_threshold=15)
        agent._last_goals = {"goals": []}
        agent._last_eval_iteration = 1
        agent._last_score = 70.0
        # Only 10 pt drop < 15 threshold
        assert agent.should_reevaluate(2, 60.0) is False


# ─── Goal Parsing ─────────────────────────────────────

class TestGoalParsing:
    def test_valid_goals(self):
        agent = _make_agent()
        goals = _sample_goals(3)
        result = agent._parse_goals(json.dumps(goals))
        assert len(result["goals"]) == 3
        assert result["goals"][0]["id"] == "goal_1"

    def test_empty_response(self):
        agent = _make_agent()
        result = agent._parse_goals("")
        assert "goals" in result

    def test_malformed_json(self):
        agent = _make_agent()
        result = agent._parse_goals("not json at all")
        assert "goals" in result

    def test_goals_with_extra_fields(self):
        agent = _make_agent()
        goals = _sample_goals(2)
        goals["extra_field"] = "ignored"
        result = agent._parse_goals(json.dumps(goals))
        assert len(result["goals"]) == 2


# ─── Prompt Building ─────────────────────────────────

class TestPromptBuilding:
    def test_basic_prompt(self):
        agent = _make_agent()
        prompt = agent._build_prompt(5, {})
        assert "iteration #5" in prompt.lower()
        assert "json" in prompt.lower()

    def test_quality_history_included(self):
        agent = _make_agent()
        history = [
            {"composite": 50, "fun": 40, "stability": 60, "balance": 55,
             "novelty": 30, "retention": 45},
        ]
        prompt = agent._build_prompt(2, {"quality_history": history})
        assert "Quality Scores" in prompt
        assert "composite=50" in prompt

    def test_known_bugs_included(self):
        agent = _make_agent()
        prompt = agent._build_prompt(3, {"known_bugs": ["crash on load", "NaN damage"]})
        assert "crash on load" in prompt
        assert "NaN damage" in prompt

    def test_economy_report_included(self):
        agent = _make_agent()
        prompt = agent._build_prompt(3, {"economy_report": {"health": 0.7}})
        assert "Economy Report" in prompt

    def test_low_confidence_agents(self):
        agent = _make_agent()
        conf = {"low_confidence_agents": [{"agent": "designer"}]}
        prompt = agent._build_prompt(3, {"confidence_stats": conf})
        assert "designer" in prompt


# ─── Execute (integration-ish with mocked LLM) ───────

class TestExecute:
    @pytest.mark.asyncio
    async def test_successful_execution(self):
        agent = _make_agent()
        goals = _sample_goals(3)
        agent._call_llm = AsyncMock(return_value=json.dumps(goals))

        result = await agent.execute(1, {"current_score": 50.0})
        assert result.success is True
        assert result.action == "set_goals"
        assert result.metadata["goals_count"] == 3
        assert agent._last_eval_iteration == 1

    @pytest.mark.asyncio
    async def test_failed_execution(self):
        agent = _make_agent()
        agent._call_llm = AsyncMock(side_effect=RuntimeError("LLM down"))

        result = await agent.execute(1, {})
        assert result.success is False
        assert "LLM down" in result.error

    @pytest.mark.asyncio
    async def test_state_updated_after_success(self):
        agent = _make_agent()
        goals = _sample_goals(2)
        agent._call_llm = AsyncMock(return_value=json.dumps(goals))

        await agent.execute(5, {"current_score": 72.0})
        assert agent._last_eval_iteration == 5
        assert agent._last_score == 72.0
        assert len(agent.last_goals["goals"]) == 2


# ─── Last Goals Property ─────────────────────────────

class TestLastGoals:
    def test_empty_initially(self):
        agent = _make_agent()
        assert agent.last_goals == {}

    @pytest.mark.asyncio
    async def test_populated_after_execute(self):
        agent = _make_agent()
        goals = _sample_goals(1)
        agent._call_llm = AsyncMock(return_value=json.dumps(goals))
        await agent.execute(1, {})
        assert len(agent.last_goals["goals"]) == 1


# ─── Default System Prompt ───────────────────────────

class TestDefaultPrompt:
    def test_has_content(self):
        prompt = GoalSetterAgent._default_system_prompt()
        assert "Goal Setter" in prompt
        assert "JSON" in prompt
