"""Tests for backend.core.incremental_builder"""

import pytest
from backend.core.incremental_builder import (
    IncrementalBuilder,
    BuildScope,
    DependencyInfo,
)


# ── File Hash Tracking ────────────────────────────────────

class TestGetChangedFiles:
    def test_detects_modified_file(self):
        builder = IncrementalBuilder()
        builder.update_hashes({"src/main.js": "const x = 1;"})
        changed = builder.get_changed_files({"src/main.js": "const x = 2;"})
        assert "src/main.js" in changed

    def test_no_changes_returns_empty(self):
        builder = IncrementalBuilder()
        files = {"src/main.js": "const x = 1;"}
        builder.update_hashes(files)
        changed = builder.get_changed_files(files)
        assert len(changed) == 0

    def test_detects_new_file(self):
        builder = IncrementalBuilder()
        builder.update_hashes({"src/main.js": "const x = 1;"})
        changed = builder.get_changed_files({
            "src/main.js": "const x = 1;",
            "src/new.js": "const y = 2;",
        })
        assert "src/new.js" in changed
        assert "src/main.js" not in changed

    def test_detects_deleted_file(self):
        builder = IncrementalBuilder()
        builder.update_hashes({
            "src/main.js": "const x = 1;",
            "src/old.js": "const y = 2;",
        })
        changed = builder.get_changed_files({"src/main.js": "const x = 1;"})
        assert "src/old.js" in changed

    def test_empty_initial_state(self):
        builder = IncrementalBuilder()
        changed = builder.get_changed_files({"src/main.js": "const x = 1;"})
        assert "src/main.js" in changed

    def test_multiple_changes(self):
        builder = IncrementalBuilder()
        builder.update_hashes({
            "src/a.js": "a",
            "src/b.js": "b",
            "src/c.js": "c",
        })
        changed = builder.get_changed_files({
            "src/a.js": "a_modified",
            "src/b.js": "b",
            "src/c.js": "c_modified",
        })
        assert changed == {"src/a.js", "src/c.js"}


# ── Dependency Graph Building ─────────────────────────────

class TestDependencyGraph:
    def test_parses_es_module_import(self):
        builder = IncrementalBuilder()
        files = {
            "src/main.js": 'import { Player } from "./player";\nconsole.log(Player);',
            "src/player.js": "export class Player {}",
        }
        builder.build_dependency_graph(files)
        info = builder.get_dependency_info("src/main.js")
        assert "src/player.js" in info.imports

    def test_parses_require(self):
        builder = IncrementalBuilder()
        files = {
            "src/main.js": 'const utils = require("./utils");\nconsole.log(utils);',
            "src/utils.js": "module.exports = {};",
        }
        builder.build_dependency_graph(files)
        info = builder.get_dependency_info("src/main.js")
        assert "src/utils.js" in info.imports

    def test_parses_dynamic_import(self):
        builder = IncrementalBuilder()
        files = {
            "src/main.js": 'const mod = await import("./lazy");\nconsole.log(mod);',
            "src/lazy.js": "export default 42;",
        }
        builder.build_dependency_graph(files)
        info = builder.get_dependency_info("src/main.js")
        assert "src/lazy.js" in info.imports

    def test_ignores_npm_packages(self):
        builder = IncrementalBuilder()
        files = {
            "src/main.js": 'import Phaser from "phaser";\nconsole.log(Phaser);',
        }
        builder.build_dependency_graph(files)
        info = builder.get_dependency_info("src/main.js")
        assert len(info.imports) == 0

    def test_reverse_graph(self):
        builder = IncrementalBuilder()
        files = {
            "src/main.js": 'import { Player } from "./player";',
            "src/player.js": "export class Player {}",
        }
        builder.build_dependency_graph(files)
        info = builder.get_dependency_info("src/player.js")
        assert "src/main.js" in info.imported_by

    def test_multiple_imports(self):
        builder = IncrementalBuilder()
        files = {
            "src/main.js": (
                'import { Player } from "./player";\n'
                'import { Enemy } from "./enemy";\n'
            ),
            "src/player.js": "export class Player {}",
            "src/enemy.js": "export class Enemy {}",
        }
        builder.build_dependency_graph(files)
        info = builder.get_dependency_info("src/main.js")
        assert "src/player.js" in info.imports
        assert "src/enemy.js" in info.imports

    def test_no_imports_file(self):
        builder = IncrementalBuilder()
        files = {
            "src/constants.js": "export const PI = 3.14;",
        }
        builder.build_dependency_graph(files)
        info = builder.get_dependency_info("src/constants.js")
        assert len(info.imports) == 0
        assert len(info.imported_by) == 0

    def test_subdirectory_imports(self):
        builder = IncrementalBuilder()
        files = {
            "src/main.js": 'import { Combat } from "./systems/combat";',
            "src/systems/combat.js": "export class Combat {}",
        }
        builder.build_dependency_graph(files)
        info = builder.get_dependency_info("src/main.js")
        assert "src/systems/combat.js" in info.imports

    def test_parent_directory_import(self):
        builder = IncrementalBuilder()
        files = {
            "src/systems/combat.js": 'import { config } from "../config";',
            "src/config.js": "export const config = {};",
        }
        builder.build_dependency_graph(files)
        info = builder.get_dependency_info("src/systems/combat.js")
        assert "src/config.js" in info.imports


# ── Transitive Dependents ─────────────────────────────────

class TestAffectedFiles:
    def test_direct_dependent(self):
        builder = IncrementalBuilder()
        files = {
            "src/player.js": "export class Player {}",
            "src/main.js": 'import { Player } from "./player";',
        }
        builder.build_dependency_graph(files)
        affected = builder.get_affected_files({"src/player.js"})
        assert "src/main.js" in affected

    def test_transitive_dependent(self):
        builder = IncrementalBuilder()
        files = {
            "src/config.js": "export const CONFIG = {};",
            "src/player.js": 'import { CONFIG } from "./config";\nexport class Player {}',
            "src/main.js": 'import { Player } from "./player";',
        }
        builder.build_dependency_graph(files)
        affected = builder.get_affected_files({"src/config.js"})
        assert "src/player.js" in affected
        assert "src/main.js" in affected

    def test_no_dependents(self):
        builder = IncrementalBuilder()
        files = {
            "src/isolated.js": "console.log('hello');",
            "src/other.js": "console.log('world');",
        }
        builder.build_dependency_graph(files)
        affected = builder.get_affected_files({"src/isolated.js"})
        assert len(affected) == 0

    def test_circular_dependency_no_infinite_loop(self):
        builder = IncrementalBuilder()
        files = {
            "src/a.js": 'import { B } from "./b";\nexport class A {}',
            "src/b.js": 'import { A } from "./a";\nexport class B {}',
        }
        builder.build_dependency_graph(files)
        # Should not hang — must return in finite time
        affected = builder.get_affected_files({"src/a.js"})
        assert "src/b.js" in affected


# ── Build Scope ───────────────────────────────────────────

class TestBuildScope:
    def test_first_build_is_full(self):
        builder = IncrementalBuilder()
        files = {"src/main.js": "console.log('hi');"}
        scope = builder.get_build_scope(files)
        assert scope.is_full_rebuild is True
        assert scope.has_changes is True
        assert "src/main.js" in scope.all_files_to_rebuild

    def test_no_changes_after_update(self):
        builder = IncrementalBuilder()
        files = {"src/main.js": "console.log('hi');"}
        builder.get_build_scope(files)
        builder.update_hashes(files)
        scope = builder.get_build_scope(files)
        assert scope.has_changes is False
        assert scope.file_count == 0

    def test_incremental_rebuild(self):
        builder = IncrementalBuilder()
        files = {
            "src/player.js": "export class Player {}",
            "src/main.js": 'import { Player } from "./player";\nnew Player();',
            "src/utils.js": "export function log() {}",
        }
        # First build
        scope = builder.get_build_scope(files)
        builder.update_hashes(files)

        # Change only player.js
        files["src/player.js"] = "export class Player { hp = 100; }"
        scope = builder.get_build_scope(files)

        assert scope.is_full_rebuild is False
        assert "src/player.js" in scope.changed_files
        assert "src/main.js" in scope.affected_files
        assert "src/utils.js" not in scope.all_files_to_rebuild

    def test_full_rebuild_when_many_changes(self):
        builder = IncrementalBuilder()
        # Create 10 files
        files = {f"src/file{i}.js": f"const x{i} = {i};" for i in range(10)}
        scope = builder.get_build_scope(files)
        builder.update_hashes(files)

        # Change 8 of 10 files (80% > 70% threshold)
        for i in range(8):
            files[f"src/file{i}.js"] = f"const x{i} = {i + 100};"
        scope = builder.get_build_scope(files)
        assert scope.is_full_rebuild is True

    def test_build_scope_file_count(self):
        scope = BuildScope(
            changed_files={"a.js"},
            affected_files={"b.js"},
            all_files_to_rebuild={"a.js", "b.js"},
        )
        assert scope.file_count == 2


# ── Reset ─────────────────────────────────────────────────

class TestReset:
    def test_reset_clears_all(self):
        builder = IncrementalBuilder()
        files = {"src/main.js": "console.log('hi');"}
        builder.get_build_scope(files)
        builder.update_hashes(files)

        builder.reset()

        # After reset, everything should be fresh
        scope = builder.get_build_scope(files)
        assert scope.is_full_rebuild is True


# ── Stats ─────────────────────────────────────────────────

class TestStats:
    def test_stats_after_graph_build(self):
        builder = IncrementalBuilder()
        files = {
            "src/main.js": 'import { Player } from "./player";',
            "src/player.js": "export class Player {}",
        }
        builder.build_dependency_graph(files)
        builder.update_hashes(files)

        stats = builder.get_stats()
        assert stats["tracked_files"] == 2
        assert stats["graph_nodes"] == 2
        assert stats["graph_edges"] >= 1
        assert stats["max_dependents"] >= 1

    def test_stats_empty(self):
        builder = IncrementalBuilder()
        stats = builder.get_stats()
        assert stats["tracked_files"] == 0
        assert stats["graph_nodes"] == 0
        assert stats["graph_edges"] == 0
        assert stats["max_dependents"] == 0


# ── Import Extraction Edge Cases ──────────────────────────

class TestImportExtraction:
    def test_import_default(self):
        builder = IncrementalBuilder()
        files = {
            "src/main.js": 'import Game from "./game";',
            "src/game.js": "export default class Game {}",
        }
        builder.build_dependency_graph(files)
        info = builder.get_dependency_info("src/main.js")
        assert "src/game.js" in info.imports

    def test_import_star(self):
        builder = IncrementalBuilder()
        files = {
            "src/main.js": 'import * as Utils from "./utils";',
            "src/utils.js": "export function log() {}",
        }
        builder.build_dependency_graph(files)
        info = builder.get_dependency_info("src/main.js")
        assert "src/utils.js" in info.imports

    def test_import_side_effect(self):
        builder = IncrementalBuilder()
        files = {
            "src/main.js": 'import "./polyfill";',
            "src/polyfill.js": "// polyfill code",
        }
        builder.build_dependency_graph(files)
        info = builder.get_dependency_info("src/main.js")
        assert "src/polyfill.js" in info.imports

    def test_mixed_imports(self):
        builder = IncrementalBuilder()
        files = {
            "src/app.js": (
                'import { A } from "./a";\n'
                'const b = require("./b");\n'
                'const c = await import("./c");\n'
            ),
            "src/a.js": "export const A = 1;",
            "src/b.js": "module.exports = 2;",
            "src/c.js": "export default 3;",
        }
        builder.build_dependency_graph(files)
        info = builder.get_dependency_info("src/app.js")
        assert "src/a.js" in info.imports
        assert "src/b.js" in info.imports
        assert "src/c.js" in info.imports
