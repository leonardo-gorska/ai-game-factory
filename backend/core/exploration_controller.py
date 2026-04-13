"""
GORVAX GAME FACTORY — Exploration Controller
Intelligent exploration vs exploitation using UCB1 and adaptive epsilon-greedy.

Replaces the binary explore/exploit mode in StagnationGuard with a
mathematically-grounded controller that balances discovering new
strategies vs refining known-good ones.
"""

from __future__ import annotations

import logging
import math
import random
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ArmStats:
    """Statistics for one arm (strategy) in the multi-armed bandit."""
    name: str
    pulls: int = 0
    total_reward: float = 0.0
    best_reward: float = 0.0

    @property
    def avg_reward(self) -> float:
        return self.total_reward / max(self.pulls, 1)


@dataclass
class ExplorationDecision:
    """Result of an exploration vs exploitation decision."""
    mode: str                  # "explore" | "exploit" | "hybrid"
    temperature: float         # LLM sampling temperature (0.0 - 1.0)
    strategy: str              # Which strategy/arm was selected
    confidence: float          # How confident we are (0.0 - 1.0)
    reasoning: str             # Human-readable explanation
    ucb_scores: dict[str, float] = field(default_factory=dict)

    @property
    def is_exploring(self) -> bool:
        """True when mode is 'explore' or 'hybrid'."""
        return self.mode in ("explore", "hybrid")

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "temperature": self.temperature,
            "strategy": self.strategy,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
            "ucb_scores": self.ucb_scores,
        }


class ExplorationController:
    """
    Multi-armed bandit controller using UCB1 + adaptive epsilon-greedy.

    Arms represent different mutation strategies:
    - conservative: small changes, low temperature
    - balanced: moderate changes, medium temperature
    - aggressive: major changes, high temperature
    - radical: completely new approach, very high temperature

    The controller learns which strategy works best over time and
    balances exploration of new strategies vs exploiting proven ones.
    """

    # ── Default strategies ────────────────────────────

    DEFAULT_STRATEGIES: dict[str, float] = {
        "conservative": 0.4,
        "balanced": 0.7,
        "aggressive": 0.9,
        "radical": 1.0,
    }

    def __init__(
        self,
        strategies: dict[str, float] | None = None,
        epsilon_start: float = 0.3,
        epsilon_min: float = 0.05,
        epsilon_decay: float = 0.995,
        ucb_c: float = 1.414,  # sqrt(2) — standard UCB1 exploration parameter
        seed: int | None = None,
    ) -> None:
        self.strategies = strategies or self.DEFAULT_STRATEGIES
        self.epsilon = epsilon_start
        self.epsilon_min = epsilon_min
        self.epsilon_decay = epsilon_decay
        self.ucb_c = ucb_c

        # M5: Thread-safe local RNG instance
        self._rng = random.Random(seed)

        # Initialize arms
        self.arms: dict[str, ArmStats] = {
            name: ArmStats(name=name) for name in self.strategies
        }
        self.total_pulls = 0
        self.history: list[dict[str, Any]] = []

    def decide(
        self,
        is_stagnated: bool = False,
        current_score: float = 0.0,
        score_trend: float = 0.0,
    ) -> ExplorationDecision:
        """
        Decide exploration strategy for the next iteration.

        Uses a hybrid approach:
        1. UCB1 for arm selection when we have enough data
        2. Epsilon-greedy as a fallback
        3. Forced exploration when stagnated

        Args:
            is_stagnated: Whether the StagnationGuard detected stagnation
            current_score: Current quality score (0-100)
            score_trend: Score change over recent iterations

        Returns:
            ExplorationDecision with strategy, temperature, and reasoning
        """
        # Phase 1: If stagnated, force exploration with aggressive/radical
        if is_stagnated:
            return self._forced_exploration(current_score)

        # Phase 2: If too few pulls, do pure exploration
        if self.total_pulls < len(self.arms) * 2:
            return self._initial_exploration()

        # Phase 3: UCB1 + epsilon-greedy hybrid
        return self._ucb_decision(current_score, score_trend)

    def record_outcome(self, strategy: str, reward: float) -> None:
        """
        Record the outcome of a strategy.

        Args:
            strategy: Which strategy was used
            reward: Normalized reward (0.0 - 1.0), typically quality_score / 100
        """
        arm = self.arms.get(strategy)
        if not arm:
            logger.warning("Unknown strategy '%s', ignoring outcome", strategy)
            return

        arm.pulls += 1
        arm.total_reward += reward
        arm.best_reward = max(arm.best_reward, reward)
        self.total_pulls += 1

        # Decay epsilon
        self.epsilon = max(self.epsilon_min, self.epsilon * self.epsilon_decay)

        self.history.append({
            "strategy": strategy,
            "reward": reward,
            "epsilon": self.epsilon,
            "total_pulls": self.total_pulls,
        })

        logger.debug(
            "📊 Exploration: strategy=%s reward=%.3f avg=%.3f pulls=%d eps=%.3f",
            strategy, reward, arm.avg_reward, arm.pulls, self.epsilon,
        )

    def get_stats(self) -> dict[str, Any]:
        """Get current exploration controller statistics."""
        return {
            "epsilon": self.epsilon,
            "total_pulls": self.total_pulls,
            "arms": {
                name: {
                    "pulls": arm.pulls,
                    "avg_reward": float(f"{arm.avg_reward:.4f}"),
                    "best_reward": float(f"{arm.best_reward:.4f}"),
                }
                for name, arm in self.arms.items()
            },
            "best_strategy": max(
                self.arms.values(),
                key=lambda a: a.avg_reward,
            ).name if self.total_pulls > 0 else None,
            "history_length": len(self.history),
        }

    # ── Internal decision strategies ──────────────────

    def _forced_exploration(self, current_score: float) -> ExplorationDecision:
        """Force exploration when stagnation is detected."""
        # Pick aggressive or radical, weighted by how bad the stagnation is
        if current_score < 30:
            strategy = "radical"
        elif current_score < 60:
            strategy = self._rng.choice(["aggressive", "radical"])
        else:
            strategy = self._rng.choice(["balanced", "aggressive"])

        temp = self.strategies[strategy]

        return ExplorationDecision(
            mode="explore",
            temperature=temp,
            strategy=strategy,
            confidence=0.3,  # Low confidence during forced exploration
            reasoning=(
                f"Stagnation detected (score={current_score:.0f}). "
                f"Forcing {strategy} exploration at temp={temp}."
            ),
            ucb_scores=self._compute_ucb_scores(),
        )

    def _initial_exploration(self) -> ExplorationDecision:
        """Pure exploration phase — try each arm at least twice."""
        # Find least-pulled arm
        least_pulled = min(self.arms.values(), key=lambda a: a.pulls)
        strategy = least_pulled.name
        temp = self.strategies[strategy]

        return ExplorationDecision(
            mode="explore",
            temperature=temp,
            strategy=strategy,
            confidence=0.2,
            reasoning=(
                f"Initial exploration phase ({self.total_pulls}/{len(self.arms) * 2}). "
                f"Trying '{strategy}' (pulled {least_pulled.pulls} times)."
            ),
        )

    def _ucb_decision(self, current_score: float, score_trend: float) -> ExplorationDecision:
        """UCB1 + epsilon-greedy hybrid decision."""
        ucb_scores = self._compute_ucb_scores()

        # Epsilon-greedy: explore randomly with probability epsilon
        if self._rng.random() < self.epsilon:
            strategy = self._rng.choice(list(self.arms.keys()))
            temp: float = self.strategies[strategy]

            return ExplorationDecision(
                mode="explore",
                temperature=temp,
                strategy=strategy,
                confidence=0.5,
                reasoning=(
                    f"Epsilon-greedy exploration (ε={self.epsilon:.3f}). "
                    f"Randomly selected '{strategy}'."
                ),
                ucb_scores=ucb_scores,
            )

        # Exploit: pick the arm with highest UCB score
        strategy = max(ucb_scores, key=ucb_scores.get)  # type: ignore
        arm = self.arms[strategy]
        temp = self.strategies[strategy]

        # Adjust temperature based on trend
        if score_trend > 0:
            # Scores are improving — slightly lower temp to refine
            temp = max(0.3, temp - 0.1)
            mode = "exploit"
        elif score_trend < -5:
            # Scores dropping — boost exploration
            temp = min(1.0, temp + 0.15)
            mode = "hybrid"
        else:
            mode = "exploit"

        confidence = min(0.95, arm.pulls / (self.total_pulls + 1) * 2)

        return ExplorationDecision(
            mode=mode,
            temperature=temp,
            strategy=strategy,
            confidence=confidence,
            reasoning=(
                f"UCB1 selected '{strategy}' (UCB={ucb_scores[strategy]:.3f}, "
                f"avg={arm.avg_reward:.3f}, pulls={arm.pulls}). "
                f"Mode={mode}, trend={score_trend:+.1f}."
            ),
            ucb_scores=ucb_scores,
        )

    def _compute_ucb_scores(self) -> dict[str, float]:
        """Compute UCB1 scores for all arms."""
        if self.total_pulls == 0:
            return {name: float("inf") for name in self.arms}

        scores: dict[str, float] = {}
        log_total = math.log(self.total_pulls)

        for name, arm in self.arms.items():
            if arm.pulls == 0:
                scores[name] = float("inf")  # Unpulled arms have infinite priority
            else:
                exploitation = arm.avg_reward
                exploration_bonus = self.ucb_c * math.sqrt(log_total / arm.pulls)
                scores[name] = exploitation + exploration_bonus

        return scores
