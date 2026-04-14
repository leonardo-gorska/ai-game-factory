"""Unit tests for AgentForker (Roadmap v3 Item #9)."""

from __future__ import annotations

import pytest
from backend.agents.agent_forker import AgentForker, ForkDecision, MergeResult


# ── Fixtures ──────────────────────────────────────────

@pytest.fixture
def forker() -> AgentForker:
    return AgentForker()


def _make_input(
    bugs: int = 0,
    gdd_len: int = 0,
    critic: str = "",
    roadmap: str = "",
) -> dict:
    return {
        "known_bugs": [f"bug_{i}" for i in range(bugs)],
        "gdd_update": "x" * gdd_len,
        "last_critic_feedback": critic,
        "roadmap_task": roadmap,
    }


# ── Detection Tests ──────────────────────────────────

class TestDetection:
    def test_no_fork_when_no_bugs_no_features(self, forker: AgentForker) -> None:
        decision = forker.detect_divergent_goals(_make_input())
        assert not decision.should_fork

    def test_no_fork_bugs_only(self, forker: AgentForker) -> None:
        decision = forker.detect_divergent_goals(_make_input(bugs=5))
        assert not decision.should_fork

    def test_no_fork_features_only(self, forker: AgentForker) -> None:
        decision = forker.detect_divergent_goals(_make_input(gdd_len=100))
        assert not decision.should_fork

    def test_fork_when_both(self, forker: AgentForker) -> None:
        decision = forker.detect_divergent_goals(_make_input(bugs=3, gdd_len=100))
        assert decision.should_fork
        assert len(decision.tasks) == 2

    def test_fork_with_critic_feedback_and_gdd(self, forker: AgentForker) -> None:
        decision = forker.detect_divergent_goals(_make_input(
            critic="Fix the player movement bug",
            gdd_len=100,
        ))
        assert decision.should_fork

    def test_fork_with_roadmap_task(self, forker: AgentForker) -> None:
        decision = forker.detect_divergent_goals(_make_input(
            bugs=2,
            roadmap="Implement inventory system " * 5,
        ))
        assert decision.should_fork


# ── Fork Tasks Tests ─────────────────────────────────

class TestForkTasks:
    def test_fix_task_has_no_gdd(self, forker: AgentForker) -> None:
        input_data = _make_input(bugs=3, gdd_len=200)
        tasks = forker.fork_tasks(input_data)
        fix_task = tasks[0]
        assert fix_task["_fork_role"] == "fix"
        assert fix_task["gdd_update"] == ""
        assert fix_task["roadmap_task"] == ""
        assert len(fix_task["known_bugs"]) == 3

    def test_feature_task_has_no_bugs(self, forker: AgentForker) -> None:
        input_data = _make_input(bugs=3, gdd_len=200)
        tasks = forker.fork_tasks(input_data)
        feature_task = tasks[1]
        assert feature_task["_fork_role"] == "feature"
        assert len(feature_task["known_bugs"]) == 0
        assert feature_task["last_critic_feedback"] == ""

    def test_fork_creates_deep_copies(self, forker: AgentForker) -> None:
        input_data = _make_input(bugs=3, gdd_len=200)
        tasks = forker.fork_tasks(input_data)
        # Modifying one shouldn't affect the other
        tasks[0]["known_bugs"].append("extra")
        assert len(tasks[1]["known_bugs"]) == 0


# ── Merge Tests ───────────────────────────────────────

class TestMerge:
    def test_merge_empty(self, forker: AgentForker) -> None:
        result = forker.merge_results([])
        assert result.fork_count == 0
        assert result.merged_code_changes == {}

    def test_merge_no_conflicts(self, forker: AgentForker) -> None:
        class FakeResult:
            metadata = {
                "code_changes": {
                    "files": [{"path": "src/a.js", "content": "a"}],
                },
                "_fork_role": "fix",
            }
        class FakeResult2:
            metadata = {
                "code_changes": {
                    "files": [{"path": "src/b.js", "content": "b"}],
                },
                "_fork_role": "feature",
            }

        result = forker.merge_results([FakeResult(), FakeResult2()])
        assert result.fork_count == 2
        assert not result.has_conflicts
        assert len(result.merged_code_changes["files"]) == 2

    def test_merge_with_conflict_fix_wins(self, forker: AgentForker) -> None:
        class FixResult:
            metadata = {
                "code_changes": {
                    "files": [{"path": "src/shared.js", "content": "fixed"}],
                },
                "_fork_role": "fix",
            }
        class FeatureResult:
            metadata = {
                "code_changes": {
                    "files": [{"path": "src/shared.js", "content": "featured"}],
                },
                "_fork_role": "feature",
            }

        # Feature first, then fix — fix should win
        result = forker.merge_results([FeatureResult(), FixResult()])
        assert result.has_conflicts
        assert len(result.conflicts) == 1
        # Fix wins
        final_file = result.merged_code_changes["files"][0]
        assert final_file["content"] == "fixed"


# ── ForkDecision / MergeResult Dataclasses ────────────

class TestDataclasses:
    def test_fork_decision_defaults(self) -> None:
        d = ForkDecision()
        assert not d.should_fork
        assert d.tasks == []
        assert d.reason == ""

    def test_merge_result_has_conflicts(self) -> None:
        r = MergeResult(conflicts=["a", "b"])
        assert r.has_conflicts
        r2 = MergeResult()
        assert not r2.has_conflicts
