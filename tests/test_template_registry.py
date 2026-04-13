"""
Tests for backend.templates.registry — Template Library

Covers:
- Template auto-discovery from filesystem
- GDD keyword analysis
- Existing system detection
- Suggestion logic (relevance + deduplication)
- Edge cases (empty GDD, no templates, etc.)
"""
import pytest
from pathlib import Path

from backend.templates.registry import TemplateRegistry, Template


# ── Fixtures ──────────────────────────────────────────────

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "backend" / "templates"


class TestTemplateDiscovery:
    """Template auto-discovery from the filesystem."""

    def setup_method(self):
        self.registry = TemplateRegistry(TEMPLATES_DIR)

    def test_discovers_all_16_templates(self):
        assert self.registry.template_count == 16

    def test_categories_are_correct(self):
        categories = {t.category for t in self.registry.templates}
        assert categories == {"game_systems", "ui", "core"}

    def test_game_systems_count(self):
        gs = self.registry.get_by_category("game_systems")
        assert len(gs) == 8

    def test_ui_count(self):
        ui = self.registry.get_by_category("ui")
        assert len(ui) == 4

    def test_core_count(self):
        core = self.registry.get_by_category("core")
        assert len(core) == 4

    def test_each_template_has_code(self):
        for t in self.registry.templates:
            assert len(t.code) > 50, f"Template {t.system} has too little code"

    def test_each_template_has_description(self):
        for t in self.registry.templates:
            assert len(t.description) > 10, f"Template {t.system} lacks description"

    def test_get_template_by_system(self):
        t = self.registry.get_template("inventory")
        assert t is not None
        assert t.system == "inventory"
        assert t.category == "game_systems"

    def test_get_template_nonexistent(self):
        assert self.registry.get_template("nonexistent") is None

    def test_available_systems(self):
        systems = self.registry.get_available_systems()
        assert "inventory" in systems
        assert "game_loop" in systems
        assert "hud" in systems

    def test_template_to_dict(self):
        t = self.registry.get_template("shop")
        d = t.to_dict()
        assert d["system"] == "shop"
        assert d["category"] == "game_systems"
        assert "code" in d


class TestTemplateSuggestion:
    """Suggest relevant templates based on GDD and existing code."""

    def setup_method(self):
        self.registry = TemplateRegistry(TEMPLATES_DIR)

    def test_suggests_inventory_from_gdd(self):
        gdd = {"features": "The player has an inventory to collect items"}
        suggestions = self.registry.suggest(gdd, {})
        systems = [s.system for s in suggestions]
        assert "inventory" in systems

    def test_suggests_combat_from_gdd(self):
        gdd = {"combat": "Turn-based combat with initiative system"}
        suggestions = self.registry.suggest(gdd, {})
        systems = [s.system for s in suggestions]
        assert "combat_turn" in systems

    def test_limits_suggestions_to_max(self):
        gdd = {
            "features": (
                "inventory items combat turn-based shop buy sell "
                "quest mission loot drops save load"
            )
        }
        suggestions = self.registry.suggest(gdd, {}, max_suggestions=2)
        assert len(suggestions) <= 2

    def test_no_suggestions_for_empty_gdd(self):
        suggestions = self.registry.suggest({}, {})
        assert len(suggestions) == 0

    def test_skips_already_implemented_systems(self):
        gdd = {"features": "player inventory with items"}
        existing_files = {
            "inventory.js": (
                "class Inventory {\n"
                "  addItem(item) { }\n"
                "  removeItem(id) { }\n"
                "}"
            ),
        }
        suggestions = self.registry.suggest(gdd, existing_files)
        systems = [s.system for s in suggestions]
        assert "inventory" not in systems

    def test_suggests_multiple_systems(self):
        gdd = {"features": "shop with buy and sell, plus quest system with missions"}
        suggestions = self.registry.suggest(gdd, {}, max_suggestions=5)
        systems = [s.system for s in suggestions]
        assert "shop" in systems
        assert "quest_system" in systems


class TestGDDAnalysis:
    """Tests for _analyze_gdd keyword matching."""

    def setup_method(self):
        self.registry = TemplateRegistry(TEMPLATES_DIR)

    def test_nested_gdd_structure(self):
        gdd = {
            "game": {
                "systems": {
                    "economy": "players can buy and sell items in a shop"
                }
            }
        }
        needed = self.registry._analyze_gdd(gdd)
        assert "shop" in needed

    def test_list_gdd_structure(self):
        gdd = {
            "features": [
                "inventory management",
                "quest log with objectives",
            ]
        }
        needed = self.registry._analyze_gdd(gdd)
        assert "inventory" in needed
        assert "quest_system" in needed

    def test_case_insensitive_matching(self):
        gdd = {"description": "TURN-BASED COMBAT with INITIATIVE"}
        needed = self.registry._analyze_gdd(gdd)
        assert "combat_turn" in needed

    def test_no_false_positives(self):
        gdd = {"title": "A simple puzzle game about matching colors"}
        needed = self.registry._analyze_gdd(gdd)
        assert "combat_turn" not in needed
        assert "inventory" not in needed

    def test_core_systems_detected(self):
        gdd = {
            "architecture": (
                "Uses a game loop with fixed timestep, "
                "event bus for pub/sub, and entity component system"
            )
        }
        needed = self.registry._analyze_gdd(gdd)
        assert "game_loop" in needed
        assert "event_bus" in needed
        assert "entity_component" in needed


class TestExistingDetection:
    """Tests for _detect_existing pattern matching."""

    def setup_method(self):
        self.registry = TemplateRegistry(TEMPLATES_DIR)

    def test_detects_inventory_class(self):
        files = {
            "game.js": (
                "class Inventory {\n"
                "  addItem(item) { this.items.push(item); }\n"
                "  removeItem(id) { this.items = this.items.filter(i => i.id !== id); }\n"
                "}"
            ),
        }
        detected = self.registry._detect_existing(files)
        assert "inventory" in detected

    def test_requires_multiple_pattern_matches(self):
        files = {
            "game.js": "// Just mentions Inventory once\nclass Inventory {}"
        }
        detected = self.registry._detect_existing(files)
        # Only 1 match, need 2 for confidence
        assert "inventory" not in detected

    def test_detects_state_machine(self):
        files = {
            "fsm.js": (
                "class StateMachine {\n"
                "  setState(name) { this.current = name; }\n"
                "  transition() {}\n"
                "}"
            ),
        }
        detected = self.registry._detect_existing(files)
        assert "state_machine" in detected

    def test_empty_files_detects_nothing(self):
        detected = self.registry._detect_existing({})
        assert len(detected) == 0


class TestEdgeCases:
    """Edge cases and robustness tests."""

    def test_nonexistent_templates_dir(self, tmp_path):
        registry = TemplateRegistry(tmp_path / "does_not_exist")
        assert registry.template_count == 0

    def test_empty_templates_dir(self, tmp_path):
        (tmp_path / "game_systems").mkdir()
        registry = TemplateRegistry(tmp_path)
        assert registry.template_count == 0

    def test_suggest_with_no_templates(self, tmp_path):
        registry = TemplateRegistry(tmp_path)
        suggestions = registry.suggest({"features": "inventory"}, {})
        assert len(suggestions) == 0

    def test_template_is_frozen_dataclass(self):
        t = Template(
            system="test",
            category="core",
            description="test template",
            code="// test",
            filename="test.js",
        )
        with pytest.raises(Exception):
            t.system = "modified"

    def test_deeply_nested_gdd_flattening(self):
        registry = TemplateRegistry(TEMPLATES_DIR)
        gdd = {"a": {"b": {"c": {"d": {"e": "inventory items"}}}}}
        needed = registry._analyze_gdd(gdd)
        assert "inventory" in needed

    def test_max_suggestions_zero(self):
        registry = TemplateRegistry(TEMPLATES_DIR)
        suggestions = registry.suggest(
            {"features": "inventory shop quest"},
            {},
            max_suggestions=0,
        )
        assert len(suggestions) == 0
