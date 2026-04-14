"""
GORVAX GAME FACTORY — CI/CD Pipeline
Automated build → lint → test → simulate → quality gate pipeline
with canary deployment and rollback support.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class StageStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class StageResult:
    """Result of a single CI stage."""
    name: str
    status: StageStatus = StageStatus.PENDING
    duration_ms: float = 0.0
    details: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status.value,
            "duration_ms": round(self.duration_ms, 1),
            "details": self.details,
            "error": self.error,
        }


@dataclass
class PipelineRun:
    """Complete CI pipeline run result."""
    run_id: int
    iteration: int
    started_at: float = field(default_factory=time.time)
    finished_at: float | None = None
    stages: list[StageResult] = field(default_factory=list)
    passed: bool = False
    promoted: bool = False
    canary: bool = False

    @property
    def duration_ms(self) -> float:
        if self.finished_at:
            return (self.finished_at - self.started_at) * 1000
        return (time.time() - self.started_at) * 1000

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "iteration": self.iteration,
            "duration_ms": round(self.duration_ms, 1),
            "passed": self.passed,
            "promoted": self.promoted,
            "canary": self.canary,
            "stages": [s.to_dict() for s in self.stages],
        }


@dataclass
class QualityGateConfig:
    """Configuration for the quality gate stage."""
    min_composite_score: float = 30.0
    max_regression_points: float = 5.0
    require_build_success: bool = True
    require_lint_pass: bool = True
    min_novelty: float = 5.0


class CIPipeline:
    """
    CI/CD Pipeline with quality gates and canary deployment.
    
    Stages:
    1. Build — compile game with Vite
    2. Lint — static analysis (ESLint)
    3. Test — tester agent evaluation
    4. Simulate — Monte Carlo simulation
    5. Quality Gate — multi-objective score check
    6. Canary — compare against current best
    7. Promote/Rollback — deploy or reject
    """

    def __init__(
        self,
        quality_gate: QualityGateConfig | None = None,
    ) -> None:
        self.quality_gate = quality_gate or QualityGateConfig()
        self._runs: list[PipelineRun] = []
        self._runs_by_id: dict[int, PipelineRun] = {}  # B8: O(1) lookup
        self._next_run_id = 1
        self._current_best_score: float = 0.0
        self._total_promotions = 0
        self._total_rejections = 0
        self._total_rollbacks = 0

    async def run(
        self,
        iteration: int,
        build_result: dict[str, Any],
        lint_result: dict[str, Any],
        test_result: dict[str, Any],
        sim_result: dict[str, Any],
        quality_score: dict[str, Any],
        canary: bool = True,
    ) -> PipelineRun:
        """
        Execute the full CI pipeline.
        
        Args:
            iteration: Current pipeline iteration number
            build_result: Output from GameBuilder
            lint_result: Output from GameEvaluator
            test_result: Output from TesterAgent
            sim_result: Output from Simulator
            quality_score: Output from QualityEngine
            canary: Whether to run canary comparison
        """
        run = PipelineRun(
            run_id=self._next_run_id,
            iteration=iteration,
            canary=canary,
        )
        self._next_run_id += 1

        try:
            # Stage 1: Build
            build_stage = await self._stage_build(build_result)
            run.stages.append(build_stage)
            if build_stage.status == StageStatus.FAILED and self.quality_gate.require_build_success:
                run.passed = False
                run.finished_at = time.time()
                self._total_rejections += 1
                self._runs.append(run)
                self._runs_by_id[run.run_id] = run
                logger.warning("CI run #%d FAILED at build stage", run.run_id)
                return run

            # Stage 2: Lint
            lint_stage = await self._stage_lint(lint_result)
            run.stages.append(lint_stage)
            if lint_stage.status == StageStatus.FAILED and self.quality_gate.require_lint_pass:
                run.passed = False
                run.finished_at = time.time()
                self._total_rejections += 1
                self._runs.append(run)
                self._runs_by_id[run.run_id] = run
                logger.warning("CI run #%d FAILED at lint stage", run.run_id)
                return run

            # Stage 3: Test
            test_stage = await self._stage_test(test_result)
            run.stages.append(test_stage)

            # Stage 4: Simulate
            sim_stage = await self._stage_simulate(sim_result)
            run.stages.append(sim_stage)

            # Stage 5: Quality Gate
            gate_stage = await self._stage_quality_gate(quality_score)
            run.stages.append(gate_stage)
            if gate_stage.status == StageStatus.FAILED:
                run.passed = False
                run.finished_at = time.time()
                self._total_rejections += 1
                self._runs.append(run)
                self._runs_by_id[run.run_id] = run
                logger.warning("CI run #%d FAILED at quality gate", run.run_id)
                return run

            # Stage 6: Canary (if enabled)
            if canary:
                canary_stage = await self._stage_canary(quality_score)
                run.stages.append(canary_stage)
                if canary_stage.status == StageStatus.FAILED:
                    run.passed = False
                    run.finished_at = time.time()
                    self._total_rollbacks += 1
                    self._runs.append(run)
                    self._runs_by_id[run.run_id] = run
                    logger.info("CI run #%d: canary rejected (rollback)", run.run_id)
                    return run

            # All stages passed
            run.passed = True
            run.promoted = True
            run.finished_at = time.time()

            # Update best score
            composite = quality_score.get("composite", 0.0)
            if composite > self._current_best_score:
                self._current_best_score = composite

            self._total_promotions += 1
            self._runs.append(run)
            self._runs_by_id[run.run_id] = run
            logger.info(
                "CI run #%d PASSED ✅ (promoted, score=%.1f)",
                run.run_id, composite,
            )
            return run

        except Exception as e:
            error_stage = StageResult(
                name="error",
                status=StageStatus.FAILED,
                error=str(e),
            )
            run.stages.append(error_stage)
            run.passed = False
            run.finished_at = time.time()
            self._runs.append(run)
            self._runs_by_id[run.run_id] = run
            logger.error("CI run #%d ERROR: %s", run.run_id, e)
            return run

    async def _stage_build(self, build_result: dict[str, Any]) -> StageResult:
        """Check build result."""
        t0 = time.monotonic()
        success = build_result.get("success", False)
        return StageResult(
            name="build",
            status=StageStatus.PASSED if success else StageStatus.FAILED,
            duration_ms=(time.monotonic() - t0) * 1000,
            details={
                "success": success,
                "errors": build_result.get("errors", []),
                "warnings": build_result.get("warnings", 0),
            },
            error=None if success else "Build failed",
        )

    async def _stage_lint(self, lint_result: dict[str, Any]) -> StageResult:
        """Check lint result."""
        t0 = time.monotonic()
        errors = lint_result.get("error_count", 0)
        warnings = lint_result.get("warning_count", 0)
        passed = errors == 0
        return StageResult(
            name="lint",
            status=StageStatus.PASSED if passed else StageStatus.FAILED,
            duration_ms=(time.monotonic() - t0) * 1000,
            details={
                "errors": errors,
                "warnings": warnings,
                "rules_violated": lint_result.get("rules_violated", []),
            },
            error=None if passed else f"{errors} lint errors",
        )

    async def _stage_test(self, test_result: dict[str, Any]) -> StageResult:
        """Evaluate test results (always passes, provides info)."""
        t0 = time.monotonic()
        issues = test_result.get("issues_found", 0)
        severity = test_result.get("max_severity", "low")
        return StageResult(
            name="test",
            status=StageStatus.PASSED if severity != "critical" else StageStatus.FAILED,
            duration_ms=(time.monotonic() - t0) * 1000,
            details={
                "issues_found": issues,
                "max_severity": severity,
                "categories": test_result.get("categories", {}),
            },
        )

    async def _stage_simulate(self, sim_result: dict[str, Any]) -> StageResult:
        """Evaluate simulation results."""
        t0 = time.monotonic()
        return StageResult(
            name="simulate",
            status=StageStatus.PASSED,
            duration_ms=(time.monotonic() - t0) * 1000,
            details={
                "runs": sim_result.get("total_runs", 0),
                "avg_score": sim_result.get("avg_score", 0),
                "confidence": sim_result.get("confidence_interval", {}),
                "exploits_found": sim_result.get("exploits_found", 0),
            },
        )

    async def _stage_quality_gate(self, quality_score: dict[str, Any]) -> StageResult:
        """Multi-objective quality gate check."""
        t0 = time.monotonic()
        composite = quality_score.get("composite", 0.0)
        regression = quality_score.get("regression_penalty", 0.0)
        novelty = quality_score.get("novelty", 0.0)

        gate_checks = {
            "min_score": composite >= self.quality_gate.min_composite_score,
            "max_regression": regression <= self.quality_gate.max_regression_points,
            "min_novelty": novelty >= self.quality_gate.min_novelty,
        }

        all_passed = all(gate_checks.values())
        failures = [k for k, v in gate_checks.items() if not v]

        return StageResult(
            name="quality_gate",
            status=StageStatus.PASSED if all_passed else StageStatus.FAILED,
            duration_ms=(time.monotonic() - t0) * 1000,
            details={
                "composite_score": composite,
                "regression_penalty": regression,
                "novelty": novelty,
                "checks": gate_checks,
                "thresholds": {
                    "min_score": self.quality_gate.min_composite_score,
                    "max_regression": self.quality_gate.max_regression_points,
                    "min_novelty": self.quality_gate.min_novelty,
                },
            },
            error=f"Failed gates: {', '.join(failures)}" if failures else None,
        )

    async def _stage_canary(self, quality_score: dict[str, Any]) -> StageResult:
        """
        Canary comparison: new version must be >= current best - tolerance.
        Prevents deploying worse versions.
        """
        t0 = time.monotonic()
        composite = quality_score.get("composite", 0.0)
        tolerance = 3.0  # Allow up to 3 points below best

        is_better = composite >= (self._current_best_score - tolerance)
        delta = composite - self._current_best_score

        return StageResult(
            name="canary",
            status=StageStatus.PASSED if is_better else StageStatus.FAILED,
            duration_ms=(time.monotonic() - t0) * 1000,
            details={
                "candidate_score": composite,
                "current_best": self._current_best_score,
                "delta": round(delta, 2),
                "tolerance": tolerance,
                "promoted": is_better,
            },
            error=None if is_better else f"Score {composite:.1f} < best {self._current_best_score:.1f} - {tolerance}",
        )

    # ── Stats & History ──────────────────────────────────

    def get_stats(self) -> dict[str, Any]:
        """Return CI pipeline statistics."""
        return {
            "total_runs": len(self._runs),
            "promotions": self._total_promotions,
            "rejections": self._total_rejections,
            "rollbacks": self._total_rollbacks,
            "current_best_score": self._current_best_score,
            "pass_rate": round(
                self._total_promotions / len(self._runs) * 100, 1
            ) if self._runs else 0.0,
        }

    def get_history(self, limit: int = 20) -> list[dict[str, Any]]:
        """Return recent CI run history."""
        return [r.to_dict() for r in self._runs[-limit:]]

    def get_run(self, run_id: int) -> PipelineRun | None:
        """Get a specific CI run by ID."""
        return self._runs_by_id.get(run_id)
