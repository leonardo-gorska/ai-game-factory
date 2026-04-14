"""
Tests for PlaytestSimulator — game simulation and metrics.
"""

import json
import pytest
from pathlib import Path

from backend.game.simulator import PlaytestSimulator, SimulationAggregate


@pytest.fixture
def simulator(tmp_path: Path) -> PlaytestSimulator:
    # Simulator prefers src/game_config.json (JSON format)
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    config_json = src_dir / "game_config.json"
    config_json.write_text(json.dumps({
        "startingGold": 100,
        "startingGems": 5,
        "idleGoldPerSecond": 1,
        "idleXPPerSecond": 0.5,
        "heroBaseHP": 100,
        "heroBaseATK": 10,
        "heroBaseDEF": 5,
        "heroLevelUpMultiplier": 1.15,
        "xpPerLevel": 100,
        "xpScalingFactor": 1.5,
        "combatTickMs": 1000,
        "critChance": 0.1,
        "critMultiplier": 2.0,
        "floorsPerDungeon": 5,
        "enemiesPerFloor": 3,
        "enemyScalingPerFloor": 1.2,
        "goldDropMin": 5,
        "goldDropMax": 25,
        "maxOfflineHours": 12,
        "offlineEfficiency": 0.5,
    }))
    return PlaytestSimulator(game_dir=tmp_path)


# ── Basic Simulation ──────────────────────────────

class TestSimulation:
    def test_run_returns_aggregate(self, simulator: PlaytestSimulator):
        result = simulator.run_simulation(num_runs=5, durations_hours=[1.0], seed=42)
        assert isinstance(result, SimulationAggregate)

    def test_deterministic_with_seed(self, simulator: PlaytestSimulator):
        r1 = simulator.run_simulation(num_runs=5, durations_hours=[1.0], seed=42)
        r2 = simulator.run_simulation(num_runs=5, durations_hours=[1.0], seed=42)
        assert r1.avg_level == r2.avg_level
        assert r1.crash_rate == r2.crash_rate

    def test_total_runs_positive(self, simulator: PlaytestSimulator):
        result = simulator.run_simulation(num_runs=5, durations_hours=[1.0], seed=1)
        assert result.total_runs > 0


# ── Metrics Validity ──────────────────────────────

class TestMetrics:
    def test_crash_rate_in_range(self, simulator: PlaytestSimulator):
        result = simulator.run_simulation(num_runs=5, durations_hours=[1.0], seed=42)
        assert 0.0 <= result.crash_rate <= 1.0

    def test_retention_in_range(self, simulator: PlaytestSimulator):
        result = simulator.run_simulation(num_runs=5, durations_hours=[1.0], seed=42)
        assert 0.0 <= result.estimated_retention_d1 <= 1.0
        assert 0.0 <= result.estimated_retention_d7 <= 1.0
        assert 0.0 <= result.estimated_retention_d30 <= 1.0

    def test_avg_level_positive(self, simulator: PlaytestSimulator):
        result = simulator.run_simulation(num_runs=5, durations_hours=[1.0], seed=42)
        assert result.avg_level >= 0


# ── Quality Metrics Export ────────────────────────

class TestQualityMetrics:
    def test_to_quality_metrics_returns_dict(self, simulator: PlaytestSimulator):
        result = simulator.run_simulation(num_runs=5, durations_hours=[1.0], seed=42)
        qm = result.to_quality_metrics()
        assert isinstance(qm, dict)
        assert "crash_rate" in qm or "sim_runs" in qm


# ── Per-Profile Stats ─────────────────────────────

class TestPerProfile:
    def test_per_profile_stats_present(self, simulator: PlaytestSimulator):
        result = simulator.run_simulation(num_runs=5, durations_hours=[1.0], seed=42)
        # With valid config, per_profile_stats should be populated
        assert result.total_runs > 0
        assert len(result.per_profile_stats) > 0

    def test_each_profile_has_avg_level(self, simulator: PlaytestSimulator):
        result = simulator.run_simulation(num_runs=5, durations_hours=[1.0], seed=42)
        for ps in result.per_profile_stats:
            assert hasattr(ps, "avg_level")
            assert hasattr(ps, "profile")
