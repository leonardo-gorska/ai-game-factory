"""Tests for backend.agents.self_reflection — Self-Reflection Agent (Roadmap v2 Item 9)"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.agents.self_reflection import SelfReflectionAgent


@pytest.fixture
def agent():
    """Create a SelfReflectionAgent with mocked LLM dependencies."""
    with patch("backend.agents.self_reflection.PROMPTS_DIR") as mock_dir:
        mock_path = MagicMock()
        mock_path.read_text.return_value = "You are a self-reflection agent."
        mock_dir.__truediv__ = MagicMock(return_value=mock_path)

        mock_router = MagicMock()
        mock_db = MagicMock()
        agent = SelfReflectionAgent(
            llm_router=mock_router,
            database=mock_db,
            interval=10,
        )
        return agent


class TestSelfReflectionAgentProperties:
    """Tests for SelfReflectionAgent configuration and properties."""

    def test_agent_name(self, agent):
        assert agent.name == "self_reflection"

    def test_agent_role(self, agent):
        assert agent.role == "Meta-Analysis & Self-Reflection"

    def test_interval_property(self, agent):
        assert agent.interval == 10

    def test_should_run_at_interval(self, agent):
        assert agent.should_run(10) is True
        assert agent.should_run(20) is True
        assert agent.should_run(30) is True

    def test_should_not_run_off_interval(self, agent):
        assert agent.should_run(1) is False
        assert agent.should_run(5) is False
        assert agent.should_run(7) is False

    def test_should_not_run_at_zero(self, agent):
        assert agent.should_run(0) is False

    def test_custom_interval(self):
        with patch("backend.agents.self_reflection.PROMPTS_DIR") as mock_dir:
            mock_path = MagicMock()
            mock_path.read_text.return_value = "prompt"
            mock_dir.__truediv__ = MagicMock(return_value=mock_path)
            a = SelfReflectionAgent(
                llm_router=MagicMock(),
                database=MagicMock(),
                interval=5,
            )
            assert a.interval == 5
            assert a.should_run(5) is True
            assert a.should_run(7) is False


class TestSelfReflectionBuildPrompt:
    """Tests for _build_prompt generation."""

    def test_builds_prompt_with_score_history(self, agent):
        prompt = agent._build_prompt(20, {
            "score_history": [50, 55, 60, 58, 62, 65, 63, 67, 70, 68],
            "current_score": 68,
            "total_iterations": 20,
        })
        assert "Score History" in prompt
        assert "68" in prompt

    def test_builds_prompt_with_cost_history(self, agent):
        prompt = agent._build_prompt(20, {
            "cost_history": [0.01, 0.02, 0.015, 0.01, 0.025],
            "current_score": 70,
        })
        assert "Cost Stats" in prompt
        assert "$" in prompt

    def test_builds_prompt_with_failures(self, agent):
        prompt = agent._build_prompt(20, {
            "failure_log": [
                {"iteration": 5, "agent": "developer", "error": "Build failed"},
                {"iteration": 8, "agent": "tester", "error": "Timeout"},
            ],
            "current_score": 65,
        })
        assert "Recent Failures" in prompt
        assert "developer" in prompt

    def test_builds_prompt_minimal_data(self, agent):
        prompt = agent._build_prompt(10, {"current_score": 50})
        assert "Current State" in prompt
        assert "50" in prompt

    def test_builds_prompt_with_trend_analysis(self, agent):
        """Should compute trend when 5+ scores available."""
        prompt = agent._build_prompt(10, {
            "score_history": [30, 35, 40, 42, 45, 50, 55, 60, 65, 70],
            "current_score": 70,
        })
        assert "Trend:" in prompt
        assert "delta=" in prompt


class TestSelfReflectionExecute:
    """Tests for SelfReflectionAgent.execute()."""

    @pytest.mark.asyncio
    async def test_execute_success(self, agent):
        insights = {
            "patterns": [],
            "unstable_areas": [],
            "plateau_detected": False,
            "recommendations": [{"priority": "high", "action": "Increase exploration"}],
            "risk_level": "low",
            "summary": "Pipeline is progressing well.",
        }
        agent._call_llm = AsyncMock(return_value=json.dumps(insights))

        result = await agent.execute(10, {
            "score_history": [50, 55, 60],
            "current_score": 60,
        })

        assert result.success is True
        assert result.agent_name == "self_reflection"
        assert result.action == "self_reflect"
        assert "insights" in result.metadata

    @pytest.mark.asyncio
    async def test_execute_failure(self, agent):
        agent._call_llm = AsyncMock(side_effect=RuntimeError("LLM down"))

        result = await agent.execute(10, {"current_score": 50})

        assert result.success is False
        assert "LLM down" in result.error

    @pytest.mark.asyncio
    async def test_execute_malformed_response(self, agent):
        """Should use fallback parsing for non-JSON responses."""
        agent._call_llm = AsyncMock(return_value="This is not JSON but analysis text")

        result = await agent.execute(10, {"current_score": 50})

        assert result.success is True
        # Fallback should produce a valid dict with 'summary'
        insights = json.loads(result.output)
        assert "summary" in insights
