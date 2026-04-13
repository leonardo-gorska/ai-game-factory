"""
Tests for DiffAnalyzer — code change risk analysis.
"""

import pytest
from pathlib import Path

from backend.core.diff_analyzer import DiffAnalyzer, DiffReport


@pytest.fixture
def analyzer(tmp_path: Path) -> DiffAnalyzer:
    return DiffAnalyzer(game_dir=tmp_path)


# ── Basic Analysis ────────────────────────────────

class TestAnalyze:
    def test_returns_diff_report(self, analyzer: DiffAnalyzer):
        report = analyzer.analyze(
            previous_files={"a.js": "console.log('hello');"},
            current_files={"a.js": "console.log('world');"},
        )
        assert isinstance(report, DiffReport)

    def test_no_change(self, analyzer: DiffAnalyzer):
        files = {"a.js": "var x = 1;"}
        report = analyzer.analyze(previous_files=files, current_files=files)
        assert report.files_modified == 0
        assert report.total_churn == 0
        assert report.risk_score == 0 or report.risk_level == "low"

    def test_new_file(self, analyzer: DiffAnalyzer):
        report = analyzer.analyze(
            previous_files={},
            current_files={"new.js": "console.log('hi');\n"},
        )
        assert report.files_added == 1
        assert report.lines_added > 0

    def test_deleted_file(self, analyzer: DiffAnalyzer):
        report = analyzer.analyze(
            previous_files={"old.js": "var x = 1;\n"},
            current_files={},
        )
        assert report.files_deleted == 1
        assert report.lines_removed > 0

    def test_modified_file(self, analyzer: DiffAnalyzer):
        report = analyzer.analyze(
            previous_files={"a.js": "var x = 1;\n"},
            current_files={"a.js": "var x = 2;\nvar y = 3;\n"},
        )
        assert report.files_modified == 1


# ── Risk Score ────────────────────────────────────

class TestRiskScore:
    def test_low_risk_small_change(self, analyzer: DiffAnalyzer):
        report = analyzer.analyze(
            previous_files={"a.js": "var x = 1;"},
            current_files={"a.js": "var x = 2;"},
        )
        assert report.risk_score < 50

    def test_higher_risk_large_change(self, analyzer: DiffAnalyzer):
        prev = {"a.js": "\n".join([f"line{i}" for i in range(100)])}
        curr = {"a.js": "\n".join([f"newline{i}" for i in range(200)])}
        report = analyzer.analyze(previous_files=prev, current_files=curr)
        assert report.risk_score > 0  # some risk for a big change

    def test_risk_level_is_valid(self, analyzer: DiffAnalyzer):
        report = analyzer.analyze(
            previous_files={"a.js": "x"},
            current_files={"a.js": "y"},
        )
        assert report.risk_level in ("low", "medium", "high", "critical")


# ── Critical Files ────────────────────────────────

class TestCriticalFiles:
    def test_critical_file_detected(self, analyzer: DiffAnalyzer):
        report = analyzer.analyze(
            previous_files={"config.js": "var x = 1;"},
            current_files={"config.js": "var x = 2;"},
        )
        assert len(report.critical_files_touched) > 0


# ── Risky Patterns ────────────────────────────────

class TestRiskyPatterns:
    def test_eval_pattern_detected(self, analyzer: DiffAnalyzer):
        report = analyzer.analyze(
            previous_files={},
            current_files={"bad.js": "eval('alert(1)');\n"},
        )
        assert len(report.risky_patterns_found) > 0


# ── to_dict ───────────────────────────────────────

class TestToDict:
    def test_to_dict_keys(self, analyzer: DiffAnalyzer):
        report = analyzer.analyze(
            previous_files={"a.js": "x"},
            current_files={"a.js": "y"},
        )
        d = report.to_dict()
        expected = {
            "files_added", "files_modified", "files_deleted",
            "lines_added", "lines_removed", "total_churn",
            "critical_files_touched", "risky_patterns_found",
            "cyclomatic_complexity", "risk_score", "risk_level",
        }
        assert set(d.keys()) == expected


# ── generate_diff ─────────────────────────────────

class TestGenerateDiff:
    def test_shows_changes(self, analyzer: DiffAnalyzer):
        diff = analyzer.generate_diff(
            previous_files={"a.js": "var x = 1;\n"},
            current_files={"a.js": "var x = 2;\nvar y = 3;\n"},
        )
        assert "+" in diff  # additions present
        assert "-" in diff  # removals present
        assert "a.js" in diff

    def test_new_file(self, analyzer: DiffAnalyzer):
        diff = analyzer.generate_diff(
            previous_files={},
            current_files={"new.js": "console.log('hi');\n"},
        )
        assert "+console.log" in diff
        assert "new.js" in diff

    def test_no_changes(self, analyzer: DiffAnalyzer):
        files = {"a.js": "var x = 1;\n"}
        diff = analyzer.generate_diff(previous_files=files, current_files=files)
        assert diff == ""

    def test_truncation(self, analyzer: DiffAnalyzer):
        # Create a large diff that exceeds max_chars
        big_content = "\n".join([f"line_{i} = {i};" for i in range(500)])
        diff = analyzer.generate_diff(
            previous_files={"big.js": ""},
            current_files={"big.js": big_content},
            max_chars=200,
        )
        assert len(diff) <= 220  # 200 + len("... [truncated]") + newline
        assert "truncated" in diff

