"""
GORVAX GAME FACTORY — Progressive Complexity Manager

Builds the game in phases: core loop first, complex systems later.
This prevents the Designer from generating massive GDDs that cause
unstable builds by constraining which systems are allowed per phase.

Roadmap v2 Item #4.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ── Phase definitions ─────────────────────────────────────

@dataclass(frozen=True)
class Phase:
    """A single complexity phase with entry requirements and constraints."""

    name: str
    min_iteration: int
    min_score: int
    allowed_systems: list[str] = field(default_factory=list)
    max_new_files: int = 5

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "min_iteration": self.min_iteration,
            "min_score": self.min_score,
            "allowed_systems": list(self.allowed_systems),
            "max_new_files": self.max_new_files,
        }


PHASES: list[Phase] = [
    Phase(
        name="core_loop",
        min_iteration=1,
        min_score=0,
        allowed_systems=["game_loop", "player", "input", "rendering"],
        max_new_files=5,
    ),
    Phase(
        name="basic_systems",
        min_iteration=3,
        min_score=40,
        allowed_systems=["combat", "inventory", "ui_hud"],
        max_new_files=4,
    ),
    Phase(
        name="progression",
        min_iteration=6,
        min_score=55,
        allowed_systems=["xp", "levels", "quests", "loot"],
        max_new_files=4,
    ),
    Phase(
        name="economy",
        min_iteration=9,
        min_score=65,
        allowed_systems=["shop", "currency", "rewards", "crafting"],
        max_new_files=3,
    ),
    Phase(
        name="polish",
        min_iteration=12,
        min_score=70,
        allowed_systems=["audio", "particles", "achievements", "settings"],
        max_new_files=3,
    ),
]


# ── Manager ───────────────────────────────────────────────

class ComplexityManager:
    """Controls progressive complexity by gating systems behind phases.

    The Designer agent receives constraints that limit which game systems
    can be added based on the current iteration number and best score
    achieved so far.  This ensures a solid core loop before layering
    advanced systems on top.
    """

    def __init__(self, phases: list[Phase] | None = None) -> None:
        self._phases = phases or PHASES
        self._previous_phase: Phase | None = None

    def get_current_phase(
        self, iteration: int, best_score: int,
    ) -> Phase:
        """Return the highest phase unlocked by *iteration* and *best_score*.

        Walks the phase list in reverse so the most advanced qualifying
        phase is returned first.
        """
        for phase in reversed(self._phases):
            if iteration >= phase.min_iteration and best_score >= phase.min_score:
                return phase
        return self._phases[0]

    def get_allowed_systems(
        self, iteration: int, best_score: int,
    ) -> list[str]:
        """Return all systems allowed up to and including the current phase.

        Unlike ``get_current_phase().allowed_systems`` which only lists the
        *new* systems for that phase, this method accumulates systems from
        all unlocked phases so prior-phase systems remain available.
        """
        current = self.get_current_phase(iteration, best_score)
        allowed: list[str] = []
        for phase in self._phases:
            allowed.extend(phase.allowed_systems)
            if phase.name == current.name:
                break
        return allowed

    def get_designer_constraints(self, phase: Phase) -> dict[str, Any]:
        """Generate constraint dict to inject into the Designer agent input.

        Returns:
            Dict with phase name, allowed systems, max new files, and a
            natural-language instruction string.
        """
        all_allowed = self.get_allowed_systems(
            phase.min_iteration, phase.min_score,
        )

        constraints = {
            "phase": phase.name,
            "allowed_systems": all_allowed,
            "max_new_files": phase.max_new_files,
            "instruction": (
                f"FASE {phase.name.upper()}: foque APENAS nos sistemas "
                f"{all_allowed}. NÃO adicione sistemas de fases futuras. "
                f"Máximo de {phase.max_new_files} arquivos novos nesta iteração."
            ),
        }
        return constraints

    def check_phase_transition(
        self, iteration: int, best_score: int,
    ) -> tuple[bool, Phase]:
        """Check whether the phase changed since the last call.

        Returns:
            Tuple of (transitioned: bool, current_phase: Phase).
        """
        current = self.get_current_phase(iteration, best_score)
        transitioned = (
            self._previous_phase is not None
            and current.name != self._previous_phase.name
        )
        if transitioned:
            logger.info(
                "🎯 Phase transition: %s → %s (iter=%d, score=%d)",
                self._previous_phase.name, current.name,  # type: ignore[union-attr]
                iteration, best_score,
            )
        self._previous_phase = current
        return transitioned, current
