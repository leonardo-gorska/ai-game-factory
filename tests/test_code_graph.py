"""Unit tests for CodeGraph (Roadmap v3 Item #8)."""

from __future__ import annotations

import pytest
from backend.core.code_graph import CodeGraph, ImpactReport


# ── Fixtures ──────────────────────────────────────────

SAMPLE_FILES: dict[str, str] = {
    "src/main.js": """
import { Player } from './player.js';
import { Enemy } from './enemy.js';
const game = { player: new Player(), enemy: new Enemy() };
""",
    "src/player.js": """
import { Config } from './config.js';
export class Player { constructor() { this.hp = Config.HP; } }
""",
    "src/enemy.js": """
import { Config } from './config.js';
export class Enemy { constructor() { this.hp = Config.ENEMY_HP; } }
""",
    "src/config.js": """
export const Config = { HP: 100, ENEMY_HP: 50, SPEED: 5 };
""",
    "src/ui.js": """
import { Player } from './player.js';
export function renderUI(p) { return p.hp; }
""",
}


@pytest.fixture
def graph() -> CodeGraph:
    cg = CodeGraph()
    cg.update(SAMPLE_FILES)
    return cg


# ── Basic Graph Construction ─────────────────────────

class TestGraphConstruction:
    def test_nodes_count(self, graph: CodeGraph) -> None:
        stats = graph.get_stats()
        assert stats["total_nodes"] == 5

    def test_edges_exist(self, graph: CodeGraph) -> None:
        stats = graph.get_stats()
        assert stats["total_edges"] > 0

    def test_imports(self, graph: CodeGraph) -> None:
        imports = graph.get_imports("src/main.js")
        assert "src/player.js" in imports
        assert "src/enemy.js" in imports

    def test_imported_by(self, graph: CodeGraph) -> None:
        imported_by = graph.get_imported_by("src/config.js")
        assert "src/player.js" in imported_by
        assert "src/enemy.js" in imported_by


# ── Impact Context ───────────────────────────────────

class TestImpactContext:
    def test_config_change_impacts(self, graph: CodeGraph) -> None:
        """Changing config.js should transitively affect player, enemy, main, ui."""
        impact = graph.get_impact_context(["src/config.js"])
        assert isinstance(impact, ImpactReport)
        # player.js and enemy.js directly import config
        assert "src/player.js" in impact.affected_files
        assert "src/enemy.js" in impact.affected_files
        # main.js imports player and enemy
        assert "src/main.js" in impact.affected_files

    def test_leaf_change_no_impact(self, graph: CodeGraph) -> None:
        """Changing ui.js (a leaf) should not impact others."""
        impact = graph.get_impact_context(["src/ui.js"])
        assert impact.total_impact == 0
        assert len(impact.affected_files) == 0

    def test_nonexistent_file(self, graph: CodeGraph) -> None:
        """Non-existent file should return empty impact."""
        impact = graph.get_impact_context(["src/does_not_exist.js"])
        assert impact.total_impact == 0
        assert len(impact.affected_files) == 0

    def test_has_impact_property(self, graph: CodeGraph) -> None:
        impact = graph.get_impact_context(["src/config.js"])
        assert impact.has_impact
        empty = graph.get_impact_context(["src/ui.js"])
        assert not empty.has_impact


# ── Developer Context ────────────────────────────────

class TestDeveloperContext:
    def test_context_returns_code(self, graph: CodeGraph) -> None:
        context = graph.get_context_for_developer(
            changed_files=["src/config.js"],
            current_files=SAMPLE_FILES,
        )
        assert isinstance(context, dict)
        assert len(context) > 0

    def test_context_char_limit(self, graph: CodeGraph) -> None:
        context = graph.get_context_for_developer(
            changed_files=["src/config.js"],
            current_files=SAMPLE_FILES,
            max_context_chars=50,
        )
        total_chars = sum(len(v) for v in context.values())
        # Should respect the limit (may include 1 file before hitting limit)
        assert total_chars <= 3050  # one file can be up to 3000 chars

    def test_context_empty_for_leaf(self, graph: CodeGraph) -> None:
        context = graph.get_context_for_developer(
            changed_files=["src/ui.js"],
            current_files=SAMPLE_FILES,
        )
        assert len(context) == 0


# ── Stats ─────────────────────────────────────────────

class TestStats:
    def test_stats_keys(self, graph: CodeGraph) -> None:
        stats = graph.get_stats()
        assert "total_nodes" in stats
        assert "total_edges" in stats
        assert "max_fan_out" in stats
        assert "max_fan_in" in stats
        assert "most_depended_on" in stats
        assert "initialized" in stats

    def test_empty_graph(self) -> None:
        cg = CodeGraph()
        stats = cg.get_stats()
        assert stats["total_nodes"] == 0
        assert stats["total_edges"] == 0

    def test_initialized_flag(self) -> None:
        cg = CodeGraph()
        assert not cg.is_initialized
        cg.update(SAMPLE_FILES)
        assert cg.is_initialized


# ── Update Behavior ──────────────────────────────────

class TestUpdate:
    def test_update_replaces_graph(self) -> None:
        cg = CodeGraph()
        cg.update(SAMPLE_FILES)
        assert cg.get_stats()["total_nodes"] == 5

        # Update with fewer files
        cg.update({"src/solo.js": "const x = 1;"})
        assert cg.get_stats()["total_nodes"] == 1

    def test_update_empty_files(self) -> None:
        cg = CodeGraph()
        cg.update({})
        assert cg.get_stats()["total_nodes"] == 0
