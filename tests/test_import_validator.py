"""
Tests for backend.core.import_validator — Pre-flight Import Validator.
"""

from pathlib import Path

import pytest

from backend.core.import_validator import validate_imports


# ── Helpers ────────────────────────────────────────


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


# ── Tests ──────────────────────────────────────────


class TestValidateImports:
    def test_valid_imports_no_fixes(self, tmp_path: Path):
        """All imports resolve correctly → no fixes."""
        _write(tmp_path / "main.js", "import { Foo } from './utils.js';\n")
        _write(tmp_path / "utils.js", "export const Foo = 1;\n")

        fixed, fixes = validate_imports(tmp_path)

        assert fixed is False
        assert fixes == []

    def test_broken_import_gets_fixed(self, tmp_path: Path):
        """Import to non-existent file with a similar file → auto-fix."""
        # main.js imports './utls.js' but the real file is 'utils.js'
        _write(tmp_path / "main.js", "import { Foo } from './utls.js';\n")
        _write(tmp_path / "utils.js", "export const Foo = 1;\n")

        fixed, fixes = validate_imports(tmp_path)

        assert fixed is True
        assert len(fixes) == 1
        assert "FIXED" in fixes[0]

        # Verify the file was rewritten with the correct path
        content = (tmp_path / "main.js").read_text(encoding="utf-8")
        assert "./utils.js" in content
        assert "./utls.js" not in content

    def test_broken_import_no_match(self, tmp_path: Path):
        """Import to non-existent file with no similar file → warn only."""
        _write(tmp_path / "main.js", "import { X } from './totally_different.js';\n")
        _write(tmp_path / "utils.js", "export const X = 1;\n")

        fixed, fixes = validate_imports(tmp_path)

        assert fixed is True
        assert len(fixes) == 1
        assert "WARN" in fixes[0]

        # File should NOT be rewritten
        content = (tmp_path / "main.js").read_text(encoding="utf-8")
        assert "./totally_different.js" in content

    def test_package_imports_ignored(self, tmp_path: Path):
        """Package imports like 'phaser' should be ignored."""
        _write(
            tmp_path / "main.js",
            "import Phaser from 'phaser';\nimport { Scene } from 'phaser';\n",
        )

        fixed, fixes = validate_imports(tmp_path)

        assert fixed is False
        assert fixes == []

    def test_empty_directory(self, tmp_path: Path):
        """Empty src directory → no fixes."""
        tmp_path.mkdir(exist_ok=True)

        fixed, fixes = validate_imports(tmp_path)

        assert fixed is False
        assert fixes == []

    def test_subdirectory_imports(self, tmp_path: Path):
        """Imports across subdirectories should resolve correctly."""
        _write(
            tmp_path / "scenes" / "GameScene.js",
            "import { Hero } from '../entities/Hero.js';\n",
        )
        _write(tmp_path / "entities" / "Hero.js", "export class Hero {}\n")

        fixed, fixes = validate_imports(tmp_path)

        assert fixed is False
        assert fixes == []
