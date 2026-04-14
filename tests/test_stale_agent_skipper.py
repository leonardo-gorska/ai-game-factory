"""
Tests for StaleAgentSkipper — skip logic for analysis agents.
"""

import pytest

from backend.core.stale_agent_skipper import StaleAgentSkipper, AGENT_RELEVANT_PATTERNS


# ── Iteration 1 never skips ──────────────────────────

class TestNeverSkipIteration1:
    def test_economy_not_skipped_iter1(self):
        """No agent should be skipped on the very first iteration."""
        assert not StaleAgentSkipper.should_skip(
            "economy_guardian", iteration=1, changed_files={},
        )

    def test_performance_not_skipped_iter1(self):
        """Performance should never be skipped on iteration 1."""
        assert not StaleAgentSkipper.should_skip(
            "performance", iteration=1,
            prev_perf_score=80.0, curr_perf_score=80.0,
        )

    def test_exploit_not_skipped_iter1(self):
        """Exploit detector should never be skipped on iteration 1."""
        assert not StaleAgentSkipper.should_skip(
            "exploit_detector", iteration=1, changed_files={},
        )

    def test_researcher_not_skipped_iter1(self):
        """Researcher should never be skipped on iteration 1."""
        assert not StaleAgentSkipper.should_skip("researcher", iteration=1)


# ── Economy Guardian ─────────────────────────────────

class TestEconomyGuardianSkip:
    def test_skip_no_economy_files_changed(self):
        """Skip when changed files don't match economy patterns."""
        changed = {"src/systems/PlayerMovement.js": "code"}
        assert StaleAgentSkipper.should_skip(
            "economy_guardian", iteration=3, changed_files=changed,
        )

    def test_skip_no_files_changed(self):
        """Skip when no files changed at all."""
        assert StaleAgentSkipper.should_skip(
            "economy_guardian", iteration=3, changed_files={},
        )

    def test_no_skip_economy_file_changed(self):
        """Don't skip when an economy-related file changed."""
        changed = {"src/systems/EconomySystem.js": "code"}
        assert not StaleAgentSkipper.should_skip(
            "economy_guardian", iteration=3, changed_files=changed,
        )

    def test_no_skip_shop_file_changed(self):
        """Don't skip when a shop-related file changed."""
        changed = {"src/systems/ShopManager.js": "code"}
        assert not StaleAgentSkipper.should_skip(
            "economy_guardian", iteration=3, changed_files=changed,
        )

    def test_no_skip_currency_file_changed(self):
        """Don't skip when a currency-related file changed."""
        changed = {"src/systems/CurrencyManager.js": "code"}
        assert not StaleAgentSkipper.should_skip(
            "economy_guardian", iteration=3, changed_files=changed,
        )

    def test_no_skip_reward_file_changed(self):
        """Don't skip when a reward-related file changed."""
        changed = {"src/systems/RewardSystem.js": "code"}
        assert not StaleAgentSkipper.should_skip(
            "economy_guardian", iteration=3, changed_files=changed,
        )


# ── Performance Agent ────────────────────────────────

class TestPerformanceSkip:
    def test_skip_score_stable(self):
        """Skip when performance score didn't drop."""
        assert StaleAgentSkipper.should_skip(
            "performance", iteration=3,
            prev_perf_score=75.0, curr_perf_score=75.0,
        )

    def test_skip_score_improved(self):
        """Skip when performance score improved."""
        assert StaleAgentSkipper.should_skip(
            "performance", iteration=3,
            prev_perf_score=60.0, curr_perf_score=80.0,
        )

    def test_no_skip_score_dropped(self):
        """Don't skip when performance score dropped."""
        assert not StaleAgentSkipper.should_skip(
            "performance", iteration=3,
            prev_perf_score=80.0, curr_perf_score=70.0,
        )

    def test_no_skip_no_prev_score(self):
        """Don't skip when there's no previous score."""
        assert not StaleAgentSkipper.should_skip(
            "performance", iteration=3,
            prev_perf_score=None, curr_perf_score=75.0,
        )

    def test_no_skip_no_curr_score(self):
        """Don't skip when there's no current score."""
        assert not StaleAgentSkipper.should_skip(
            "performance", iteration=3,
            prev_perf_score=75.0, curr_perf_score=None,
        )


# ── Exploit Detector ─────────────────────────────────

class TestExploitDetectorSkip:
    def test_skip_no_combat_changes(self):
        """Skip when no combat/reward files changed."""
        changed = {"src/ui/MenuScreen.js": "code"}
        assert StaleAgentSkipper.should_skip(
            "exploit_detector", iteration=3, changed_files=changed,
        )

    def test_no_skip_combat_file_changed(self):
        """Don't skip when a combat-related file changed."""
        changed = {"src/systems/CombatSystem.js": "code"}
        assert not StaleAgentSkipper.should_skip(
            "exploit_detector", iteration=3, changed_files=changed,
        )

    def test_no_skip_damage_file_changed(self):
        """Don't skip when a damage-related file changed."""
        changed = {"src/systems/DamageCalculator.js": "code"}
        assert not StaleAgentSkipper.should_skip(
            "exploit_detector", iteration=3, changed_files=changed,
        )

    def test_no_skip_reward_file_changed(self):
        """Don't skip when a reward file changed (shared with economy)."""
        changed = {"src/systems/RewardDropTable.js": "code"}
        assert not StaleAgentSkipper.should_skip(
            "exploit_detector", iteration=3, changed_files=changed,
        )


# ── Researcher ───────────────────────────────────────

class TestResearcherSkip:
    def test_skip_iteration_2(self):
        """Skip researcher on iteration 2 (too early to research again)."""
        assert StaleAgentSkipper.should_skip("researcher", iteration=2)

    def test_no_skip_iteration_3(self):
        """Don't skip researcher from iteration 3 onwards."""
        assert not StaleAgentSkipper.should_skip("researcher", iteration=3)

    def test_no_skip_iteration_5(self):
        """Don't skip researcher on later iterations."""
        assert not StaleAgentSkipper.should_skip("researcher", iteration=5)


# ── Unknown agents ───────────────────────────────────

class TestUnknownAgent:
    def test_unknown_agent_never_skipped(self):
        """Agents not in the skip rules are never skipped."""
        assert not StaleAgentSkipper.should_skip(
            "tester", iteration=5, changed_files={},
        )

    def test_designer_never_skipped(self):
        """Designer is never in the skip rules."""
        assert not StaleAgentSkipper.should_skip(
            "designer", iteration=5, changed_files={},
        )


# ── Pattern config ───────────────────────────────────

class TestPatternConfig:
    def test_economy_patterns_exist(self):
        """Economy agent must have relevance patterns defined."""
        assert "economy_guardian" in AGENT_RELEVANT_PATTERNS
        assert len(AGENT_RELEVANT_PATTERNS["economy_guardian"]) >= 4

    def test_exploit_patterns_exist(self):
        """Exploit agent must have relevance patterns defined."""
        assert "exploit_detector" in AGENT_RELEVANT_PATTERNS
        assert len(AGENT_RELEVANT_PATTERNS["exploit_detector"]) >= 4
