"""Unit tests for RegressionSuite (Roadmap v3 Item #10)."""

from __future__ import annotations

import json
import pytest
from pathlib import Path
from backend.core.regression_suite import (
    RegressionSuite,
    RegressionResult,
    RegressionTest,
    MILESTONE_THRESHOLD,
)


# ── Fixtures ──────────────────────────────────────────

SAMPLE_GAME_FILES: dict[str, str] = {
    "src/player.js": """
export class Player {
    constructor() { this.hp = 100; }
    attack(target) { target.hp -= 10; }
}
export function createPlayer() { return new Player(); }
""",
    "src/config.js": """
export const Config = {
    maxHP: 100,
    speed: 5,
    damage: 10,
};
""",
    "src/enemy.js": """
import { Config } from './config.js';
export class Enemy {
    constructor() { this.hp = Config.maxHP; }
}
""",
    "src/styles.css": "body { margin: 0; }",
}


@pytest.fixture
def suite(tmp_path: Path) -> RegressionSuite:
    return RegressionSuite(tmp_path / "regression")


# ── Milestone Detection ──────────────────────────────

class TestMilestoneDetection:
    def test_below_threshold(self, suite: RegressionSuite) -> None:
        assert not suite.should_generate(score=30, best_score=0)

    def test_at_threshold(self, suite: RegressionSuite) -> None:
        assert suite.should_generate(score=MILESTONE_THRESHOLD, best_score=0)

    def test_above_threshold(self, suite: RegressionSuite) -> None:
        assert suite.should_generate(score=80, best_score=70)

    def test_below_best_score(self, suite: RegressionSuite) -> None:
        assert not suite.should_generate(score=65, best_score=70)


# ── Test Generation ──────────────────────────────────

class TestGeneration:
    def test_generates_tests(self, suite: RegressionSuite) -> None:
        count = suite.generate_tests(SAMPLE_GAME_FILES, score=70, iteration=1)
        assert count > 0

    def test_no_tests_for_css(self, suite: RegressionSuite) -> None:
        count = suite.generate_tests(
            {"src/styles.css": "body { margin: 0; }"},
            score=70,
            iteration=1,
        )
        assert count == 0

    def test_no_duplicate_tests(self, suite: RegressionSuite) -> None:
        count1 = suite.generate_tests(SAMPLE_GAME_FILES, score=70, iteration=1)
        count2 = suite.generate_tests(SAMPLE_GAME_FILES, score=75, iteration=2)
        assert count1 > 0
        assert count2 == 0  # Same files, same exports — no new tests

    def test_exports_detected(self, suite: RegressionSuite) -> None:
        suite.generate_tests(SAMPLE_GAME_FILES, score=70, iteration=1)
        stats = suite.get_stats()
        assert stats["total_tests"] > 0
        assert stats["files_covered"] > 0

    def test_config_keys_detected(self, suite: RegressionSuite) -> None:
        suite.generate_tests(SAMPLE_GAME_FILES, score=70, iteration=1)
        stats = suite.get_stats()
        check_types = stats["check_types"]
        assert "config_key" in check_types


# ── Test Execution ────────────────────────────────────

class TestExecution:
    def test_passing_suite(self, suite: RegressionSuite) -> None:
        suite.generate_tests(SAMPLE_GAME_FILES, score=70, iteration=1)
        result = suite.run_tests(SAMPLE_GAME_FILES)
        assert result.is_passing
        assert result.passed > 0
        assert result.failed == 0

    def test_failing_when_export_removed(self, suite: RegressionSuite) -> None:
        suite.generate_tests(SAMPLE_GAME_FILES, score=70, iteration=1)
        # Remove Player export
        modified = {**SAMPLE_GAME_FILES}
        modified["src/player.js"] = "const x = 1;"
        result = suite.run_tests(modified)
        assert result.failed > 0

    def test_empty_suite_passes(self, suite: RegressionSuite) -> None:
        result = suite.run_tests(SAMPLE_GAME_FILES)
        assert result.is_passing
        assert result.total == 0

    def test_deleted_file_skipped(self, suite: RegressionSuite) -> None:
        suite.generate_tests(SAMPLE_GAME_FILES, score=70, iteration=1)
        # Run with a subset (enemy.js deleted)
        subset = {k: v for k, v in SAMPLE_GAME_FILES.items() if "enemy" not in k}
        result = suite.run_tests(subset)
        # Should not fail for deleted files
        assert result.failed == 0


# ── Pruning ───────────────────────────────────────────

class TestPruning:
    def test_prune_removes_obsolete(self, suite: RegressionSuite) -> None:
        suite.generate_tests(SAMPLE_GAME_FILES, score=70, iteration=1)
        total_before = suite.get_stats()["total_tests"]
        # Prune with only config.js remaining
        pruned = suite.prune_obsolete({"src/config.js": SAMPLE_GAME_FILES["src/config.js"]})
        assert pruned > 0
        assert suite.get_stats()["total_tests"] < total_before

    def test_prune_nothing_when_all_exist(self, suite: RegressionSuite) -> None:
        suite.generate_tests(SAMPLE_GAME_FILES, score=70, iteration=1)
        pruned = suite.prune_obsolete(SAMPLE_GAME_FILES)
        assert pruned == 0


# ── Persistence ───────────────────────────────────────

class TestPersistence:
    def test_save_and_reload(self, tmp_path: Path) -> None:
        path = tmp_path / "regression"
        suite1 = RegressionSuite(path)
        suite1.generate_tests(SAMPLE_GAME_FILES, score=70, iteration=1)
        count1 = suite1.get_stats()["total_tests"]

        # Reload from disk
        suite2 = RegressionSuite(path)
        count2 = suite2.get_stats()["total_tests"]
        assert count2 == count1

    def test_json_format(self, tmp_path: Path) -> None:
        path = tmp_path / "regression"
        suite = RegressionSuite(path)
        suite.generate_tests(SAMPLE_GAME_FILES, score=70, iteration=1)

        json_path = path / "regression_tests.json"
        assert json_path.exists()
        data = json.loads(json_path.read_text())
        assert isinstance(data, list)
        assert len(data) > 0
        assert "name" in data[0]
        assert "check_type" in data[0]


# ── RegressionResult Dataclass ────────────────────────

class TestRegressionResult:
    def test_defaults(self) -> None:
        r = RegressionResult()
        assert r.is_passing
        assert r.total == 0

    def test_with_failures(self) -> None:
        r = RegressionResult(passed=5, failed=2, errors=["a", "b"])
        assert not r.is_passing
        assert r.total == 7

    def test_to_dict(self) -> None:
        r = RegressionResult(passed=3, failed=1, errors=["err1"])
        d = r.to_dict()
        assert d["passed"] == 3
        assert d["failed"] == 1
        assert not d["is_passing"]
