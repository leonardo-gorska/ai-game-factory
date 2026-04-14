"""
GORVAX GAME FACTORY — Watchdog Global (Phase 3)
Supervisiona o pipeline 24/7, detecta anomalias e auto-pausa com notificação.

Anomalias detectadas:
  - Iteration timeout (>10 min)
  - Crash streak (3+ falhas consecutivas)
  - Cost spike (>3× média por iteração)
  - Disk space baixo (<500MB)
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Awaitable

logger = logging.getLogger(__name__)


# ── Types ──────────────────────────────────────────────

class AlertSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AlertType(str, Enum):
    ITERATION_TIMEOUT = "iteration_timeout"
    CRASH_STREAK = "crash_streak"
    COST_SPIKE = "cost_spike"
    DISK_LOW = "disk_low"
    PIPELINE_HEALTHY = "pipeline_healthy"


@dataclass
class WatchdogAlert:
    """An alert emitted by the watchdog."""
    alert_type: AlertType
    severity: AlertSeverity
    message: str
    details: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    auto_action: str = ""  # "pause", "abort_iteration", ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "alert_type": self.alert_type.value,
            "severity": self.severity.value,
            "message": self.message,
            "details": self.details,
            "timestamp": self.timestamp,
            "auto_action": self.auto_action,
        }


@dataclass
class HealthStatus:
    """Health check snapshot."""
    is_healthy: bool = True
    uptime_seconds: float = 0.0
    iterations_completed: int = 0
    consecutive_failures: int = 0
    total_cost_usd: float = 0.0
    disk_free_mb: float = 0.0
    active_alerts: list[dict[str, Any]] = field(default_factory=list)
    last_check: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "is_healthy": self.is_healthy,
            "uptime_seconds": round(self.uptime_seconds, 1),
            "iterations_completed": self.iterations_completed,
            "consecutive_failures": self.consecutive_failures,
            "total_cost_usd": round(self.total_cost_usd, 4),
            "disk_free_mb": round(self.disk_free_mb, 0),
            "active_alerts": self.active_alerts,
            "last_check": self.last_check,
        }


# Type for alert callbacks
AlertCallback = Callable[[WatchdogAlert], Awaitable[None]]


# ── Watchdog ───────────────────────────────────────────

class Watchdog:
    """
    Global system supervisor that monitors the pipeline health.

    Runs as a background asyncio task, checking every `check_interval`
    seconds. Emits alerts and can auto-pause the pipeline.

    Usage:
        watchdog = Watchdog()
        watchdog.on_alert(my_callback)
        await watchdog.start()  # starts background loop
        ...
        watchdog.record_iteration_start(iteration)
        watchdog.record_iteration_end(iteration, success=True, cost=0.05)
        ...
        await watchdog.stop()
    """

    def __init__(
        self,
        *,
        iteration_timeout_seconds: float = 600.0,   # 10 minutes
        max_consecutive_failures: int = 3,
        cost_spike_multiplier: float = 3.0,
        min_disk_mb: float = 500.0,
        check_interval: float = 30.0,
    ) -> None:
        # Configuration
        self._iteration_timeout = iteration_timeout_seconds
        self._max_consecutive_failures = max_consecutive_failures
        self._cost_spike_multiplier = cost_spike_multiplier
        self._min_disk_mb = min_disk_mb
        self._check_interval = check_interval

        # State tracking
        self._start_time: float = 0.0
        self._current_iteration: int = 0
        self._iteration_start_time: float = 0.0
        self._iterations_completed: int = 0
        self._consecutive_failures: int = 0
        self._iteration_costs: list[float] = []
        self._active_alerts: list[WatchdogAlert] = []
        self._alert_history: list[WatchdogAlert] = []

        # Pause request — pipeline checks this
        self._pause_requested: bool = False
        self._abort_iteration_requested: bool = False

        # Background task
        self._task: asyncio.Task[None] | None = None
        self._running: bool = False

        # Callbacks
        self._alert_callbacks: list[AlertCallback] = []

    # ── Public API ─────────────────────────────────────

    def on_alert(self, callback: AlertCallback) -> None:
        """Register a callback for watchdog alerts."""
        self._alert_callbacks.append(callback)

    @property
    def pause_requested(self) -> bool:
        """Check if watchdog is requesting a pipeline pause."""
        return self._pause_requested

    @property
    def abort_iteration_requested(self) -> bool:
        """Check if watchdog wants to abort the current iteration."""
        return self._abort_iteration_requested

    def clear_pause_request(self) -> None:
        """Clear the pause request after pipeline handles it."""
        self._pause_requested = False

    def clear_abort_request(self) -> None:
        """Clear the abort request after pipeline handles it."""
        self._abort_iteration_requested = False

    def reset_consecutive_failures(self) -> None:
        """Reset consecutive failure counter after auto-resume."""
        self._consecutive_failures = 0

    async def start(self) -> None:
        """Start the watchdog background monitoring loop."""
        if self._running:
            return
        self._running = True
        self._start_time = time.time()
        self._task = asyncio.create_task(self._monitor_loop())
        logger.info("🐕 Watchdog started — monitoring every %.0fs", self._check_interval)

    async def stop(self) -> None:
        """Stop the watchdog monitoring loop."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Watchdog stopped")

    # ── Iteration Tracking ─────────────────────────────

    def record_iteration_start(self, iteration: int) -> None:
        """Called when a new pipeline iteration begins."""
        self._current_iteration = iteration
        self._iteration_start_time = time.time()
        self._abort_iteration_requested = False

    def record_iteration_end(
        self,
        iteration: int,
        *,
        success: bool,
        cost_usd: float = 0.0,
    ) -> None:
        """Called when a pipeline iteration completes."""
        self._iterations_completed += 1
        self._iteration_costs.append(cost_usd)

        if success:
            self._consecutive_failures = 0
        else:
            self._consecutive_failures += 1

        # Clear iteration timer
        self._iteration_start_time = 0.0

    # ── Health Check ───────────────────────────────────

    def get_health(self) -> HealthStatus:
        """Get the current health status snapshot."""
        disk_free = self._get_disk_free_mb()
        total_cost = sum(self._iteration_costs)

        return HealthStatus(
            is_healthy=not self._pause_requested and self._consecutive_failures < self._max_consecutive_failures,
            uptime_seconds=time.time() - self._start_time if self._start_time else 0.0,
            iterations_completed=self._iterations_completed,
            consecutive_failures=self._consecutive_failures,
            total_cost_usd=total_cost,
            disk_free_mb=disk_free,
            active_alerts=[a.to_dict() for a in self._active_alerts],
            last_check=datetime.now(timezone.utc).isoformat(),
        )

    # ── Background Monitor ─────────────────────────────

    async def _monitor_loop(self) -> None:
        """Main monitoring loop running in background."""
        while self._running:
            try:
                await self._run_checks()
                await asyncio.sleep(self._check_interval)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Watchdog check failed: %s", exc)
                await asyncio.sleep(self._check_interval)

    async def _run_checks(self) -> None:
        """Run all health checks."""
        self._active_alerts.clear()

        await self._check_iteration_timeout()
        await self._check_crash_streak()
        await self._check_cost_spike()
        await self._check_disk_space()

        if not self._active_alerts:
            logger.debug("Watchdog: all checks passed ✓")

    # ── Individual Checks ──────────────────────────────

    async def _check_iteration_timeout(self) -> None:
        """Check if the current iteration has been running too long."""
        if self._iteration_start_time <= 0:
            return

        # Don't re-trigger if abort already requested
        if self._abort_iteration_requested:
            return

        elapsed = time.time() - self._iteration_start_time
        if elapsed > self._iteration_timeout:
            alert = WatchdogAlert(
                alert_type=AlertType.ITERATION_TIMEOUT,
                severity=AlertSeverity.CRITICAL,
                message=(
                    f"Iteração #{self._current_iteration} rodando há "
                    f"{elapsed:.0f}s (limite: {self._iteration_timeout:.0f}s)"
                ),
                details={
                    "iteration": self._current_iteration,
                    "elapsed_seconds": round(elapsed, 1),
                    "timeout_seconds": self._iteration_timeout,
                },
                auto_action="abort_iteration",
            )
            self._abort_iteration_requested = True
            await self._emit_alert(alert)

    async def _check_crash_streak(self) -> None:
        """Check for consecutive iteration failures."""
        if self._consecutive_failures >= self._max_consecutive_failures:
            alert = WatchdogAlert(
                alert_type=AlertType.CRASH_STREAK,
                severity=AlertSeverity.CRITICAL,
                message=(
                    f"{self._consecutive_failures} falhas consecutivas — "
                    f"pausando pipeline"
                ),
                details={
                    "consecutive_failures": self._consecutive_failures,
                    "threshold": self._max_consecutive_failures,
                },
                auto_action="pause",
            )
            self._pause_requested = True
            await self._emit_alert(alert)

    async def _check_cost_spike(self) -> None:
        """Check if the latest iteration cost is anomalously high."""
        if len(self._iteration_costs) < 3:
            return  # Need at least 3 data points

        # Don't re-trigger if already paused — prevents infinite pause loop
        if self._pause_requested:
            return

        # Average of all but the last iteration
        history = self._iteration_costs[:-1]
        avg_cost = sum(history) / len(history)
        latest_cost = self._iteration_costs[-1]

        if avg_cost > 0 and latest_cost > avg_cost * self._cost_spike_multiplier:
            alert = WatchdogAlert(
                alert_type=AlertType.COST_SPIKE,
                severity=AlertSeverity.WARNING,
                message=(
                    f"Custo da última iteração (${latest_cost:.4f}) é "
                    f"{latest_cost/avg_cost:.1f}× a média (${avg_cost:.4f})"
                ),
                details={
                    "latest_cost": round(latest_cost, 4),
                    "average_cost": round(avg_cost, 4),
                    "multiplier": round(latest_cost / avg_cost, 1),
                    "threshold_multiplier": self._cost_spike_multiplier,
                },
                auto_action="pause",
            )
            self._pause_requested = True
            await self._emit_alert(alert)

    async def _check_disk_space(self) -> None:
        """Check if disk space is running low."""
        free_mb = self._get_disk_free_mb()

        if free_mb < self._min_disk_mb:
            alert = WatchdogAlert(
                alert_type=AlertType.DISK_LOW,
                severity=AlertSeverity.CRITICAL,
                message=(
                    f"Espaço em disco baixo: {free_mb:.0f}MB "
                    f"(mínimo: {self._min_disk_mb:.0f}MB)"
                ),
                details={
                    "free_mb": round(free_mb, 0),
                    "min_mb": self._min_disk_mb,
                },
                auto_action="pause",
            )
            self._pause_requested = True
            await self._emit_alert(alert)

    # ── Helpers ────────────────────────────────────────

    async def _emit_alert(self, alert: WatchdogAlert) -> None:
        """Store alert and notify all callbacks."""
        self._active_alerts.append(alert)
        self._alert_history.append(alert)

        # Keep history bounded
        if len(self._alert_history) > 100:
            self._alert_history = self._alert_history[-50:]

        severity_icon = {
            AlertSeverity.INFO: "ℹ️",
            AlertSeverity.WARNING: "⚠️",
            AlertSeverity.CRITICAL: "🚨",
        }
        icon = severity_icon.get(alert.severity, "❓")
        logger.warning(
            "%s Watchdog alert [%s]: %s (action: %s)",
            icon, alert.alert_type.value, alert.message, alert.auto_action
        )

        for callback in self._alert_callbacks:
            try:
                await callback(alert)
            except Exception as exc:
                logger.debug("Alert callback error: %s", exc)

    @staticmethod
    def _get_disk_free_mb() -> float:
        """Get free disk space in MB for the current drive."""
        try:
            usage = shutil.disk_usage(".")
            return usage.free / (1024 * 1024)
        except Exception:
            return 99999.0  # Assume OK on error
