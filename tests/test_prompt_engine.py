"""
Tests for PromptEngine — template rendering, fallback warnings, and engine/genre coverage.
"""

import logging
import pytest

from backend.llm.prompt_engine import PromptEngine, GENRE_MECHANICS, ENGINE_FEATURES
from backend.config import get_config


@pytest.fixture
def engine() -> PromptEngine:
    """Create a PromptEngine with the current project config."""
    cfg = get_config()
    return PromptEngine(cfg.project)


# ── Template Rendering ──────────────────────────────

class TestRender:
    def test_render_designer_prompt(self, engine: PromptEngine):
        """Designer prompt should render successfully."""
        result = engine.render("designer")
        assert isinstance(result, str)
        assert len(result) > 50

    def test_render_developer_prompt(self, engine: PromptEngine):
        result = engine.render("developer")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_render_tester_prompt(self, engine: PromptEngine):
        result = engine.render("tester")
        assert isinstance(result, str)

    def test_render_nonexistent_returns_empty(self, engine: PromptEngine):
        """Rendering an unknown template should return empty string."""
        result = engine.render("does_not_exist_template_xyz")
        assert result == ""


# ── Genre/Engine Coverage ──────────────────────────

class TestCoverage:
    def test_all_genres_have_mechanics(self):
        """Every genre should have an entry in GENRE_MECHANICS."""
        from backend.config import VALID_GENRES
        for genre in VALID_GENRES:
            assert genre in GENRE_MECHANICS, f"Missing GENRE_MECHANICS entry for '{genre}'"

    def test_all_engines_have_features(self):
        """Every engine should have an entry in ENGINE_FEATURES."""
        from backend.config import VALID_ENGINES
        for eng in VALID_ENGINES:
            assert eng in ENGINE_FEATURES, f"Missing ENGINE_FEATURES entry for '{eng}'"

    def test_genre_mechanics_non_empty(self):
        for genre, mechanics in GENRE_MECHANICS.items():
            assert len(mechanics) > 10, f"GENRE_MECHANICS['{genre}'] is suspiciously short"

    def test_engine_features_non_empty(self):
        for eng, features in ENGINE_FEATURES.items():
            assert len(features) > 10, f"ENGINE_FEATURES['{eng}'] is suspiciously short"


# ── Fallback Warnings ──────────────────────────────

class TestFallbacks:
    def test_unknown_genre_logs_warning(self, caplog):
        """Unknown genre should trigger a CFG-03 warning but not crash."""
        from backend.config import get_config, ProjectConfig
        cfg = get_config()
        # Create a project config with a fake genre
        fake_project = ProjectConfig(
            game_name="Test",
            platform="web",
            engine="phaser3",
            genre="nonexistent_genre",
            monetization="none",
        )
        eng = PromptEngine(fake_project)
        with caplog.at_level(logging.WARNING):
            result = eng.render("designer")
        assert isinstance(result, str)
        # Should have logged a warning about missing genre
        assert any("CFG-03" in rec.message or "nonexistent_genre" in rec.message for rec in caplog.records)

    def test_unknown_engine_logs_warning(self, caplog):
        """Unknown engine should trigger a CFG-03 warning but not crash."""
        from backend.config import ProjectConfig
        fake_project = ProjectConfig(
            game_name="Test",
            platform="web",
            engine="nonexistent_engine",
            genre="idle_rpg",
            monetization="none",
        )
        eng = PromptEngine(fake_project)
        with caplog.at_level(logging.WARNING):
            result = eng.render("designer")
        assert isinstance(result, str)
        assert any("CFG-03" in rec.message or "nonexistent_engine" in rec.message for rec in caplog.records)
