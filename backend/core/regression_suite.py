"""
GORVAX GAME FACTORY — Automated Regression Suite

Generates heuristic unit tests at milestones and runs them
before builds to catch regressions.  No LLM needed — tests
are structural checks on exports, functions, and config constants.

Roadmap v3 Item #10.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Milestone threshold: score >= this triggers test generation
MILESTONE_THRESHOLD = 60


@dataclass
class RegressionResult:
    """Result of running the regression test suite."""

    passed: int = 0
    failed: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def is_passing(self) -> bool:
        return self.failed == 0 and len(self.errors) == 0

    @property
    def total(self) -> int:
        return self.passed + self.failed

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "failed": self.failed,
            "total": self.total,
            "is_passing": self.is_passing,
            "errors": self.errors[:20],  # cap for prompt size
        }


@dataclass
class RegressionTest:
    """A single heuristic regression test."""

    name: str
    target_file: str
    check_type: str  # "export_exists" | "function_exists" | "config_key"
    expected_value: str
    created_at_iteration: int


class RegressionSuite:
    """Generates and runs heuristic regression tests.

    Tests check structural properties of game source files:
    - Exported functions / classes exist
    - Config keys are present
    - Expected patterns appear in the source

    Usage::

        suite = RegressionSuite(Path("data/regression_tests"))
        result = suite.run_tests(current_files)
        if suite.should_generate(score=75, best_score=70):
            suite.generate_tests(current_files, score=75, iteration=5)
    """

    def __init__(self, tests_dir: Path) -> None:
        self.tests_dir = tests_dir
        self._tests: list[RegressionTest] = []
        self._load()

    # ── Public API ────────────────────────────────────────

    def should_generate(
        self, score: float, best_score: float = 0.0,
    ) -> bool:
        """True if the current build is a milestone worth snapshotting."""
        return score >= MILESTONE_THRESHOLD and score >= best_score

    def generate_tests(
        self,
        game_files: dict[str, str],
        score: float,
        iteration: int,
    ) -> int:
        """Generate heuristic tests from current game files.

        Returns number of tests generated.
        """
        new_tests: list[RegressionTest] = []

        for file_path, content in game_files.items():
            if not self._is_testable(file_path):
                continue

            # Check for exported functions
            exports = self._extract_exports(content)
            for export_name in exports:
                test = RegressionTest(
                    name=f"export_{file_path}_{export_name}",
                    target_file=file_path,
                    check_type="export_exists",
                    expected_value=export_name,
                    created_at_iteration=iteration,
                )
                new_tests.append(test)

            # Check for config keys (in config.js)
            if "config" in file_path.lower():
                config_keys = self._extract_config_keys(content)
                for key in config_keys:
                    test = RegressionTest(
                        name=f"config_{file_path}_{key}",
                        target_file=file_path,
                        check_type="config_key",
                        expected_value=key,
                        created_at_iteration=iteration,
                    )
                    new_tests.append(test)

            # Check for class definitions
            functions = self._extract_functions(content)
            for func_name in functions:
                test = RegressionTest(
                    name=f"func_{file_path}_{func_name}",
                    target_file=file_path,
                    check_type="function_exists",
                    expected_value=func_name,
                    created_at_iteration=iteration,
                )
                new_tests.append(test)

        # Merge with existing tests (avoid duplicates by name)
        existing_names = {t.name for t in self._tests}
        added = 0
        for test in new_tests:
            if test.name not in existing_names:
                self._tests.append(test)
                existing_names.add(test.name)
                added += 1

        self._save()
        logger.info(
            "📋 Regression: generated %d new test(s) at milestone (score=%.0f, iter=%d). Total: %d",
            added, score, iteration, len(self._tests),
        )
        return added

    def run_tests(
        self, game_files: dict[str, str],
    ) -> RegressionResult:
        """Run all regression tests against current game files."""
        if not self._tests:
            return RegressionResult()

        passed = 0
        failed = 0
        errors: list[str] = []

        for test in self._tests:
            content = game_files.get(test.target_file, "")

            if not content:
                # File was deleted — not necessarily a failure
                continue

            ok = self._run_single_test(test, content)
            if ok:
                passed += 1
            else:
                failed += 1
                errors.append(
                    f"FAIL: {test.check_type} '{test.expected_value}' "
                    f"not found in {test.target_file}",
                )

        return RegressionResult(passed=passed, failed=failed, errors=errors)

    def prune_obsolete(self, current_files: dict[str, str]) -> int:
        """Remove tests for files that no longer exist.

        Returns number of pruned tests.
        """
        before = len(self._tests)
        self._tests = [
            t for t in self._tests
            if t.target_file in current_files
        ]
        pruned = before - len(self._tests)
        if pruned > 0:
            self._save()
            logger.info("📋 Regression: pruned %d obsolete test(s)", pruned)
        return pruned

    def get_stats(self) -> dict[str, Any]:
        """Return test suite statistics."""
        return {
            "total_tests": len(self._tests),
            "files_covered": len({t.target_file for t in self._tests}),
            "check_types": dict(
                self._count_by_type(),
            ),
        }

    # ── Private Helpers ───────────────────────────────────

    @staticmethod
    def _is_testable(file_path: str) -> bool:
        """Only test JS/TS source files."""
        return file_path.endswith((".js", ".ts", ".jsx", ".tsx"))

    @staticmethod
    def _extract_exports(content: str) -> list[str]:
        """Extract exported names from JS/TS content."""
        exports: list[str] = []

        # export function/class/const name
        for match in re.finditer(
            r"export\s+(?:default\s+)?(?:function|class|const|let|var)\s+(\w+)",
            content,
        ):
            exports.append(match.group(1))

        # module.exports = { ... } — extract keys
        for match in re.finditer(
            r"module\.exports\s*=\s*\{([^}]+)\}",
            content,
        ):
            for key_match in re.finditer(r"(\w+)\s*[,:]", match.group(1)):
                exports.append(key_match.group(1))

        return exports

    @staticmethod
    def _extract_functions(content: str) -> list[str]:
        """Extract function/method names (non-exported too)."""
        functions: list[str] = []

        # function declarations
        for match in re.finditer(r"(?<!export\s)function\s+(\w+)", content):
            functions.append(match.group(1))

        # Class methods
        for match in re.finditer(
            r"^\s+(\w+)\s*\([^)]*\)\s*\{",
            content,
            re.MULTILINE,
        ):
            name = match.group(1)
            if name not in ("if", "for", "while", "switch", "catch"):
                functions.append(name)

        return functions

    @staticmethod
    def _extract_config_keys(content: str) -> list[str]:
        """Extract top-level config keys."""
        keys: list[str] = []
        for match in re.finditer(r"(\w+)\s*:\s*[^,\n]+", content):
            name = match.group(1)
            if name and not name.startswith("//"):
                keys.append(name)
        return keys[:20]  # Cap to avoid huge test suites

    def _run_single_test(
        self, test: RegressionTest, content: str,
    ) -> bool:
        """Run a single heuristic test."""
        if test.check_type == "export_exists":
            return test.expected_value in content

        if test.check_type == "function_exists":
            return test.expected_value in content

        if test.check_type == "config_key":
            return test.expected_value in content

        return True  # Unknown check type — pass

    def _count_by_type(self) -> dict[str, int]:
        """Count tests by check type."""
        counts: dict[str, int] = {}
        for t in self._tests:
            counts[t.check_type] = counts.get(t.check_type, 0) + 1
        return counts

    def _save(self) -> None:
        """Persist tests to disk."""
        self.tests_dir.mkdir(parents=True, exist_ok=True)
        data = [
            {
                "name": t.name,
                "target_file": t.target_file,
                "check_type": t.check_type,
                "expected_value": t.expected_value,
                "created_at_iteration": t.created_at_iteration,
            }
            for t in self._tests
        ]
        path = self.tests_dir / "regression_tests.json"
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _load(self) -> None:
        """Load previously saved tests."""
        path = self.tests_dir / "regression_tests.json"
        if not path.exists():
            return

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            self._tests = [
                RegressionTest(**item) for item in data
            ]
            logger.info("📋 Regression: loaded %d test(s)", len(self._tests))
        except Exception as exc:
            logger.warning("Failed to load regression tests: %s", exc)
            self._tests = []
