"""
GORVAX GAME FACTORY — Parallel Scheduler (DAG-based Wave Execution)

Maps step dependencies as a DAG and executes independent steps in
parallel via ``asyncio.gather()``.  Steps are grouped into "waves"
using topological sort (Kahn's algorithm).

Roadmap v3 Item #1.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)

# Type alias: a factory that returns a coroutine producing a result dict.
CoroFactory = Callable[[], Awaitable[dict[str, Any]]]


@dataclass
class StepNode:
    """A single step in the pipeline DAG."""

    name: str
    dependencies: set[str] = field(default_factory=set)
    coro_factory: CoroFactory | None = None


class ParallelScheduler:
    """DAG scheduler that groups steps into parallel waves.

    Usage::

        scheduler = ParallelScheduler()
        scheduler.add_step("researcher", set(), lambda: run_researcher())
        scheduler.add_step("designer", {"researcher"}, lambda: run_designer())
        scheduler.add_step("developer", {"designer"}, lambda: run_developer())
        scheduler.add_step("performance", {"build"}, lambda: run_perf())
        scheduler.add_step("simulator", {"build"}, lambda: run_sim())
        scheduler.add_step("build", {"developer"}, lambda: run_build())
        waves = scheduler.compute_waves()
        results = await scheduler.execute()
    """

    def __init__(self) -> None:
        self._steps: dict[str, StepNode] = {}

    # ── Registration ──────────────────────────────────────

    def add_step(
        self,
        name: str,
        dependencies: set[str] | None = None,
        coro_factory: CoroFactory | None = None,
    ) -> None:
        """Register a step with its dependencies and coroutine factory."""
        self._steps[name] = StepNode(
            name=name,
            dependencies=dependencies or set(),
            coro_factory=coro_factory,
        )

    def remove_step(self, name: str) -> None:
        """Remove a step from the DAG (if it exists)."""
        self._steps.pop(name, None)
        # Also remove from other steps' dependencies
        for step in self._steps.values():
            step.dependencies.discard(name)

    @property
    def step_names(self) -> list[str]:
        return list(self._steps.keys())

    # ── Wave Computation (Topological Sort) ───────────────

    def compute_waves(self) -> list[list[StepNode]]:
        """Compute execution waves via Kahn's algorithm.

        Returns a list of waves.  Each wave is a list of ``StepNode``
        objects that can be executed in parallel (all their dependencies
        have been satisfied in previous waves).

        Raises:
            ValueError: If the DAG contains a cycle or a step references
                a dependency that was not registered.
        """
        if not self._steps:
            return []

        # Validate all dependencies exist
        for step in self._steps.values():
            missing = step.dependencies - set(self._steps.keys())
            if missing:
                raise ValueError(
                    f"Step '{step.name}' depends on unregistered step(s): "
                    f"{', '.join(sorted(missing))}"
                )

        # Build in-degree map
        in_degree: dict[str, int] = {name: 0 for name in self._steps}
        for step in self._steps.values():
            for dep in step.dependencies:
                # dep → step (step depends on dep)
                pass
            in_degree[step.name] = len(step.dependencies)

        # Kahn's algorithm with wave grouping
        waves: list[list[StepNode]] = []
        queue: deque[str] = deque(
            name for name, deg in in_degree.items() if deg == 0
        )

        processed = 0
        while queue:
            # All items currently in the queue form one wave
            wave: list[StepNode] = []
            next_queue: deque[str] = deque()

            while queue:
                name = queue.popleft()
                wave.append(self._steps[name])
                processed += 1

                # Decrease in-degree for successors
                for successor in self._steps.values():
                    if name in successor.dependencies:
                        in_degree[successor.name] -= 1
                        if in_degree[successor.name] == 0:
                            next_queue.append(successor.name)

            waves.append(wave)
            queue = next_queue

        if processed != len(self._steps):
            raise ValueError(
                "Cycle detected in step DAG — cannot compute execution order"
            )

        return waves

    # ── Execution ─────────────────────────────────────────

    async def execute(
        self,
        on_wave_start: Callable[[int, list[str]], Awaitable[None]] | None = None,
        on_step_complete: Callable[[str, dict[str, Any]], Awaitable[None]] | None = None,
    ) -> dict[str, Any]:
        """Execute all steps respecting the DAG order.

        Steps within the same wave run in parallel via ``asyncio.gather``.

        Args:
            on_wave_start: Optional async callback(wave_index, step_names).
            on_step_complete: Optional async callback(step_name, result).

        Returns:
            Dict mapping step_name → result dict.
        """
        waves = self.compute_waves()
        all_results: dict[str, Any] = {}
        total_start = time.monotonic()

        for wave_idx, wave in enumerate(waves):
            step_names = [s.name for s in wave]

            if on_wave_start:
                await on_wave_start(wave_idx, step_names)

            logger.info(
                "🌊 Wave %d/%d: %s",
                wave_idx + 1, len(waves), ", ".join(step_names),
            )

            # Build coroutines for this wave
            coros = []
            names = []
            for step in wave:
                if step.coro_factory is None:
                    logger.warning(
                        "Step '%s' has no coro_factory, skipping", step.name
                    )
                    all_results[step.name] = {}
                    continue
                coros.append(step.coro_factory())
                names.append(step.name)

            if coros:
                wave_start = time.monotonic()
                results = await asyncio.gather(*coros, return_exceptions=True)
                wave_elapsed = (time.monotonic() - wave_start) * 1000

                for name, result in zip(names, results):
                    if isinstance(result, Exception):
                        logger.error(
                            "Step '%s' failed with exception: %s", name, result
                        )
                        all_results[name] = {"_error": str(result)}
                    else:
                        all_results[name] = result

                    if on_step_complete:
                        await on_step_complete(name, all_results[name])

                logger.info(
                    "🌊 Wave %d completed in %.0fms (%d steps)",
                    wave_idx + 1, wave_elapsed, len(names),
                )

        total_elapsed = (time.monotonic() - total_start) * 1000
        logger.info(
            "🏁 All %d waves completed in %.0fms",
            len(waves), total_elapsed,
        )

        return all_results

    # ── Utilities ─────────────────────────────────────────

    def get_dag_info(self) -> dict[str, Any]:
        """Return a summary of the DAG for debugging / dashboard."""
        try:
            waves = self.compute_waves()
            return {
                "total_steps": len(self._steps),
                "total_waves": len(waves),
                "waves": [
                    [s.name for s in wave] for wave in waves
                ],
            }
        except ValueError as exc:
            return {
                "total_steps": len(self._steps),
                "error": str(exc),
            }
