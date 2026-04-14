"""
Tests for backend.orchestrator.multi_pipeline and backend.core.resource_scheduler
(v3 Roadmap Item 17 — Multi-Game Factory Mode)
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.config import ProjectConfig, AppConfig
from backend.core.resource_scheduler import ResourceScheduler, GameAllocation
from backend.orchestrator.multi_pipeline import MultiPipeline, GameSlot


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ResourceScheduler Tests
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestGameAllocation:
    def test_defaults(self):
        alloc = GameAllocation(game_id="test")
        assert alloc.game_id == "test"
        assert alloc.priority == 5
        assert alloc.allocated_usd == 0.0
        assert alloc.used_usd == 0.0

    def test_remaining(self):
        alloc = GameAllocation(game_id="x", allocated_usd=10.0, used_usd=3.5)
        assert alloc.remaining_usd == 6.5

    def test_remaining_never_negative(self):
        alloc = GameAllocation(game_id="y", allocated_usd=1.0, used_usd=5.0)
        assert alloc.remaining_usd == 0.0

    def test_usage_pct(self):
        alloc = GameAllocation(game_id="z", allocated_usd=10.0, used_usd=7.0)
        assert alloc.usage_pct == 70.0

    def test_usage_pct_zero_allocation(self):
        alloc = GameAllocation(game_id="w")
        assert alloc.usage_pct == 0.0

    def test_to_dict(self):
        alloc = GameAllocation(game_id="d", priority=3, allocated_usd=5.0, used_usd=2.0)
        d = alloc.to_dict()
        assert d["game_id"] == "d"
        assert d["priority"] == 3
        assert d["allocated_usd"] == 5.0
        assert d["used_usd"] == 2.0
        assert d["remaining_usd"] == 3.0


class TestResourceScheduler:
    def test_init(self):
        rs = ResourceScheduler(total_budget_usd=20.0)
        assert rs.total_budget == 20.0

    def test_register_and_rebalance(self):
        rs = ResourceScheduler(total_budget_usd=10.0)
        rs.register("game_a", priority=0)
        # Single game gets all the budget
        assert rs.get_allocation("game_a") == pytest.approx(10.0)

    def test_register_multiple_equal_priority(self):
        rs = ResourceScheduler(total_budget_usd=12.0)
        rs.register("a", priority=5)
        rs.register("b", priority=5)
        # Equal priority → equal split
        assert rs.get_allocation("a") == pytest.approx(6.0)
        assert rs.get_allocation("b") == pytest.approx(6.0)

    def test_priority_based_allocation(self):
        rs = ResourceScheduler(total_budget_usd=12.0)
        # Priority 0 → weight 11, Priority 10 → weight 1
        rs.register("high", priority=0)   # weight 11
        rs.register("low", priority=10)   # weight 1
        # Total weight = 12
        assert rs.get_allocation("high") == pytest.approx(11.0)
        assert rs.get_allocation("low") == pytest.approx(1.0)

    def test_unregister_rebalances(self):
        rs = ResourceScheduler(total_budget_usd=10.0)
        rs.register("a", priority=5)
        rs.register("b", priority=5)
        assert rs.get_allocation("a") == pytest.approx(5.0)
        rs.unregister("b")
        # After removing b, a gets all the budget
        assert rs.get_allocation("a") == pytest.approx(10.0)

    def test_unregister_nonexistent(self):
        rs = ResourceScheduler()
        assert rs.unregister("nonexistent") is False

    def test_record_usage(self):
        rs = ResourceScheduler(total_budget_usd=10.0)
        rs.register("g", priority=5)
        rs.record_usage("g", 2.5)
        assert rs.get_remaining("g") == pytest.approx(7.5)

    def test_record_usage_nonexistent(self):
        rs = ResourceScheduler()
        # Should not raise
        rs.record_usage("nonexistent", 1.0)

    def test_is_over_budget(self):
        rs = ResourceScheduler(total_budget_usd=5.0)
        rs.register("g", priority=5)
        assert rs.is_over_budget("g") is False
        rs.record_usage("g", 6.0)
        assert rs.is_over_budget("g") is True

    def test_is_over_budget_nonexistent(self):
        rs = ResourceScheduler()
        assert rs.is_over_budget("x") is False

    def test_get_remaining_nonexistent(self):
        rs = ResourceScheduler()
        assert rs.get_remaining("x") == 0.0

    def test_get_allocation_nonexistent(self):
        rs = ResourceScheduler()
        assert rs.get_allocation("x") == 0.0

    def test_set_total_budget(self):
        rs = ResourceScheduler(total_budget_usd=10.0)
        rs.register("a", priority=5)
        rs.set_total_budget(20.0)
        assert rs.total_budget == 20.0
        assert rs.get_allocation("a") == pytest.approx(20.0)

    def test_set_total_budget_negative_clamped(self):
        rs = ResourceScheduler()
        rs.set_total_budget(-5.0)
        assert rs.total_budget == 0.0

    def test_allocate_creates_if_needed(self):
        rs = ResourceScheduler(total_budget_usd=10.0)
        budget = rs.allocate("new_game", priority=5)
        assert budget > 0
        assert rs.get_allocation("new_game") > 0

    def test_get_stats(self):
        rs = ResourceScheduler(total_budget_usd=10.0)
        rs.register("a", priority=5)
        rs.register("b", priority=5)
        rs.record_usage("a", 1.0)
        stats = rs.get_stats()
        assert stats["total_budget_usd"] == 10.0
        assert stats["total_used_usd"] == 1.0
        assert stats["game_count"] == 2
        assert "a" in stats["games"]
        assert "b" in stats["games"]

    def test_register_updates_existing_priority(self):
        rs = ResourceScheduler(total_budget_usd=12.0)
        rs.register("a", priority=5)
        rs.register("a", priority=0)  # Update priority
        stats = rs.get_stats()
        assert stats["games"]["a"]["priority"] == 0

    def test_rebalance_empty(self):
        rs = ResourceScheduler()
        rs.rebalance()  # Should not raise


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# GameSlot Tests
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestGameSlot:
    def test_defaults(self):
        cfg = ProjectConfig(game_name="Test Game")
        slot = GameSlot(game_id="t1", project_config=cfg)
        assert slot.game_id == "t1"
        assert slot.status == "idle"
        assert slot.priority == 5
        assert slot.pipeline is None
        assert slot.error is None

    def test_to_dict_no_pipeline(self):
        cfg = ProjectConfig(game_name="Test Game")
        slot = GameSlot(game_id="t2", project_config=cfg, priority=3)
        d = slot.to_dict()
        assert d["game_id"] == "t2"
        assert d["game_name"] == "Test Game"
        assert d["priority"] == 3
        assert d["pipeline_state"] is None
        assert d["status"] == "idle"

    def test_to_dict_with_pipeline(self):
        cfg = ProjectConfig(game_name="With Pipeline")
        slot = GameSlot(game_id="t3", project_config=cfg)
        # Mock a pipeline with state
        mock_pipeline = MagicMock()
        mock_pipeline.state.to_dict.return_value = {"current_iteration": 5}
        slot.pipeline = mock_pipeline
        d = slot.to_dict()
        assert d["pipeline_state"] == {"current_iteration": 5}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MultiPipeline Tests
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TestMultiPipelineInit:
    def test_defaults(self):
        mp = MultiPipeline(max_concurrent=2)
        assert mp.max_concurrent == 2
        assert mp.running_count == 0
        assert mp.game_ids == []

    def test_max_concurrent_minimum(self):
        mp = MultiPipeline(max_concurrent=0)
        assert mp.max_concurrent == 1


class TestMultiPipelineAddRemove:
    def test_add_game(self):
        mp = MultiPipeline()
        cfg = ProjectConfig(game_name="My RPG")
        slot = mp.add_game("rpg1", cfg, priority=2)
        assert slot.game_id == "rpg1"
        assert slot.project_config.game_name == "My RPG"
        assert slot.priority == 2
        assert "rpg1" in mp.game_ids

    def test_add_game_auto_id(self):
        mp = MultiPipeline()
        slot = mp.add_game()
        assert slot.game_id is not None
        assert len(slot.game_id) == 8

    def test_add_game_duplicate_raises(self):
        mp = MultiPipeline()
        mp.add_game("dup")
        with pytest.raises(ValueError, match="already exists"):
            mp.add_game("dup")

    def test_add_game_clamps_priority(self):
        mp = MultiPipeline()
        slot_low = mp.add_game("lo", priority=-5)
        slot_high = mp.add_game("hi", priority=20)
        assert slot_low.priority == 0
        assert slot_high.priority == 10

    def test_remove_game(self):
        mp = MultiPipeline()
        mp.add_game("rm")
        assert mp.remove_game("rm") is True
        assert "rm" not in mp.game_ids

    def test_remove_nonexistent(self):
        mp = MultiPipeline()
        assert mp.remove_game("nope") is False

    def test_get_game(self):
        mp = MultiPipeline()
        mp.add_game("g1", ProjectConfig(game_name="Test"))
        slot = mp.get_game("g1")
        assert slot is not None
        assert slot.game_id == "g1"

    def test_get_game_not_found(self):
        mp = MultiPipeline()
        assert mp.get_game("nope") is None

    def test_list_games(self):
        mp = MultiPipeline()
        mp.add_game("a")
        mp.add_game("b")
        games = mp.list_games()
        assert len(games) == 2
        game_ids = [g.game_id for g in games]
        assert "a" in game_ids
        assert "b" in game_ids


class TestMultiPipelineLifecycle:
    @pytest.mark.asyncio
    async def test_start_game_not_found(self):
        mp = MultiPipeline()
        with pytest.raises(ValueError, match="not found"):
            await mp.start_game("nonexistent")

    @pytest.mark.asyncio
    async def test_stop_game_not_found(self):
        mp = MultiPipeline()
        with pytest.raises(ValueError, match="not found"):
            await mp.stop_game("nonexistent")

    @pytest.mark.asyncio
    async def test_pause_game_not_found(self):
        mp = MultiPipeline()
        with pytest.raises(ValueError, match="not found"):
            await mp.pause_game("nonexistent")

    @pytest.mark.asyncio
    async def test_resume_game_not_found(self):
        mp = MultiPipeline()
        with pytest.raises(ValueError, match="not found"):
            await mp.resume_game("nonexistent")

    @pytest.mark.asyncio
    async def test_stop_game_not_running(self):
        mp = MultiPipeline()
        mp.add_game("idle_game")
        result = await mp.stop_game("idle_game")
        assert result["status"] == "not_running"

    @pytest.mark.asyncio
    async def test_pause_game_not_running(self):
        mp = MultiPipeline()
        mp.add_game("idle_game")
        result = await mp.pause_game("idle_game")
        assert result["status"] == "not_running"

    @pytest.mark.asyncio
    async def test_resume_game_not_paused(self):
        mp = MultiPipeline()
        mp.add_game("idle_game")
        result = await mp.resume_game("idle_game")
        assert result["status"] == "not_paused"

    @pytest.mark.asyncio
    async def test_max_concurrent_blocks(self):
        """Starting beyond max_concurrent should return limit reached."""
        mp = MultiPipeline(max_concurrent=1)
        mp.add_game("g1")
        mp.add_game("g2")

        # Mock pipeline creation to avoid real Pipeline init
        mock_pipeline = MagicMock()
        mock_pipeline.start = AsyncMock()
        mock_pipeline.on_event = MagicMock()

        with patch.object(mp, "_create_pipeline", return_value=mock_pipeline):
            result1 = await mp.start_game("g1")
            assert result1["status"] == "started"

            # g1 is now "running", so g2 should be blocked
            result2 = await mp.start_game("g2")
            assert result2["status"] == "max_concurrent_reached"

        # Cleanup
        mp._games["g1"]._task.cancel()
        await asyncio.sleep(0.1)

    @pytest.mark.asyncio
    async def test_start_already_running(self):
        mp = MultiPipeline(max_concurrent=2)
        mp.add_game("g1")

        mock_pipeline = MagicMock()
        mock_pipeline.start = AsyncMock()
        mock_pipeline.on_event = MagicMock()

        with patch.object(mp, "_create_pipeline", return_value=mock_pipeline):
            await mp.start_game("g1")
            result = await mp.start_game("g1")
            assert result["status"] == "already_running"

        mp._games["g1"]._task.cancel()
        await asyncio.sleep(0.1)

    @pytest.mark.asyncio
    async def test_stop_all(self):
        mp = MultiPipeline(max_concurrent=3)
        mp.add_game("g1")
        mp.add_game("g2")

        mock_pipeline = MagicMock()
        mock_pipeline.start = AsyncMock()
        mock_pipeline.stop = AsyncMock()
        mock_pipeline.on_event = MagicMock()

        with patch.object(mp, "_create_pipeline", return_value=mock_pipeline):
            await mp.start_game("g1")
            await mp.start_game("g2")
            result = await mp.stop_all()
            assert "g1" in result["stopped"]
            assert "g2" in result["stopped"]

        await asyncio.sleep(0.1)


class TestMultiPipelineCrossPollination:
    def test_cross_insights_not_found(self):
        mp = MultiPipeline()
        result = mp.get_cross_insights("nonexistent")
        assert "error" in result

    def test_cross_insights_no_siblings(self):
        mp = MultiPipeline()
        mp.add_game("solo")
        result = mp.get_cross_insights("solo")
        assert result["sibling_count"] == 0
        assert result["insights"] == []

    def test_cross_insights_with_siblings(self):
        mp = MultiPipeline()
        mp.add_game("g1", ProjectConfig(game_name="Game 1", genre="puzzle"))
        mp.add_game("g2", ProjectConfig(game_name="Game 2", genre="action"))

        # Mock pipeline state for g2
        mock_pipeline = MagicMock()
        mock_pipeline.state.best_score = 75
        mock_pipeline.state.total_iterations = 10
        mock_pipeline.state.get_score_trend.return_value = "improving"
        mock_pipeline.quality_engine.get_trend.return_value = "up"
        mp._games["g2"].pipeline = mock_pipeline

        result = mp.get_cross_insights("g1")
        assert result["sibling_count"] == 1
        assert result["insights"][0]["game_id"] == "g2"
        assert result["insights"][0]["best_score"] == 75


class TestMultiPipelineSummary:
    def test_empty_summary(self):
        mp = MultiPipeline(max_concurrent=3)
        summary = mp.get_summary()
        assert summary["total_games"] == 0
        assert summary["max_concurrent"] == 3
        assert summary["running_count"] == 0
        assert summary["games"] == []

    def test_summary_with_games(self):
        mp = MultiPipeline()
        mp.add_game("a", ProjectConfig(game_name="Alpha"))
        mp.add_game("b", ProjectConfig(game_name="Beta"))
        summary = mp.get_summary()
        assert summary["total_games"] == 2
        assert len(summary["games"]) == 2
        game_names = [g["game_name"] for g in summary["games"]]
        assert "Alpha" in game_names
        assert "Beta" in game_names

    def test_summary_resource_allocation(self):
        mp = MultiPipeline(total_budget_usd=10.0)
        mp.add_game("a", priority=5)
        mp.add_game("b", priority=5)
        summary = mp.get_summary()
        assert "resource_allocation" in summary
        assert summary["resource_allocation"]["total_budget_usd"] == 10.0

    def test_summary_status_counts(self):
        mp = MultiPipeline()
        mp.add_game("a")
        mp.add_game("b")
        mp._games["a"].status = "running"
        summary = mp.get_summary()
        assert summary["status_counts"]["idle"] == 1
        assert summary["status_counts"]["running"] == 1


class TestMultiPipelineEvents:
    @pytest.mark.asyncio
    async def test_on_event_registered(self):
        mp = MultiPipeline()
        events = []

        async def handler(event):
            events.append(event)

        mp.on_event(handler)
        await mp._emit("test_event", {"foo": "bar"})
        assert len(events) == 1
        assert events[0]["type"] == "test_event"

    @pytest.mark.asyncio
    async def test_event_callback_error_handled(self):
        mp = MultiPipeline()

        async def bad_handler(event):
            raise RuntimeError("oops")

        mp.on_event(bad_handler)
        # Should not raise
        await mp._emit("test", {})
