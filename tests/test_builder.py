"""
Tests for GameBuilder — initialization, source files, and lint check.
"""

from pathlib import Path
from unittest.mock import patch

import pytest

from backend.game.builder import GameBuilder


# ── Initialization ────────────────────────────────

class TestBuilderInit:
    def test_creates_with_default_dir(self):
        """Builder should instantiate with the default GAME_DIR."""
        builder = GameBuilder()
        assert builder._game_dir is not None

    def test_creates_with_custom_dir(self, tmp_path: Path):
        """Builder should accept a custom directory."""
        with patch("backend.game.builder.get_config") as mock_cfg:
            mock_cfg.return_value.server.game_port = 5173
            builder = GameBuilder(game_dir=tmp_path)
        assert builder._game_dir == tmp_path

    def test_uses_dynamic_port(self):
        """Builder should read game_port from config."""
        with patch("backend.game.builder.get_config") as mock_cfg:
            mock_cfg.return_value.server.game_port = 9999
            builder = GameBuilder()
        assert builder._game_port == 9999


# ── Source Files ──────────────────────────────────

class TestSourceFiles:
    def test_get_source_files_returns_dict(self, tmp_path: Path):
        """get_source_files should return a dict of path -> content."""
        src = tmp_path / "src"
        src.mkdir()
        (src / "main.js").write_text("console.log('hi');")
        (src / "game.js").write_text("export default {};")

        with patch("backend.game.builder.get_config") as mock_cfg:
            mock_cfg.return_value.server.game_port = 5173
            builder = GameBuilder(game_dir=tmp_path)

        files = builder.get_source_files()
        assert isinstance(files, dict)
        assert len(files) == 2

    def test_get_source_files_empty_dir(self, tmp_path: Path):
        """get_source_files should handle empty src directory."""
        src = tmp_path / "src"
        src.mkdir()

        with patch("backend.game.builder.get_config") as mock_cfg:
            mock_cfg.return_value.server.game_port = 5173
            builder = GameBuilder(game_dir=tmp_path)

        files = builder.get_source_files()
        assert files == {}

    def test_get_source_files_no_src_dir(self, tmp_path: Path):
        """get_source_files should return empty dict if no src/ dir exists."""
        with patch("backend.game.builder.get_config") as mock_cfg:
            mock_cfg.return_value.server.game_port = 5173
            builder = GameBuilder(game_dir=tmp_path)

        files = builder.get_source_files()
        assert files == {}


# ── Lint Check ────────────────────────────────────

class TestLintCheck:
    @pytest.mark.asyncio
    async def test_basic_lint_check_valid_js(self, tmp_path: Path):
        """_basic_lint_check should pass for valid JS."""
        src = tmp_path / "src"
        src.mkdir()
        (src / "main.js").write_text("const x = 1;\nconsole.log(x);\n")

        with patch("backend.game.builder.get_config") as mock_cfg:
            mock_cfg.return_value.server.game_port = 5173
            builder = GameBuilder(game_dir=tmp_path)

        ok, output = await builder._basic_lint_check()
        assert ok is True
        assert "passed" in output.lower()

    @pytest.mark.asyncio
    async def test_basic_lint_check_mismatched_braces(self, tmp_path: Path):
        """_basic_lint_check should detect mismatched braces."""
        src = tmp_path / "src"
        src.mkdir()
        (src / "main.js").write_text("function test() {{{{\n}\n")

        with patch("backend.game.builder.get_config") as mock_cfg:
            mock_cfg.return_value.server.game_port = 5173
            builder = GameBuilder(game_dir=tmp_path)

        ok, output = await builder._basic_lint_check()
        assert ok is False
        assert "braces" in output.lower()

    @pytest.mark.asyncio
    async def test_basic_lint_check_empty_file(self, tmp_path: Path):
        """_basic_lint_check should flag empty files."""
        src = tmp_path / "src"
        src.mkdir()
        (src / "main.js").write_text("")

        with patch("backend.game.builder.get_config") as mock_cfg:
            mock_cfg.return_value.server.game_port = 5173
            builder = GameBuilder(game_dir=tmp_path)

        ok, output = await builder._basic_lint_check()
        assert ok is False
        assert "empty" in output.lower()
