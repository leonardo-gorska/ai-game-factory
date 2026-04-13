"""
GORVAX GAME FACTORY — Experiment Tracker (Phase 3 + Roadmap v3)
Mini-MLflow local: salva, compara e exporta snapshots de cada iteração
para tracking completo de parâmetros, métricas e configurações.
Inclui prompt tuning metadata (Item #3).
"""

from __future__ import annotations

import csv
import io
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.config import ITERATIONS_DIR

logger = logging.getLogger(__name__)


@dataclass
class ExperimentSnapshot:
    """Complete snapshot of one pipeline iteration."""

    iteration: int
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    # ── Parameters ─────────────────────────────────────
    llm_temperature: float = 0.7
    quality_weights: dict[str, float] = field(default_factory=dict)
    exploration_mode: bool = False
    provider_used: str = ""

    # ── Metrics ────────────────────────────────────────
    quality_score: float = 0.0
    quality_breakdown: dict[str, float] = field(default_factory=dict)
    novelty_score: float = 0.0
    performance_score: float = 0.0
    sim_runs: int = 0
    sim_crash_rate: float = 0.0
    sim_engagement: float = 0.0
    diff_risk_score: float = 0.0

    # ── Cost ───────────────────────────────────────────
    cost_usd: float = 0.0
    tokens_used: int = 0

    # ── Status ─────────────────────────────────────────
    build_success: bool = False
    iteration_status: str = ""  # "complete", "failed", "rollback"

    # ── Tags ───────────────────────────────────────────
    tags: list[str] = field(default_factory=list)

    # ── Prompt Tuning (Roadmap v3 Item #3) ─────────────
    prompt_hashes: dict[str, str] = field(default_factory=dict)
    prompt_variants: dict[str, str] = field(default_factory=dict)

    # ── Extra ──────────────────────────────────────────
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "iteration": self.iteration,
            "timestamp": self.timestamp,
            "parameters": {
                "llm_temperature": self.llm_temperature,
                "quality_weights": self.quality_weights,
                "exploration_mode": self.exploration_mode,
                "provider_used": self.provider_used,
            },
            "metrics": {
                "quality_score": self.quality_score,
                "quality_breakdown": self.quality_breakdown,
                "novelty_score": self.novelty_score,
                "performance_score": self.performance_score,
                "sim_runs": self.sim_runs,
                "sim_crash_rate": self.sim_crash_rate,
                "sim_engagement": self.sim_engagement,
                "diff_risk_score": self.diff_risk_score,
            },
            "cost": {
                "cost_usd": self.cost_usd,
                "tokens_used": self.tokens_used,
            },
            "status": {
                "build_success": self.build_success,
                "iteration_status": self.iteration_status,
            },
            "tags": self.tags,
            "prompt_tuning": {
                "prompt_hashes": self.prompt_hashes,
                "prompt_variants": self.prompt_variants,
            },
            "extra": self.extra,
        }

    def flat_dict(self) -> dict[str, Any]:
        """Flat dictionary for CSV export."""
        return {
            "iteration": self.iteration,
            "timestamp": self.timestamp,
            "llm_temperature": self.llm_temperature,
            "exploration_mode": self.exploration_mode,
            "provider_used": self.provider_used,
            "quality_score": self.quality_score,
            "novelty_score": self.novelty_score,
            "performance_score": self.performance_score,
            "sim_runs": self.sim_runs,
            "sim_crash_rate": self.sim_crash_rate,
            "sim_engagement": self.sim_engagement,
            "diff_risk_score": self.diff_risk_score,
            "cost_usd": self.cost_usd,
            "tokens_used": self.tokens_used,
            "build_success": self.build_success,
            "iteration_status": self.iteration_status,
            "tags": ",".join(self.tags),
            "prompt_hashes": json.dumps(self.prompt_hashes) if self.prompt_hashes else "",
            "prompt_variants": json.dumps(self.prompt_variants) if self.prompt_variants else "",
        }


@dataclass
class ExperimentComparison:
    """Diff between two experiment snapshots."""
    iter_a: int
    iter_b: int
    metric_deltas: dict[str, float] = field(default_factory=dict)
    param_changes: dict[str, dict[str, Any]] = field(default_factory=dict)
    tag_diff: dict[str, list[str]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "comparing": [self.iter_a, self.iter_b],
            "metric_deltas": self.metric_deltas,
            "param_changes": self.param_changes,
            "tag_diff": self.tag_diff,
        }


class ExperimentTracker:
    """
    Mini-MLflow local for tracking pipeline experiment data.

    Records a complete snapshot of each iteration including parameters,
    metrics, costs, and tags. Supports comparison, filtering, and CSV export.

    Usage:
        tracker = ExperimentTracker()
        tracker.record(ExperimentSnapshot(iteration=1, quality_score=72.5))
        tracker.record(ExperimentSnapshot(iteration=2, quality_score=78.1))
        diff = tracker.compare(1, 2)
        csv_data = tracker.export_csv()
    """

    MAX_EXPERIMENTS = 500

    def __init__(self) -> None:
        self._experiments: dict[int, ExperimentSnapshot] = {}
        self._persist_path = ITERATIONS_DIR / "experiments.json"
        self._load()

    # ── Record ─────────────────────────────────────────

    def record(self, snapshot: ExperimentSnapshot) -> None:
        """Save an experiment snapshot for an iteration."""
        self._experiments[snapshot.iteration] = snapshot

        tag_str = f" [{', '.join(snapshot.tags)}]" if snapshot.tags else ""
        logger.info(
            "📊 Experiment #%d recorded: score=%.1f cost=$%.4f%s",
            snapshot.iteration,
            snapshot.quality_score,
            snapshot.cost_usd,
            tag_str,
        )

        # M10: Enforce cap and persist
        if len(self._experiments) > self.MAX_EXPERIMENTS:
            oldest = min(self._experiments)
            del self._experiments[oldest]
        self._save()

    def record_from_dict(
        self,
        iteration: int,
        *,
        quality_score: float = 0.0,
        quality_breakdown: dict[str, float] | None = None,
        novelty_score: float = 0.0,
        performance_score: float = 0.0,
        sim_runs: int = 0,
        sim_crash_rate: float = 0.0,
        sim_engagement: float = 0.0,
        diff_risk_score: float = 0.0,
        cost_usd: float = 0.0,
        tokens_used: int = 0,
        build_success: bool = False,
        iteration_status: str = "",
        exploration_mode: bool = False,
        llm_temperature: float = 0.7,
        provider_used: str = "",
        tags: list[str] | None = None,
        extra: dict[str, Any] | None = None,
    ) -> ExperimentSnapshot:
        """Convenience method to record from keyword args."""
        snapshot = ExperimentSnapshot(
            iteration=iteration,
            quality_score=quality_score,
            quality_breakdown=quality_breakdown or {},
            novelty_score=novelty_score,
            performance_score=performance_score,
            sim_runs=sim_runs,
            sim_crash_rate=sim_crash_rate,
            sim_engagement=sim_engagement,
            diff_risk_score=diff_risk_score,
            cost_usd=cost_usd,
            tokens_used=tokens_used,
            build_success=build_success,
            iteration_status=iteration_status,
            exploration_mode=exploration_mode,
            llm_temperature=llm_temperature,
            provider_used=provider_used,
            tags=tags or [],
            extra=extra or {},
        )
        self.record(snapshot)
        return snapshot

    # ── Query ──────────────────────────────────────────

    def get(self, iteration: int) -> ExperimentSnapshot | None:
        """Get a specific experiment by iteration number."""
        return self._experiments.get(iteration)

    def get_history(
        self,
        *,
        tag: str | None = None,
        min_score: float | None = None,
        max_score: float | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """
        Get experiment history with optional filters.

        Args:
            tag: Filter by tag (e.g. "milestone", "rollback")
            min_score: Minimum quality score
            max_score: Maximum quality score
            limit: Maximum number of results
        """
        experiments = sorted(
            self._experiments.values(),
            key=lambda e: e.iteration,
            reverse=True,
        )

        # Apply filters
        if tag:
            experiments = [e for e in experiments if tag in e.tags]
        if min_score is not None:
            experiments = [e for e in experiments if e.quality_score >= min_score]
        if max_score is not None:
            experiments = [e for e in experiments if e.quality_score <= max_score]
        if limit:
            experiments = experiments[:limit]

        return [e.to_dict() for e in experiments]

    def get_best(self) -> ExperimentSnapshot | None:
        """Get the experiment with the highest quality score."""
        if not self._experiments:
            return None
        return max(self._experiments.values(), key=lambda e: e.quality_score)

    # ── Compare ────────────────────────────────────────

    def compare(self, iter_a: int, iter_b: int) -> ExperimentComparison:
        """
        Compare two experiments and return the deltas.

        Args:
            iter_a: First iteration number
            iter_b: Second iteration number

        Returns:
            ExperimentComparison with metric deltas and param changes
        """
        exp_a = self._experiments.get(iter_a)
        exp_b = self._experiments.get(iter_b)

        comparison = ExperimentComparison(iter_a=iter_a, iter_b=iter_b)

        if not exp_a or not exp_b:
            return comparison

        # Metric deltas (B - A)
        metric_fields = [
            "quality_score", "novelty_score", "performance_score",
            "sim_crash_rate", "sim_engagement", "diff_risk_score",
            "cost_usd",
        ]
        for field_name in metric_fields:
            val_a = getattr(exp_a, field_name, 0.0)
            val_b = getattr(exp_b, field_name, 0.0)
            delta = val_b - val_a
            if abs(delta) > 0.001:
                comparison.metric_deltas[field_name] = round(delta, 4)

        # Quality breakdown deltas
        all_keys = set(exp_a.quality_breakdown) | set(exp_b.quality_breakdown)
        for key in all_keys:
            val_a = exp_a.quality_breakdown.get(key, 0.0)
            val_b = exp_b.quality_breakdown.get(key, 0.0)
            delta = val_b - val_a
            if abs(delta) > 0.001:
                comparison.metric_deltas[f"breakdown.{key}"] = round(delta, 4)

        # Parameter changes
        param_fields = [
            ("llm_temperature", "temperature"),
            ("exploration_mode", "exploration"),
            ("provider_used", "provider"),
        ]
        for attr, label in param_fields:
            val_a = getattr(exp_a, attr)
            val_b = getattr(exp_b, attr)
            if val_a != val_b:
                comparison.param_changes[label] = {
                    "from": val_a,
                    "to": val_b,
                }

        # Tag diff
        tags_a = set(exp_a.tags)
        tags_b = set(exp_b.tags)
        added = tags_b - tags_a
        removed = tags_a - tags_b
        if added:
            comparison.tag_diff["added"] = sorted(added)
        if removed:
            comparison.tag_diff["removed"] = sorted(removed)

        return comparison

    # ── Export ──────────────────────────────────────────

    def export_csv(self) -> str:
        """Export all experiments as CSV string."""
        if not self._experiments:
            return ""

        sorted_experiments = sorted(
            self._experiments.values(),
            key=lambda e: e.iteration,
        )

        output = io.StringIO()
        flat = sorted_experiments[0].flat_dict()
        writer = csv.DictWriter(output, fieldnames=flat.keys())
        writer.writeheader()

        for exp in sorted_experiments:
            writer.writerow(exp.flat_dict())

        return output.getvalue()

    # ── Stats ──────────────────────────────────────────

    def get_stats(self) -> dict[str, Any]:
        """Get summary statistics across all experiments."""
        if not self._experiments:
            return {"total_experiments": 0}

        experiments = list(self._experiments.values())
        scores = [e.quality_score for e in experiments]
        costs = [e.cost_usd for e in experiments]

        return {
            "total_experiments": len(experiments),
            "score_range": [min(scores), max(scores)],
            "score_avg": round(sum(scores) / len(scores), 1),
            "total_cost_usd": round(sum(costs), 4),
            "avg_cost_per_iter": round(sum(costs) / len(costs), 4) if costs else 0,
            "milestones": sum(1 for e in experiments if "milestone" in e.tags),
            "rollbacks": sum(1 for e in experiments if "rollback" in e.tags),
            "exploration_iters": sum(1 for e in experiments if e.exploration_mode),
        }

    def get_agent_latencies(self) -> dict[str, list[float]]:
        """Extract agent latency data from experiment extras.

        Returns a dict mapping agent name to a list of recorded
        durations (seconds), suitable for analytics aggregation.

        v3 Item #16 — Real-Time Dashboard Analytics.
        """
        result: dict[str, list[float]] = {}
        for snap in self._experiments.values():
            latencies = snap.extra.get("agent_latencies", {})
            for agent, dur in latencies.items():
                result.setdefault(agent, []).append(float(dur))
        return result

    # ── M10: Persistence ───────────────────────────────

    def _save(self) -> None:
        """Persist experiments to JSON file."""
        try:
            data = {
                str(k): v.to_dict() for k, v in self._experiments.items()
            }
            self._persist_path.write_text(
                json.dumps(data, indent=2, default=str),
                encoding="utf-8",
            )
        except Exception as exc:
            logger.warning("Failed to persist experiments: %s", exc)

    def _load(self) -> None:
        """Load experiments from JSON file on startup."""
        if not self._persist_path.exists():
            return
        try:
            raw = json.loads(
                self._persist_path.read_text(encoding="utf-8")
            )
            for key, val in raw.items():
                params = val.get("parameters", {})
                metrics = val.get("metrics", {})
                cost = val.get("cost", {})
                status = val.get("status", {})
                snap = ExperimentSnapshot(
                    iteration=int(key),
                    timestamp=val.get("timestamp", ""),
                    llm_temperature=params.get("llm_temperature", 0.7),
                    quality_weights=params.get("quality_weights", {}),
                    exploration_mode=params.get("exploration_mode", False),
                    provider_used=params.get("provider_used", ""),
                    quality_score=metrics.get("quality_score", 0.0),
                    quality_breakdown=metrics.get("quality_breakdown", {}),
                    novelty_score=metrics.get("novelty_score", 0.0),
                    performance_score=metrics.get("performance_score", 0.0),
                    sim_runs=metrics.get("sim_runs", 0),
                    sim_crash_rate=metrics.get("sim_crash_rate", 0.0),
                    sim_engagement=metrics.get("sim_engagement", 0.0),
                    diff_risk_score=metrics.get("diff_risk_score", 0.0),
                    cost_usd=cost.get("cost_usd", 0.0),
                    tokens_used=cost.get("tokens_used", 0),
                    build_success=status.get("build_success", False),
                    iteration_status=status.get("iteration_status", ""),
                    tags=val.get("tags", []),
                    prompt_hashes=val.get("prompt_tuning", {}).get("prompt_hashes", {}),
                    prompt_variants=val.get("prompt_tuning", {}).get("prompt_variants", {}),
                    extra=val.get("extra", {}),
                )
                self._experiments[int(key)] = snap
            logger.info(
                "📂 Loaded %d experiments from %s",
                len(self._experiments),
                self._persist_path.name,
            )
        except Exception as exc:
            logger.warning("Failed to load experiments: %s", exc)
