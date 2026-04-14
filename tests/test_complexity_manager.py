"""Tests for backend.core.complexity_manager"""

import pytest
from backend.core.complexity_manager import (
    ComplexityManager,
    Phase,
    PHASES,
)


# ── Phase Progression ─────────────────────────────────────

class TestPhaseProgression:
    """Verify that the correct phase is returned for various iteration/score combinations."""

    def setup_method(self):
        self.mgr = ComplexityManager()

    def test_first_iteration_returns_core_loop(self):
        phase = self.mgr.get_current_phase(iteration=1, best_score=0)
        assert phase.name == "core_loop"

    def test_low_score_stays_core_loop(self):
        """Even at iteration 5, if score is below 40, stay in core_loop."""
        phase = self.mgr.get_current_phase(iteration=5, best_score=30)
        assert phase.name == "core_loop"

    def test_basic_systems_unlocked(self):
        phase = self.mgr.get_current_phase(iteration=3, best_score=40)
        assert phase.name == "basic_systems"

    def test_basic_systems_high_score_no_skip(self):
        """Iteration 3 with score 80 should still be basic_systems (iteration too low for progression)."""
        phase = self.mgr.get_current_phase(iteration=3, best_score=80)
        assert phase.name == "basic_systems"

    def test_progression_unlocked(self):
        phase = self.mgr.get_current_phase(iteration=6, best_score=55)
        assert phase.name == "progression"

    def test_economy_unlocked(self):
        phase = self.mgr.get_current_phase(iteration=9, best_score=65)
        assert phase.name == "economy"

    def test_polish_unlocked(self):
        phase = self.mgr.get_current_phase(iteration=12, best_score=70)
        assert phase.name == "polish"

    def test_polish_high_iteration(self):
        """Very late iteration with high score should be polish."""
        phase = self.mgr.get_current_phase(iteration=50, best_score=90)
        assert phase.name == "polish"

    def test_score_below_threshold_blocks_advancement(self):
        """Iteration 12 but score only 50 stays at basic_systems."""
        phase = self.mgr.get_current_phase(iteration=12, best_score=50)
        assert phase.name == "basic_systems"

    def test_phases_are_ordered(self):
        """Verify PHASES list has increasing requirements."""
        for i in range(1, len(PHASES)):
            assert PHASES[i].min_iteration >= PHASES[i - 1].min_iteration
            assert PHASES[i].min_score >= PHASES[i - 1].min_score


# ── Designer Constraints ──────────────────────────────────

class TestDesignerConstraints:
    """Verify that designer constraints are properly structured."""

    def setup_method(self):
        self.mgr = ComplexityManager()

    def test_constraints_has_required_keys(self):
        phase = PHASES[0]
        constraints = self.mgr.get_designer_constraints(phase)
        assert "phase" in constraints
        assert "allowed_systems" in constraints
        assert "max_new_files" in constraints
        assert "instruction" in constraints

    def test_core_loop_constraints(self):
        phase = self.mgr.get_current_phase(iteration=1, best_score=0)
        constraints = self.mgr.get_designer_constraints(phase)
        assert constraints["phase"] == "core_loop"
        assert "game_loop" in constraints["allowed_systems"]
        assert "player" in constraints["allowed_systems"]
        assert constraints["max_new_files"] == 5

    def test_basic_systems_accumulates_core_systems(self):
        """basic_systems constraints should include core_loop systems too."""
        phase = self.mgr.get_current_phase(iteration=3, best_score=40)
        constraints = self.mgr.get_designer_constraints(phase)
        assert constraints["phase"] == "basic_systems"
        # core_loop systems still allowed
        assert "game_loop" in constraints["allowed_systems"]
        assert "player" in constraints["allowed_systems"]
        # basic_systems new additions
        assert "combat" in constraints["allowed_systems"]
        assert "inventory" in constraints["allowed_systems"]

    def test_polish_has_all_systems(self):
        """Polish phase should accumulate all systems from all phases."""
        phase = self.mgr.get_current_phase(iteration=12, best_score=70)
        constraints = self.mgr.get_designer_constraints(phase)
        assert constraints["phase"] == "polish"
        # Every phase's systems should be present
        total_systems = []
        for p in PHASES:
            total_systems.extend(p.allowed_systems)
        for system in total_systems:
            assert system in constraints["allowed_systems"]

    def test_instruction_contains_phase_name(self):
        for phase in PHASES:
            constraints = self.mgr.get_designer_constraints(phase)
            assert phase.name.upper() in constraints["instruction"]

    def test_max_new_files_in_instruction(self):
        phase = PHASES[3]  # economy
        constraints = self.mgr.get_designer_constraints(phase)
        assert str(phase.max_new_files) in constraints["instruction"]


# ── Allowed Systems Accumulation ──────────────────────────

class TestAllowedSystems:
    def setup_method(self):
        self.mgr = ComplexityManager()

    def test_core_loop_only(self):
        systems = self.mgr.get_allowed_systems(iteration=1, best_score=0)
        assert systems == ["game_loop", "player", "input", "rendering"]

    def test_progression_includes_previous(self):
        systems = self.mgr.get_allowed_systems(iteration=6, best_score=55)
        # Should include core_loop + basic_systems + progression
        assert "game_loop" in systems
        assert "combat" in systems
        assert "xp" in systems
        # Should NOT include economy/polish
        assert "shop" not in systems
        assert "audio" not in systems


# ── Phase Transitions ─────────────────────────────────────

class TestPhaseTransitions:
    def setup_method(self):
        self.mgr = ComplexityManager()

    def test_first_call_no_transition(self):
        transitioned, phase = self.mgr.check_phase_transition(1, 0)
        assert transitioned is False
        assert phase.name == "core_loop"

    def test_same_phase_no_transition(self):
        self.mgr.check_phase_transition(1, 0)
        transitioned, phase = self.mgr.check_phase_transition(2, 20)
        assert transitioned is False
        assert phase.name == "core_loop"

    def test_phase_advance_detected(self):
        self.mgr.check_phase_transition(1, 0)
        transitioned, phase = self.mgr.check_phase_transition(3, 40)
        assert transitioned is True
        assert phase.name == "basic_systems"


# ── Edge Cases ────────────────────────────────────────────

class TestEdgeCases:
    def setup_method(self):
        self.mgr = ComplexityManager()

    def test_iteration_zero(self):
        """Iteration 0 should still return core_loop (fallback)."""
        phase = self.mgr.get_current_phase(iteration=0, best_score=0)
        assert phase.name == "core_loop"

    def test_negative_score(self):
        phase = self.mgr.get_current_phase(iteration=5, best_score=-10)
        assert phase.name == "core_loop"

    def test_phase_to_dict(self):
        d = PHASES[0].to_dict()
        assert d["name"] == "core_loop"
        assert isinstance(d["allowed_systems"], list)
        assert isinstance(d["max_new_files"], int)

    def test_custom_phases(self):
        """ComplexityManager accepts custom phase list."""
        custom = [
            Phase("alpha", 1, 0, ["a"], 2),
            Phase("beta", 5, 50, ["b"], 3),
        ]
        mgr = ComplexityManager(phases=custom)
        assert mgr.get_current_phase(1, 0).name == "alpha"
        assert mgr.get_current_phase(5, 50).name == "beta"

    def test_exact_boundary_values(self):
        """Exact min_iteration and min_score should unlock the phase."""
        for phase in PHASES:
            result = self.mgr.get_current_phase(
                phase.min_iteration, phase.min_score,
            )
            assert result.name == phase.name
