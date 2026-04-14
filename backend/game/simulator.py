"""
GORVAX GAME FACTORY — Playtest Simulator v3
Heuristic bot with 5 player profiles, advanced Monte Carlo,
confidence intervals, bimodal detection, gameplay heatmaps,
long economy simulation (720h) and churn/retention model.
"""

from __future__ import annotations

import logging
import math
import random
import statistics
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from backend.config import GAME_DIR

logger = logging.getLogger(__name__)


# ── Player Profiles ───────────────────────────────────

class PlayerProfile(Enum):
    """Player profiles for simulation variance."""
    CASUAL = "casual"         # 10% ativo, 90% idle
    HARDCORE = "hardcore"     # 50% ativo, 50% idle
    OPTIMIZER = "optimizer"   # Sempre compra melhor upgrade
    EXPLORER = "explorer"     # Prioriza dungeons
    MINMAXER = "minmaxer"     # v3: 100% optimização, foca no melhor item

    @property
    def active_ratio(self) -> tuple[float, float]:
        """Active ratio range (min, max)."""
        return {
            PlayerProfile.CASUAL: (0.05, 0.15),
            PlayerProfile.HARDCORE: (0.40, 0.60),
            PlayerProfile.OPTIMIZER: (0.25, 0.45),
            PlayerProfile.EXPLORER: (0.30, 0.50),
            PlayerProfile.MINMAXER: (0.60, 0.80),
        }[self]

    @property
    def upgrade_priority(self) -> float:
        """Probability of purchasing an upgrade when possible."""
        return {
            PlayerProfile.CASUAL: 0.1,
            PlayerProfile.HARDCORE: 0.4,
            PlayerProfile.OPTIMIZER: 0.9,
            PlayerProfile.EXPLORER: 0.2,
            PlayerProfile.MINMAXER: 1.0,
        }[self]

    @property
    def combat_priority(self) -> float:
        """Probability of entering combat when active."""
        return {
            PlayerProfile.CASUAL: 0.3,
            PlayerProfile.HARDCORE: 0.7,
            PlayerProfile.OPTIMIZER: 0.5,
            PlayerProfile.EXPLORER: 0.8,
            PlayerProfile.MINMAXER: 0.6,
        }[self]


# ── Data Classes ──────────────────────────────────────

@dataclass
class SimulationResult:
    """Result of an individual simulation run."""
    run_id: int
    duration_hours: float
    profile: str = "casual"
    # Progression
    final_level: int = 1
    total_xp: float = 0
    levels_gained: int = 0
    # Economy
    gold_earned: float = 0
    gold_spent: float = 0
    gold_balance: float = 0
    gems_earned: int = 0
    # Combat
    battles_fought: int = 0
    battles_won: int = 0
    bosses_killed: int = 0
    deaths: int = 0
    # Engagement
    upgrades_purchased: int = 0
    dungeons_explored: int = 0
    active_minutes: float = 0
    idle_minutes: float = 0
    # Final states
    crashed: bool = False
    stuck: bool = False  # player couldn't progress further
    # GAM-01: Genre-specific extra data
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class ProfileStats:
    """Statistics per player profile."""
    profile: str
    runs: int = 0
    avg_level: float = 0
    avg_gold_per_hour: float = 0
    avg_deaths: float = 0
    engagement_rate: float = 0


@dataclass
class GameplayHeatmap:
    """v3: Gameplay heatmap by activity and zone."""
    zone_visits: dict[str, int] = field(default_factory=dict)
    action_distribution: dict[str, int] = field(default_factory=dict)
    time_spent_per_activity: dict[str, float] = field(default_factory=dict)
    progression_timeline: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "zone_visits": self.zone_visits,
            "action_distribution": self.action_distribution,
            "time_spent_per_activity": self.time_spent_per_activity,
            "progression_timeline": self.progression_timeline[:50],  # cap
        }


@dataclass
class SimulationAggregate:
    """Aggregated result from multiple runs."""
    total_runs: int = 0
    crash_rate: float = 0.0
    stuck_rate: float = 0.0
    # Progression
    avg_level: float = 0
    level_variance: float = 0
    progression_slope: float = 0  # levels per hour
    # Economy
    avg_gold_per_hour: float = 0
    avg_gold_balance: float = 0
    economy_inflation: float = 0  # gold growth rate
    gold_variance: float = 0
    # Combat
    avg_win_rate: float = 0
    avg_deaths: float = 0
    # Engagement
    avg_session_length: float = 0  # em segundos
    engagement_rate: float = 0  # % of bots that "continued"
    avg_upgrades: float = 0
    # Outliers
    outlier_count: int = 0
    outlier_details: list[str] = field(default_factory=list)
    # v2: Advanced
    confidence_lower: float = 0.0
    confidence_upper: float = 0.0
    is_bimodal: bool = False
    per_profile_stats: list[ProfileStats] = field(default_factory=list)
    # v3: Heatmap + Retenção
    gameplay_heatmap: GameplayHeatmap = field(default_factory=GameplayHeatmap)
    estimated_retention_d1: float = 0.0
    estimated_retention_d7: float = 0.0
    estimated_retention_d30: float = 0.0
    avg_xp_per_hour: float = 0.0

    def to_quality_metrics(self) -> dict[str, Any]:
        """Convert to a format compatible with QualityMetrics."""
        return {
            "session_length_avg": self.avg_session_length,
            "engagement_rate": self.engagement_rate,
            "crash_rate": self.crash_rate,
            "economy_inflation": self.economy_inflation,
            "progression_slope": self.progression_slope,
            "sim_runs": self.total_runs,
            "sim_variance": self.level_variance,
            "gold_per_hour": self.avg_gold_per_hour,
            "xp_per_hour": self.avg_xp_per_hour,
            "estimated_retention_d1": self.estimated_retention_d1,
            "estimated_retention_d7": self.estimated_retention_d7,
            "estimated_retention_d30": self.estimated_retention_d30,
        }


# ── GAM-01: Simulation Strategies ─────────────────────

class SimulationStrategy(ABC):
    """Abstract base for genre-specific simulation behavior."""

    @abstractmethod
    def run_tick(
        self,
        result: SimulationResult,
        *,
        second: int,
        is_active: bool,
        tick_seconds: int,
        params: dict[str, Any],
        profile: PlayerProfile,
        rng: random.Random,
        state: dict[str, Any],
    ) -> None:
        """Execute one simulation tick, mutating *result* and *state* in-place."""

    @abstractmethod
    def get_default_params(self) -> dict[str, Any]:
        """Return sensible default params for this genre."""

    def init_state(self, params: dict[str, Any], profile: PlayerProfile, rng: random.Random) -> dict[str, Any]:
        """Initialize per-run mutable state. Override if needed."""
        return {}


class IdleRPGStrategy(SimulationStrategy):
    """Original idle-RPG behavioral model (extracted from _run_single)."""

    def get_default_params(self) -> dict[str, Any]:
        return {
            "startingGold": 100, "startingGems": 5,
            "idleGoldPerSecond": 1, "idleXPPerSecond": 0.5,
            "heroBaseHP": 100, "heroBaseATK": 10, "heroBaseDEF": 5,
            "heroLevelUpMultiplier": 1.15, "xpPerLevel": 100,
            "xpScalingFactor": 1.5, "combatTickMs": 1000,
            "critChance": 0.1, "critMultiplier": 2.0,
            "floorsPerDungeon": 5, "enemiesPerFloor": 3,
            "enemyScalingPerFloor": 1.2, "goldDropMin": 5,
            "goldDropMax": 25, "maxOfflineHours": 12,
            "offlineEfficiency": 0.5,
        }

    def init_state(self, params: dict[str, Any], profile: PlayerProfile, rng: random.Random) -> dict[str, Any]:
        return {
            "level": 1, "xp": 0.0, "gold": params["startingGold"],
            "hp": params["heroBaseHP"], "atk": params["heroBaseATK"],
            "defense": params["heroBaseDEF"], "xp_needed": params["xpPerLevel"],
        }

    def run_tick(
        self, result: SimulationResult, *, second: int, is_active: bool,
        tick_seconds: int, params: dict[str, Any], profile: PlayerProfile,
        rng: random.Random, state: dict[str, Any],
    ) -> None:
        # Idle income
        eff = 1.0 if is_active else params["offlineEfficiency"]
        state["gold"] += params["idleGoldPerSecond"] * tick_seconds * eff
        state["xp"] += params["idleXPPerSecond"] * tick_seconds * eff

        # Combat
        if is_active and second % 10 == 0 and rng.random() < profile.combat_priority:
            level = state["level"]
            enemy_hp = 50 * level * params["enemyScalingPerFloor"]
            damage = max(1, state["atk"] - 3)
            if rng.random() < params["critChance"]:
                damage *= params["critMultiplier"]
            hits_to_kill = math.ceil(enemy_hp / damage)
            enemy_damage = 8 * level * hits_to_kill
            result.battles_fought += 1
            if enemy_damage < state["hp"]:
                result.battles_won += 1
                gr = rng.uniform(params["goldDropMin"] * level, params["goldDropMax"] * level)
                state["gold"] += gr
                state["xp"] += 20 * level
                if result.battles_won % int(params["floorsPerDungeon"]) == 0:
                    result.bosses_killed += 1
                    state["gold"] += gr * 3
                    state["xp"] += 40 * level
                    result.dungeons_explored += 1
            else:
                result.deaths += 1

        # Level up
        while state["xp"] >= state["xp_needed"]:
            state["xp"] -= state["xp_needed"]
            state["level"] += 1
            result.levels_gained += 1
            state["xp_needed"] = params["xpPerLevel"] * (params["xpScalingFactor"] ** (state["level"] - 1))
            mult = params["heroLevelUpMultiplier"]
            state["hp"] = params["heroBaseHP"] * (mult ** (state["level"] - 1))
            state["atk"] = params["heroBaseATK"] * (mult ** (state["level"] - 1))

        # Upgrades
        if is_active and state["gold"] > 100 * state["level"] and rng.random() < profile.upgrade_priority:
            cost = 50 * state["level"]
            if state["gold"] >= cost:
                state["gold"] -= cost
                state["atk"] *= 1.05
                result.upgrades_purchased += 1
                result.gold_spent += cost


class PlatformerStrategy(SimulationStrategy):
    """Simple platformer simulation (levels, coins, deaths, wall jumps)."""

    def get_default_params(self) -> dict[str, Any]:
        return {
            "levels_total": 50, "coins_per_level": 15,
            "death_chance": 0.12, "wall_jump_chance": 0.3,
            "time_per_level_seconds": 120, "speed_multiplier": 1.0,
        }

    def init_state(self, params: dict[str, Any], profile: PlayerProfile, rng: random.Random) -> dict[str, Any]:
        return {"current_level": 1, "coins": 0, "deaths": 0, "wall_jumps": 0}

    def run_tick(
        self, result: SimulationResult, *, second: int, is_active: bool,
        tick_seconds: int, params: dict[str, Any], profile: PlayerProfile,
        rng: random.Random, state: dict[str, Any],
    ) -> None:
        if not is_active:
            return
        tpl = max(1, int(params["time_per_level_seconds"] / params["speed_multiplier"]))
        if second % tpl == 0 and second > 0:
            if rng.random() < params["death_chance"]:
                state["deaths"] += 1
                result.deaths += 1
            else:
                state["current_level"] += 1
                result.levels_gained += 1
                coins = int(params["coins_per_level"] * rng.uniform(0.5, 1.5))
                state["coins"] += coins
                result.gold_earned += coins
        if is_active and second % 5 == 0 and rng.random() < params["wall_jump_chance"]:
            state["wall_jumps"] += 1
        result.extra = {
            "levels_completed": state["current_level"] - 1,
            "coins_collected": state["coins"],
            "wall_jumps": state["wall_jumps"],
        }
        result.final_level = state["current_level"]


class PuzzleStrategy(SimulationStrategy):
    """Simple puzzle game simulation (puzzles solved, hints used)."""

    def get_default_params(self) -> dict[str, Any]:
        return {
            "puzzles_total": 100, "time_per_puzzle_seconds": 180,
            "hint_chance": 0.2, "fail_chance": 0.08,
            "difficulty_scaling": 1.05,
        }

    def init_state(self, params: dict[str, Any], profile: PlayerProfile, rng: random.Random) -> dict[str, Any]:
        return {"puzzles_solved": 0, "hints_used": 0, "total_solve_time": 0.0, "difficulty": 1.0}

    def run_tick(
        self, result: SimulationResult, *, second: int, is_active: bool,
        tick_seconds: int, params: dict[str, Any], profile: PlayerProfile,
        rng: random.Random, state: dict[str, Any],
    ) -> None:
        if not is_active:
            return
        solve_time = int(params["time_per_puzzle_seconds"] * state["difficulty"])
        if second % max(1, solve_time) == 0 and second > 0:
            if rng.random() < params["fail_chance"] * state["difficulty"]:
                result.deaths += 1
            else:
                state["puzzles_solved"] += 1
                result.levels_gained += 1
                state["total_solve_time"] += solve_time
                state["difficulty"] *= params["difficulty_scaling"]
            if rng.random() < params["hint_chance"]:
                state["hints_used"] += 1
        result.extra = {
            "puzzles_solved": state["puzzles_solved"],
            "hints_used": state["hints_used"],
            "avg_solve_time": state["total_solve_time"] / max(1, state["puzzles_solved"]),
        }
        result.final_level = state["puzzles_solved"]


class GenericStrategy(SimulationStrategy):
    """Fallback strategy with linear progression for unknown genres."""

    def get_default_params(self) -> dict[str, Any]:
        return {
            "progress_per_minute": 1.0, "points_per_progress": 10,
            "fail_chance": 0.05,
        }

    def init_state(self, params: dict[str, Any], profile: PlayerProfile, rng: random.Random) -> dict[str, Any]:
        return {"progress": 0.0, "points": 0}

    def run_tick(
        self, result: SimulationResult, *, second: int, is_active: bool,
        tick_seconds: int, params: dict[str, Any], profile: PlayerProfile,
        rng: random.Random, state: dict[str, Any],
    ) -> None:
        if not is_active:
            return
        if second % 60 == 0 and second > 0:
            if rng.random() < params["fail_chance"]:
                result.deaths += 1
            else:
                state["progress"] += params["progress_per_minute"]
                state["points"] += int(params["points_per_progress"])
                result.levels_gained += 1
                result.gold_earned += params["points_per_progress"]
        result.extra = {"progress": state["progress"], "points": state["points"]}
        result.final_level = int(state["progress"])


# Strategy registry
_GENRE_STRATEGIES: dict[str, SimulationStrategy] = {
    "idle_rpg": IdleRPGStrategy(),
    "platformer": PlatformerStrategy(),
    "puzzle": PuzzleStrategy(),
    "generic": GenericStrategy(),
}


class PlaytestSimulator:
    """
    Simulates game sessions using heuristic bots with multiple profiles.
    Uses a strategy pattern (GAM-01) to support different game genres.

    v3 upgrades:
    - 5 player profiles (Casual, Hardcore, Optimizer, Explorer, MinMaxer)
    - 50+ runs per iteration
    - Long simulations (up to 720h / 30 days)
    - Confidence intervals and bimodal detection
    - Gameplay heatmaps (zone visits, action distribution)
    - Churn/retention model (d1/d7/d30)
    """

    def __init__(self, game_dir: Path | None = None, genre: str = "idle_rpg") -> None:
        self._game_dir = game_dir or GAME_DIR
        self._rng = random.Random()  # M11: Thread-safe local RNG
        self._genre = genre
        self._strategy = _GENRE_STRATEGIES.get(genre, _GENRE_STRATEGIES["generic"])

    def run_simulation(
        self,
        num_runs: int = 50,
        durations_hours: list[float] | None = None,
        profiles: list[PlayerProfile] | None = None,
        seed: int | None = None,
        genre_hint: str = "idle_rpg",
    ) -> SimulationAggregate:
        """
        Run multiple simulation runs with profile variance.

        Args:
            num_runs: Number of runs per duration
            durations_hours: List of durations to test
            profiles: Profiles to use (default: all 4)
            seed: Random seed for reproducible results (use iteration number)

        Returns:
            SimulationAggregate with aggregated metrics and advanced statistics
        """
        # M11: Thread-safe local RNG instance
        self._rng = random.Random(seed)
        if seed is not None:
            logger.info("🎲 Simulation with seed=%d for reproducible results", seed)

        # GAM-01: Select strategy based on genre
        strategy = _GENRE_STRATEGIES.get(genre_hint, self._strategy)
        if genre_hint not in _GENRE_STRATEGIES:
            logger.warning(
                "⚠️ GAM-01: No strategy for genre '%s', using fallback '%s'.",
                genre_hint, type(strategy).__name__,
            )

        if durations_hours is None:
            durations_hours = [1.0, 6.0, 24.0, 48.0, 168.0, 720.0]

        if profiles is None:
            profiles = list(PlayerProfile)

        # Extract game parameters
        game_params = self._extract_game_params()
        if not game_params:
            logger.warning("Could not extract game parameters")
            return SimulationAggregate()

        all_results: list[SimulationResult] = []

        # Distribute runs among profiles
        runs_per_profile = max(1, num_runs // len(profiles))

        for duration in durations_hours:
            for profile in profiles:
                for i in range(runs_per_profile):
                    result = self._run_single(
                        run_id=len(all_results) + 1,
                        duration_hours=duration,
                        params=game_params,
                        profile=profile,
                    )
                    all_results.append(result)

        aggregate = self._aggregate(all_results)

        logger.info(
            "🎮 Simulation v3 complete: %d runs (%d profiles) | crash=%.0f%% | "
            "avg_level=%.1f | gold/hr=%.0f | CI=[%.1f, %.1f] %s| "
            "Ret d1=%.0f%% d7=%.0f%% d30=%.0f%%",
            aggregate.total_runs,
            len(profiles),
            aggregate.crash_rate * 100,
            aggregate.avg_level,
            aggregate.avg_gold_per_hour,
            aggregate.confidence_lower,
            aggregate.confidence_upper,
            "⚠️ BIMODAL! " if aggregate.is_bimodal else "",
            aggregate.estimated_retention_d1 * 100,
            aggregate.estimated_retention_d7 * 100,
            aggregate.estimated_retention_d30 * 100,
        )

        return aggregate

    def _extract_game_params(self) -> dict[str, Any]:
        """Extract game parameters from JSON config (preferred) or JS fallback."""
        defaults = self._strategy.get_default_params()

        # BE-10: Prefer JSON config — stable, no fragile regex
        json_path = self._game_dir / "src" / "game_config.json"
        if json_path.exists():
            try:
                import json as _json
                data = _json.loads(json_path.read_text(encoding="utf-8"))
                params = dict(defaults)
                params.update({k: float(v) for k, v in data.items() if k in defaults})
                logger.info("Loaded game params from game_config.json (%d keys)", len(data))
                return params
            except Exception as exc:
                logger.warning("Failed to parse game_config.json, falling back to regex: %s", exc)

        # Fallback: regex extraction from config.js
        config_path = self._game_dir / "src" / "config.js"
        if not config_path.exists():
            return {}

        try:
            content = config_path.read_text(encoding="utf-8")
            params: dict[str, Any] = {}

            import re
            for key in defaults:
                pattern = rf"{key}:\s*(\d+\.?\d*)"
                match = re.search(pattern, content)
                if match:
                    params[key] = float(match.group(1))

            for key, default in defaults.items():
                params.setdefault(key, default)

            logger.info("Loaded game params from config.js regex fallback (%d keys)", len(params))
            return params

        except Exception as exc:
            logger.error("Error extracting parameters: %s", exc)
            return {}

    def _run_single(
        self,
        run_id: int,
        duration_hours: float,
        params: dict[str, Any],
        profile: PlayerProfile = PlayerProfile.CASUAL,
    ) -> SimulationResult:
        """
        GAM-01: Simulate a single session delegating to the active strategy.
        """
        strategy = self._strategy
        result = SimulationResult(
            run_id=run_id,
            duration_hours=duration_hours,
            profile=profile.value,
        )

        total_seconds = int(duration_hours * 3600)
        tick_seconds = max(1, int(params.get("combatTickMs", 1000) / 1000))

        ratio_min, ratio_max = profile.active_ratio
        active_ratio = self._rng.uniform(ratio_min, ratio_max)
        active_seconds = int(total_seconds * active_ratio)

        state = strategy.init_state(params, profile, self._rng)

        try:
            for second in range(0, total_seconds, tick_seconds):
                is_active = second < active_seconds
                strategy.run_tick(
                    result,
                    second=second,
                    is_active=is_active,
                    tick_seconds=tick_seconds,
                    params=params,
                    profile=profile,
                    rng=self._rng,
                    state=state,
                )
                # Stuck detection (generic)
                if result.levels_gained == 0 and second > 7200:
                    result.stuck = True
                    break
        except Exception:
            result.crashed = True

        # Fill common result fields from state
        result.final_level = state.get("level", result.final_level)
        result.total_xp = state.get("xp", 0.0)
        result.gold_earned = max(0, state.get("gold", 0) - params.get("startingGold", 0) + result.gold_spent)
        result.gold_balance = state.get("gold", 0.0)
        result.active_minutes = active_seconds / 60
        result.idle_minutes = (total_seconds - active_seconds) / 60

        return result

    def _aggregate(self, results: list[SimulationResult]) -> SimulationAggregate:
        """Aggregate multiple runs into statistical metrics."""
        if not results:
            return SimulationAggregate()

        agg = SimulationAggregate(total_runs=len(results))

        # Crash and stuck rates
        crashes = sum(1 for r in results if r.crashed)
        stucks = sum(1 for r in results if r.stuck)
        agg.crash_rate = crashes / len(results)
        agg.stuck_rate = stucks / len(results)

        # Filtering valid runs
        valid = [r for r in results if not r.crashed]
        if not valid:
            return agg

        # Progression
        levels = [r.final_level for r in valid]
        agg.avg_level = statistics.mean(levels)
        agg.level_variance = statistics.variance(levels) if len(levels) > 1 else 0
        slopes = [r.levels_gained / max(r.duration_hours, 0.1) for r in valid]
        agg.progression_slope = statistics.mean(slopes)

        # Economy
        gold_per_hour = [
            r.gold_earned / max(r.duration_hours, 0.1) for r in valid
        ]
        agg.avg_gold_per_hour = statistics.mean(gold_per_hour)
        agg.avg_gold_balance = statistics.mean([r.gold_balance for r in valid])
        agg.gold_variance = statistics.variance(gold_per_hour) if len(gold_per_hour) > 1 else 0

        # Inflation
        starting_gold = valid[0].gold_balance - valid[0].gold_earned if valid else 100
        if starting_gold > 0 and agg.avg_gold_per_hour > 0:
            agg.economy_inflation = agg.avg_gold_per_hour / (starting_gold * 10)
        else:
            agg.economy_inflation = 0

        # Combat
        win_rates = [
            r.battles_won / max(r.battles_fought, 1) for r in valid
        ]
        agg.avg_win_rate = statistics.mean(win_rates)
        agg.avg_deaths = statistics.mean([r.deaths for r in valid])

        # Engagement
        session_lengths_sec = [r.active_minutes * 60 for r in valid]
        agg.avg_session_length = statistics.mean(session_lengths_sec)
        engaged = sum(
            1 for r in valid
            if r.levels_gained > 0 and r.upgrades_purchased > 0
        )
        agg.engagement_rate = (engaged / len(valid)) * 100

        agg.avg_upgrades = statistics.mean([r.upgrades_purchased for r in valid])

        # Outliers (using IQR on progressions)
        if len(levels) >= 4:
            sorted_levels = sorted(levels)
            q1_idx = len(sorted_levels) // 4
            q3_idx = 3 * len(sorted_levels) // 4
            q1 = sorted_levels[q1_idx]
            q3 = sorted_levels[q3_idx]
            iqr = q3 - q1
            lower = q1 - 1.5 * iqr
            upper = q3 + 1.5 * iqr

            for r in valid:
                if r.final_level < lower or r.final_level > upper:
                    agg.outlier_count += 1
                    agg.outlier_details.append(
                        f"Run {r.run_id} ({r.profile}): level {r.final_level} "
                        f"(expected {q1}-{q3})"
                    )

        # ── v2: Confidence Intervals ──
        agg.confidence_lower, agg.confidence_upper = self._confidence_interval(
            levels
        )

        # ── v2: Bimodal Detection ──
        agg.is_bimodal = self._detect_bimodal(levels)

        # ── v2: Per-Profile Stats ──
        agg.per_profile_stats = self._compute_profile_stats(valid)

        # ── v3: XP per hour ──
        xp_per_hour = [
            r.total_xp / max(r.duration_hours, 0.1) for r in valid
        ]
        agg.avg_xp_per_hour = statistics.mean(xp_per_hour) if xp_per_hour else 0

        # ── v3: Gameplay Heatmap ──
        agg.gameplay_heatmap = self._build_heatmap(valid)

        # ── v3: Churn / Retention Estimation ──
        ret = self._estimate_retention(valid)
        agg.estimated_retention_d1 = ret["d1"]
        agg.estimated_retention_d7 = ret["d7"]
        agg.estimated_retention_d30 = ret["d30"]

        return agg

    # ── Advanced Statistical Methods ─────────────────

    @staticmethod
    def _confidence_interval(
        data: list[int | float],
        confidence: float = 0.95,
    ) -> tuple[float, float]:
        """
        Calculate confidence interval using approximate t-distribution.

        Args:
            data: List of values
            confidence: Confidence level (default 95%)

        Returns:
            (lower, upper) bounds
        """
        if len(data) < 2:
            mean = data[0] if data else 0
            return (mean, mean)

        n = len(data)
        mean = statistics.mean(data)
        se = statistics.stdev(data) / math.sqrt(n)

        # t-critical approximation for 95% CI
        # For n>30, t ≈ 1.96; for n<30, use larger values
        if n >= 120:
            t_crit = 1.96
        elif n >= 30:
            t_crit = 2.0
        elif n >= 15:
            t_crit = 2.13
        else:
            t_crit = 2.26

        margin = t_crit * se
        return (mean - margin, mean + margin)

    @staticmethod
    def _detect_bimodal(data: list[int | float]) -> bool:
        """
        Detect bimodal distribution using simplified Hartigan's dip test
        (gap-based heuristic).

        A bimodal distribution indicates a balance problem:
        two groups of players with very different experiences.

        Args:
            data: List of values

        Returns:
            True if the distribution appears bimodal
        """
        if len(data) < 10:
            return False

        sorted_data = sorted(data)
        n = len(sorted_data)

        # Calculate gaps between consecutive values
        gaps = [
            sorted_data[i + 1] - sorted_data[i]
            for i in range(n - 1)
        ]

        if not gaps:
            return False

        # If the largest gap is significantly larger than the average gap
        max_gap = max(gaps)
        avg_gap = statistics.mean(gaps)

        if avg_gap == 0:
            return False

        # Heuristic: gap > 3x the average suggests bimodality
        gap_ratio = max_gap / avg_gap

        if gap_ratio > 3.0:
            # Check if the gap divides the data into two substantial groups
            gap_idx = gaps.index(max_gap)
            left_size = gap_idx + 1
            right_size = n - left_size

            # Both groups must have at least 20% of the data
            min_group_pct = 0.20
            if (
                left_size / n >= min_group_pct
                and right_size / n >= min_group_pct
            ):
                logger.warning(
                    "⚠️ Bimodal distribution detected! "
                    "Gap ratio: %.1f, groups: %d/%d",
                    gap_ratio, left_size, right_size,
                )
                return True

        return False

    @staticmethod
    def _compute_profile_stats(
        valid_results: list[SimulationResult],
    ) -> list[ProfileStats]:
        """
        Compute separate statistics per player profile.

        Args:
            valid_results: Valid results (no crashes)

        Returns:
            List of ProfileStats per profile
        """
        profile_groups: dict[str, list[SimulationResult]] = {}

        for r in valid_results:
            profile_groups.setdefault(r.profile, []).append(r)

        stats_list: list[ProfileStats] = []

        for profile_name, results in profile_groups.items():
            levels = [r.final_level for r in results]
            gold_rates = [
                r.gold_earned / max(r.duration_hours, 0.1) for r in results
            ]
            deaths = [r.deaths for r in results]
            engaged = sum(
                1 for r in results
                if r.levels_gained > 0 and r.upgrades_purchased > 0
            )

            stats_list.append(ProfileStats(
                profile=profile_name,
                runs=len(results),
                avg_level=statistics.mean(levels) if levels else 0,
                avg_gold_per_hour=statistics.mean(gold_rates) if gold_rates else 0,
                avg_deaths=statistics.mean(deaths) if deaths else 0,
                engagement_rate=(engaged / len(results)) * 100 if results else 0,
            ))

        return stats_list

    # ── v3: Heatmap & Retention Methods ───────────────

    @staticmethod
    def _build_heatmap(
        valid_results: list[SimulationResult],
    ) -> GameplayHeatmap:
        """
        v3: Build gameplay heatmap from simulation results.
        Tracks zone visits, action distribution, and time per activity.
        """
        heatmap = GameplayHeatmap()

        for r in valid_results:
            # Zone visits (estimated by dungeon activity)
            if r.dungeons_explored > 0:
                heatmap.zone_visits["dungeons"] = (
                    heatmap.zone_visits.get("dungeons", 0) + r.dungeons_explored
                )
            heatmap.zone_visits["overworld"] = (
                heatmap.zone_visits.get("overworld", 0) + 1
            )
            if r.upgrades_purchased > 0:
                heatmap.zone_visits["shop"] = (
                    heatmap.zone_visits.get("shop", 0) + r.upgrades_purchased
                )

            # Action distribution
            heatmap.action_distribution["idle"] = (
                heatmap.action_distribution.get("idle", 0)
                + int(r.idle_minutes)
            )
            heatmap.action_distribution["active"] = (
                heatmap.action_distribution.get("active", 0)
                + int(r.active_minutes)
            )
            heatmap.action_distribution["combat"] = (
                heatmap.action_distribution.get("combat", 0)
                + r.battles_fought
            )
            heatmap.action_distribution["upgrade"] = (
                heatmap.action_distribution.get("upgrade", 0)
                + r.upgrades_purchased
            )

            # Time spent per activity
            heatmap.time_spent_per_activity["idle"] = (
                heatmap.time_spent_per_activity.get("idle", 0.0)
                + r.idle_minutes
            )
            heatmap.time_spent_per_activity["active"] = (
                heatmap.time_spent_per_activity.get("active", 0.0)
                + r.active_minutes
            )

            # Progression timeline
            if r.duration_hours >= 1:
                heatmap.progression_timeline.append({
                    "profile": r.profile,
                    "hours": r.duration_hours,
                    "level": float(r.final_level),
                    "gold": r.gold_balance,
                    "xp": r.total_xp,
                })

        return heatmap

    @staticmethod
    def _estimate_retention(
        valid_results: list[SimulationResult],
    ) -> dict[str, float]:
        """
        v3: Estimate player retention at day 1, day 7, day 30.
        Based on engagement rate and session length heuristics.

        Model:
        - d1: players who engage (level > 1, upgrades > 0) keep playing
        - d7: sustained engagement requires moderate progression
        - d30: only if economy is healthy and no stuckness
        """
        if not valid_results:
            return {"d1": 0.0, "d7": 0.0, "d30": 0.0}

        total = len(valid_results)

        # Day 1: player engages within first session
        d1_engaged = sum(
            1 for r in valid_results
            if r.levels_gained > 0
            and r.active_minutes > 5
            and not r.stuck
        )
        d1 = d1_engaged / total

        # Day 7: player has meaningful progress + not stuck + reasonable economy
        d7_engaged = sum(
            1 for r in valid_results
            if r.final_level >= 3
            and r.upgrades_purchased > 0
            and r.gold_balance > 0
            and not r.stuck
            and r.deaths < r.duration_hours * 2  # Not dying too much
        )
        d7 = d7_engaged / total

        # Day 30: deep progress, healthy economy, high engagement
        d30_engaged = sum(
            1 for r in valid_results
            if r.final_level >= 5
            and r.dungeons_explored > 0
            and r.gold_balance > 0
            and not r.stuck
            and not r.crashed
            and r.upgrades_purchased >= 2
        )
        d30 = d30_engaged / total

        return {
            "d1": min(d1, 1.0),
            "d7": min(d7, 1.0),
            "d30": min(d30, 1.0),
        }
