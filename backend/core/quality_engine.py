"""
GORVAX GAME FACTORY — Quality Engine v2.1
Motor de qualidade multi-objetivo com 7 dimensões (fun, stability,
performance, balance, novelty, retention, integration), confidence
intervals, trend analysis avançado, e auto-tuning de pesos.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class QualityMetrics:
    """Métricas brutas coletadas do Tester + Simulator."""
    # Fun & engagement
    fun_score: float = 0.0            # 0-100, avaliação do Tester
    session_length_avg: float = 0.0   # segundos médios de sessão simulada
    engagement_rate: float = 0.0      # % de bots que "continuaram jogando"

    # Stability
    crash_rate: float = 0.0           # % de runs que crasharam
    build_success: bool = False       # build compilou?
    error_count: int = 0              # erros detectados no código

    # Performance
    file_count: int = 0               # total de arquivos JS
    total_lines: int = 0              # total de linhas
    bundle_size_kb: float = 0.0       # tamanho estimado do bundle

    # Balance
    economy_inflation: float = 0.0    # taxa de inflação da economia
    progression_slope: float = 0.0    # velocidade de progressão
    difficulty_curve: float = 0.0     # curva de dificuldade (0=flat, 1=ideal, 2=steep)

    # Novelty
    novelty_score: float = 0.0        # distância das versões anteriores

    # Simulation data
    sim_runs: int = 0                 # quantidade de runs simulados
    sim_variance: float = 0.0         # variância entre runs
    gold_per_hour: float = 0.0        # ouro por hora simulado
    xp_per_hour: float = 0.0          # XP por hora simulado

    # v2: Retention
    estimated_retention_d1: float = 0.0
    estimated_retention_d7: float = 0.0
    estimated_retention_d30: float = 0.0

    # v2.1: Integration — measurable from code scan
    integration_score: float = 0.0   # 0-100, from roadmap progress %

    # v2.2: Headless health — runtime health from browser test
    headless_health_score: float = -1.0  # 0-100, -1 means not available


@dataclass
class QualityBreakdown:
    """Score decomposto por dimensão."""
    fun: float = 0.0
    stability: float = 0.0
    performance: float = 0.0
    balance: float = 0.0
    novelty: float = 0.0
    retention: float = 0.0            # v2: retenção estimada
    integration: float = 0.0          # v2.1: code integration score
    regression_penalty: float = 0.0
    composite: float = 0.0
    # v2: Confidence interval
    confidence_lower: float = 0.0
    confidence_upper: float = 0.0


# Pesos base da fórmula multi-objetivo
# v2.1: Reduced fun/retention (LLM-imagined), added integration (measurable)
# v2.3: Boosted integration (0.15→0.22) — only 1/17 tasks complete after 100 iters
#        Reduced fun (0.15→0.10) and novelty (0.12→0.08) — inflated by LLM imagination
DEFAULT_WEIGHTS = {
    "fun": 0.10,            # v2.3: Reduced further — LLM-imagined, not measured
    "stability": 0.19,
    "performance": 0.14,
    "balance": 0.12,
    "novelty": 0.08,        # v2.3: Reduced further — LLM-imagined, not measured
    "retention": 0.07,      # Reduced — LLM-imagined, not measured
    "integration": 0.22,    # v2.3: Boosted — measurable from code scan, drives task completion
    "regression_penalty": 0.08,  # v2.3: Boosted — penalize regressions more
}


class QualityEngine:
    """
    Motor de qualidade multi-objetivo v2.

    quality_score =
        w_fun * fun + w_stab * stability + w_perf * performance +
        w_bal * balance + w_nov * novelty + w_ret * retention -
        w_reg * regression_penalty

    v2: Confidence intervals, auto-tuning, retention, advanced trends.
    """

    def __init__(self) -> None:
        self._history: list[QualityBreakdown] = []
        self._weights: dict[str, float] = dict(DEFAULT_WEIGHTS)
        self._auto_tune_every: int = 5  # re-tune weights every N evals
        self._grace_period_remaining: int = 0  # P10: suppress regression after major changes
        # PERF-02: Incremental running sums for auto-tuning (last 10)
        self._running_sums: dict[str, float] = {
            "fun": 0.0, "stability": 0.0, "performance": 0.0,
            "balance": 0.0, "novelty": 0.0, "retention": 0.0,
            "integration": 0.0,
        }
        self._running_window: int = 10

    def signal_major_change(self) -> None:
        """Signal a major GDD change — suppress regression for 2 iterations."""
        self._grace_period_remaining = 2
        logger.info("⏳ Grace period activated: regression suppressed for 2 iterations")

    def evaluate(
        self,
        metrics: QualityMetrics,
        previous_metrics: QualityMetrics | None = None,
    ) -> QualityBreakdown:
        """
        Calcula o score composto a partir das métricas brutas.
        v2: inclui retention, confidence intervals, e auto-tuning.
        """
        # v2: Auto-tune weights periodically
        if len(self._history) > 0 and len(self._history) % self._auto_tune_every == 0:
            self._auto_tune_weights()

        fun = self._compute_fun(metrics)
        stability = self._compute_stability(metrics)
        performance = self._compute_performance(metrics)
        balance = self._compute_balance(metrics)
        novelty = self._compute_novelty(metrics)
        retention = self._compute_retention(metrics)
        integration = self._compute_integration(metrics)
        regression = self._compute_regression(metrics, previous_metrics)

        w = self._weights
        composite = (
            w["fun"] * fun
            + w["stability"] * stability
            + w["performance"] * performance
            + w["balance"] * balance
            + w["novelty"] * novelty
            + w["retention"] * retention
            + w["integration"] * integration
            - w["regression_penalty"] * regression
        )
        composite = max(0.0, min(100.0, composite))

        # v2: Confidence interval from sub-score variance
        sub_scores = [fun, stability, performance, balance, novelty, retention, integration]
        ci_lower, ci_upper = self._compute_confidence_interval(
            composite, sub_scores
        )

        breakdown = QualityBreakdown(
            fun=round(fun, 1),
            stability=round(stability, 1),
            performance=round(performance, 1),
            balance=round(balance, 1),
            novelty=round(novelty, 1),
            retention=round(retention, 1),
            integration=round(integration, 1),
            regression_penalty=round(regression, 1),
            composite=round(composite, 1),
            confidence_lower=round(ci_lower, 1),
            confidence_upper=round(ci_upper, 1),
        )

        self._history.append(breakdown)

        # PERF-02: Update running sums incrementally
        n = len(self._history)
        for dim in self._running_sums:
            self._running_sums[dim] += getattr(breakdown, dim)
            # Remove oldest if window exceeded
            if n > self._running_window:
                old = self._history[n - self._running_window - 1]
                self._running_sums[dim] -= getattr(old, dim)

        logger.info(
            "Quality v2.1: %.1f [%.1f-%.1f] (fun=%.0f stab=%.0f perf=%.0f "
            "bal=%.0f nov=%.0f ret=%.0f int=%.0f reg=-%.0f)",
            composite, ci_lower, ci_upper,
            fun, stability, performance, balance, novelty, retention,
            integration, regression,
        )

        return breakdown

    # ── Dimensão: Fun ──────────────────────────────────

    def _compute_fun(self, m: QualityMetrics) -> float:
        """
        Fun = mix de avaliação do Tester + métricas de engajamento simulado.
        """
        score = 0.0

        # Tester fun score (50% do peso)
        score += m.fun_score * 0.5

        # Session length: 60s = 0, 300s = 100 (5 min target)
        if m.session_length_avg > 0:
            session_score = min(100.0, (m.session_length_avg / 300.0) * 100.0)
            score += session_score * 0.25

        # Engagement rate (25% do peso)
        score += m.engagement_rate * 0.25

        return min(100.0, score)

    # ── Dimensão: Stability ────────────────────────────

    def _compute_stability(self, m: QualityMetrics) -> float:
        """
        Stability = build success + crash rate + error count + headless health.
        v2.2: When headless_health_score is available, blend it in (40% weight)
        so a game with green squares / no rendering is heavily penalized.
        """
        if not m.build_success:
            return 10.0  # Build falhou = score mínimo

        score = 70.0  # Base por build ter passado

        # Crash rate: 0% = +30, 100% = +0
        crash_penalty = m.crash_rate * 30.0
        score += 30.0 - crash_penalty

        # Erros no código
        error_penalty = min(20.0, m.error_count * 5.0)
        score -= error_penalty

        build_score = max(0.0, min(100.0, score))

        # v2.2: Blend with headless health score if available
        if m.headless_health_score >= 0:
            # 60% build-based, 40% headless-based
            return 0.6 * build_score + 0.4 * m.headless_health_score

        return build_score

    # ── Dimensão: Performance ──────────────────────────

    def _compute_performance(self, m: QualityMetrics) -> float:
        """
        Performance = file count + total lines + bundle size.
        Penaliza código excessivamente grande ou vazio.
        """
        score = 50.0  # Base

        # Arquivos: ideal 8-20
        if m.file_count < 3:
            score -= 20.0
        elif 8 <= m.file_count <= 20:
            score += 20.0
        elif m.file_count > 30:
            score -= 10.0
        else:
            score += 10.0

        # Linhas: ideal 500-3000
        if m.total_lines < 100:
            score -= 20.0
        elif 500 <= m.total_lines <= 3000:
            score += 20.0
        elif m.total_lines > 5000:
            score -= 10.0
        else:
            score += 10.0

        # Bundle: ideal < 500KB
        if 0 < m.bundle_size_kb <= 500:
            score += 10.0
        elif m.bundle_size_kb > 1000:
            score -= 10.0

        return max(0.0, min(100.0, score))

    # ── Dimensão: Balance ──────────────────────────────

    def _compute_balance(self, m: QualityMetrics) -> float:
        """
        Balance = economia saudável + progressão adequada.
        """
        score = 50.0

        # Inflação: ideal 0.01-0.05 por hora
        if 0.01 <= m.economy_inflation <= 0.05:
            score += 25.0
        elif m.economy_inflation > 0.2:
            score -= 20.0  # Hiperinflação
        elif m.economy_inflation < 0.001 and m.sim_runs > 0:
            score -= 15.0  # Economia estagnada

        # Progressão: slope ideal 0.5-1.5
        if 0.5 <= m.progression_slope <= 1.5:
            score += 25.0
        elif m.progression_slope > 3.0:
            score -= 15.0  # Muito rápido
        elif m.progression_slope < 0.1 and m.sim_runs > 0:
            score -= 15.0  # Muito lento

        return max(0.0, min(100.0, score))

    # ── Dimensão: Novelty ──────────────────────────────

    def _compute_novelty(self, m: QualityMetrics) -> float:
        """
        Novelty = distância em relação a versões anteriores.
        Score 0 (clones) a 100 (totalmente novo).
        """
        # Se não temos novelty score do diff analyzer, dar score neutro
        if m.novelty_score <= 0:
            return 50.0  # Neutro
        return min(100.0, m.novelty_score)

    # ── Dimensão: Retention (v2) ───────────────────

    def _compute_retention(self, m: QualityMetrics) -> float:
        """
        v2: Retention = estimated player retention.
        Based on d1/d7/d30 retention rates.
        """
        if m.estimated_retention_d1 <= 0 and m.estimated_retention_d7 <= 0:
            return 50.0  # No data, neutral

        score = 0.0
        # d1 retention: ideal > 50%
        score += min(40.0, m.estimated_retention_d1 * 100 * 0.4)
        # d7 retention: ideal > 30%
        score += min(35.0, m.estimated_retention_d7 * 100 * (35.0 / 30.0))
        # d30 retention: ideal > 15%
        score += min(25.0, m.estimated_retention_d30 * 100 * (25.0 / 15.0))

        return min(100.0, score)

    # ── Dimensão: Integration (v2.1) ───────────────

    @staticmethod
    def _compute_integration(m: QualityMetrics) -> float:
        """
        v2.1: Integration = measurable code integration quality.
        Based on roadmap progress percentage (how many systems are
        actually imported and used in MainScene, not just file existence).
        This is the most reliable dimension since it's measured from
        actual code, not LLM-imagined values.
        """
        # integration_score is set from roadmap.scan_progress() in evaluate_finalize
        if m.integration_score <= 0:
            return 30.0  # No data — below neutral to encourage integration
        return min(100.0, m.integration_score)

    # ── Regression Penalty ─────────────────────────────

    def _compute_regression(
        self,
        current: QualityMetrics,
        previous: QualityMetrics | None,
    ) -> float:
        """
        Penalidade por regressão em relação à iteração anterior.
        Retorna 0-100. Quanto maior, pior (mais regressão).
        Softened thresholds to avoid punishing necessary changes.
        """
        if previous is None:
            return 0.0  # Primeira iteração, sem referência

        # P10: Grace period after major changes
        if self._grace_period_remaining > 0:
            self._grace_period_remaining -= 1
            logger.info("⏳ Grace period active (%d remaining), regression=0", self._grace_period_remaining)
            return 0.0

        penalty = 0.0

        # Regressão de crash rate (tolerância aumentada)
        if current.crash_rate > previous.crash_rate + 0.15:
            penalty += 25.0

        # Regressão de build (ainda é grave)
        if previous.build_success and not current.build_success:
            penalty += 35.0

        # Regressão de session length (tolerância 50%)
        if (
            previous.session_length_avg > 0
            and current.session_length_avg < previous.session_length_avg * 0.5
        ):
            penalty += 15.0

        # Regressão de erros (tolerância maior)
        if current.error_count > previous.error_count + 5:
            penalty += 10.0

        return min(80.0, penalty)  # Cap reduzido

    # ── v2: Confidence Interval ────────────────────

    @staticmethod
    def _compute_confidence_interval(
        composite: float,
        sub_scores: list[float],
    ) -> tuple[float, float]:
        """
        v2: Compute confidence interval for composite score.
        Uses standard deviation of sub-scores as uncertainty proxy.
        """
        if len(sub_scores) < 2:
            return (composite, composite)

        mean = sum(sub_scores) / len(sub_scores)
        variance = sum((s - mean) ** 2 for s in sub_scores) / (len(sub_scores) - 1)
        std = math.sqrt(variance)

        # CI width scales with disagreement between dimensions
        margin = std * 0.5  # 0.5 = conservative estimate
        lower = max(0.0, composite - margin)
        upper = min(100.0, composite + margin)
        return (lower, upper)

    # ── v2: Auto-Tuning ──────────────────────────

    def _auto_tune_weights(self) -> None:
        """
        v2: Auto-tune dimension weights based on historical weakness.
        PERF-02: Uses incremental running sums instead of full iteration.
        """
        if len(self._history) < 5:
            return

        window = min(len(self._history), self._running_window)
        dim_avgs = {
            dim: self._running_sums[dim] / window
            for dim in self._running_sums
        }
        overall_avg = sum(dim_avgs.values()) / len(dim_avgs)
        if overall_avg == 0:
            return

        # B7: Adjust proportionally to how far dimension deviates from mean
        base_adjustment = 0.02
        for dim, avg in dim_avgs.items():
            ratio = avg / overall_avg
            if ratio < 0.8:  # Weak dimension
                strength = base_adjustment * (1.0 - ratio)  # stronger when weaker
                self._weights[dim] = min(
                    0.30, self._weights[dim] + strength
                )
            elif ratio > 1.2:  # Strong dimension
                strength = base_adjustment * (ratio - 1.0) * 0.5
                self._weights[dim] = max(
                    0.05, self._weights[dim] - strength
                )

        # Re-normalize to sum to 1.0 (excluding regression_penalty)
        positive_dims = [k for k in self._weights if k != "regression_penalty"]
        total = sum(self._weights[k] for k in positive_dims)
        reg_w = self._weights["regression_penalty"]
        target_sum = 1.0 - reg_w
        if total > 0:
            for k in positive_dims:
                self._weights[k] = self._weights[k] / total * target_sum

        logger.info(
            "\u2699\ufe0f Quality weights auto-tuned: %s",
            {k: round(v, 3) for k, v in self._weights.items()},
        )

    # ── Helpers ────────────────────────────────────────

    def get_history(self) -> list[dict[str, Any]]:
        """Retorna o histórico de breakdowns."""
        return [
            {
                "fun": b.fun,
                "stability": b.stability,
                "performance": b.performance,
                "balance": b.balance,
                "novelty": b.novelty,
                "retention": b.retention,
                "integration": b.integration,
                "regression_penalty": b.regression_penalty,
                "composite": b.composite,
                "confidence_lower": b.confidence_lower,
                "confidence_upper": b.confidence_upper,
            }
            for b in self._history
        ]

    def get_trend(self, window: int = 5) -> dict[str, Any]:
        """
        v2: Advanced trend analysis with multiple windows
        and per-dimension breakdowns.
        """
        if len(self._history) < 3:
            return {"overall": "insufficient_data", "windows": {}}

        result: dict[str, Any] = {"windows": {}, "per_dimension": {}}

        for w in [3, 5, 10]:
            if len(self._history) < w * 2:
                continue
            recent = [b.composite for b in self._history[-w:]]
            older = [b.composite for b in self._history[-w * 2:-w]]
            avg_recent = sum(recent) / len(recent)
            avg_older = sum(older) / len(older)
            delta = avg_recent - avg_older
            if delta > 3:
                label = "improving"
            elif delta < -3:
                label = "declining"
            else:
                label = "stable"
            result["windows"][f"w{w}"] = {
                "trend": label,
                "delta": round(delta, 2),
            }

        # Per-dimension trends (last 5)
        if len(self._history) >= 10:
            for dim in ["fun", "stability", "performance", "balance", "novelty", "retention", "integration"]:
                recent_vals = [getattr(b, dim, 0) for b in self._history[-5:]]
                older_vals = [getattr(b, dim, 0) for b in self._history[-10:-5]]
                delta = sum(recent_vals) / 5 - sum(older_vals) / 5
                result["per_dimension"][dim] = {
                    "trend": "improving" if delta > 3 else ("declining" if delta < -3 else "stable"),
                    "delta": round(delta, 2),
                }

        # Overall trend
        if result["windows"]:
            trends = [w["trend"] for w in result["windows"].values()]
            if all(t == "improving" for t in trends):
                result["overall"] = "improving"
            elif all(t == "declining" for t in trends):
                result["overall"] = "declining"
            else:
                result["overall"] = "mixed"
        else:
            result["overall"] = "insufficient_data"

        return result

    def get_weights(self) -> dict[str, float]:
        """v2: Returns the current (possibly auto-tuned) weights."""
        return dict(self._weights)

    @staticmethod
    def metrics_from_dict(data: dict[str, Any]) -> QualityMetrics:
        """Cria QualityMetrics a partir de um dicionário."""
        return QualityMetrics(
            fun_score=data.get("fun_score", 0),
            session_length_avg=data.get("session_length_avg", 0),
            engagement_rate=data.get("engagement_rate", 0),
            crash_rate=data.get("crash_rate", 0),
            build_success=data.get("build_success", False),
            error_count=data.get("error_count", 0),
            file_count=data.get("file_count", 0),
            total_lines=data.get("total_lines", 0),
            bundle_size_kb=data.get("bundle_size_kb", 0),
            economy_inflation=data.get("economy_inflation", 0),
            progression_slope=data.get("progression_slope", 0),
            difficulty_curve=data.get("difficulty_curve", 0),
            novelty_score=data.get("novelty_score", 0),
            sim_runs=data.get("sim_runs", 0),
            sim_variance=data.get("sim_variance", 0),
            gold_per_hour=data.get("gold_per_hour", 0),
            xp_per_hour=data.get("xp_per_hour", 0),
            estimated_retention_d1=data.get("estimated_retention_d1", 0),
            estimated_retention_d7=data.get("estimated_retention_d7", 0),
            estimated_retention_d30=data.get("estimated_retention_d30", 0),
            integration_score=data.get("integration_score", 0),
        )
