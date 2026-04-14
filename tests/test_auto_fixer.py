"""Tests for backend.core.auto_fixer"""

import pytest
from backend.core.auto_fixer import (
    try_auto_fix,
    AutoFixReport,
    FixResult,
    _fix_missing_semicolon,
    _fix_trailing_comma,
    _fix_double_semicolon,
    _fix_unused_import,
    _fix_duplicate_declaration,
)


# ── Missing Semicolon ─────────────────────────────────────

class TestFixMissingSemicolon:
    def test_adds_semicolon(self):
        content = "const x = 1\n"
        result, fixed = _fix_missing_semicolon(content, 1)
        assert fixed is True
        assert result == "const x = 1;\n"

    def test_no_fix_already_has_semicolon(self):
        content = "const x = 1;\n"
        result, fixed = _fix_missing_semicolon(content, 1)
        assert fixed is False

    def test_no_fix_for_block_opener(self):
        content = "function foo() {\n"
        result, fixed = _fix_missing_semicolon(content, 1)
        assert fixed is False

    def test_no_fix_for_block_closer(self):
        content = "}\n"
        result, fixed = _fix_missing_semicolon(content, 1)
        assert fixed is False

    def test_none_line(self):
        content = "const x = 1\n"
        result, fixed = _fix_missing_semicolon(content, None)
        assert fixed is False

    def test_out_of_range_line(self):
        content = "const x = 1\n"
        result, fixed = _fix_missing_semicolon(content, 99)
        assert fixed is False


# ── Trailing Comma ────────────────────────────────────────

class TestFixTrailingComma:
    def test_removes_trailing_comma_before_brace(self):
        content = "  foo,\n}\n"
        result, fixed = _fix_trailing_comma(content, 2)
        assert fixed is True
        assert ",}" not in result

    def test_removes_inline_trailing_comma(self):
        content = "const x = [1, 2, 3,]\n"
        result, fixed = _fix_trailing_comma(content, 1)
        assert fixed is True
        assert ",]" not in result

    def test_no_fix_when_no_trailing_comma(self):
        content = "const x = [1, 2, 3]\n"
        result, fixed = _fix_trailing_comma(content, 1)
        assert fixed is False


# ── Double Semicolon ──────────────────────────────────────

class TestFixDoubleSemicolon:
    def test_fixes_double_semicolon(self):
        content = "const x = 1;;\n"
        result, fixed = _fix_double_semicolon(content, 1)
        assert fixed is True
        assert result == "const x = 1;\n"

    def test_skips_for_loop(self):
        content = "for (let i = 0;; i++) {}\n"
        result, fixed = _fix_double_semicolon(content, 1)
        assert fixed is False

    def test_no_line_scans_whole_file(self):
        content = "const a = 1;;\nconst b = 2;\n"
        result, fixed = _fix_double_semicolon(content, None)
        assert fixed is True
        assert ";;" not in result

    def test_no_fix_clean_code(self):
        content = "const x = 1;\n"
        result, fixed = _fix_double_semicolon(content, 1)
        assert fixed is False


# ── Unused Import ─────────────────────────────────────────

class TestFixUnusedImport:
    def test_removes_import_line(self):
        content = 'import { foo } from "./bar";\nconst x = 1;\n'
        result, fixed = _fix_unused_import(content, 1)
        assert fixed is True
        assert "import" not in result
        assert "const x" in result

    def test_removes_require_line(self):
        content = 'const foo = require("./bar");\nconst x = 1;\n'
        result, fixed = _fix_unused_import(content, 1)
        assert fixed is True

    def test_no_fix_for_non_import(self):
        content = "const x = 1;\n"
        result, fixed = _fix_unused_import(content, 1)
        assert fixed is False

    def test_none_line(self):
        content = 'import { foo } from "./bar";\n'
        result, fixed = _fix_unused_import(content, None)
        assert fixed is False


# ── Duplicate Declaration ─────────────────────────────────

class TestFixDuplicateDeclaration:
    def test_converts_const_to_assignment(self):
        content = "const x = 1;\nconst x = 2;\n"
        result, fixed = _fix_duplicate_declaration(content, 2)
        assert fixed is True
        lines = result.splitlines()
        assert lines[0] == "const x = 1;"
        assert "const" not in lines[1]
        assert "x = 2;" in lines[1]

    def test_converts_let_to_assignment(self):
        content = "let x = 1;\nlet x = 2;\n"
        result, fixed = _fix_duplicate_declaration(content, 2)
        assert fixed is True

    def test_no_fix_for_non_declaration(self):
        content = "x = 2;\n"
        result, fixed = _fix_duplicate_declaration(content, 1)
        assert fixed is False


# ── Full Auto-Fix Integration ─────────────────────────────

class TestTryAutoFix:
    def test_no_errors_no_fixes(self):
        files, report = try_auto_fix([], {"test.js": "const x = 1;\n"})
        assert report.any_fixed is False
        assert report.count == 0

    def test_fixes_semicolon_error(self):
        errors = [
            {"category": "syntax", "message": "Missing semicolon", "file": "test.js", "line": 1},
        ]
        files = {"test.js": "const x = 1\n"}
        new_files, report = try_auto_fix(errors, files)
        assert report.any_fixed is True
        assert report.count == 1
        assert ";" in new_files["test.js"]

    def test_unknown_file_skipped(self):
        errors = [
            {"category": "syntax", "message": "Missing semicolon", "file": "missing.js", "line": 1},
        ]
        files = {"test.js": "const x = 1\n"}
        new_files, report = try_auto_fix(errors, files)
        assert report.any_fixed is False

    def test_no_mutation_of_original(self):
        errors = [
            {"category": "syntax", "message": "Missing semicolon", "file": "test.js", "line": 1},
        ]
        original = {"test.js": "const x = 1\n"}
        new_files, _ = try_auto_fix(errors, original)
        assert original["test.js"] == "const x = 1\n"  # original unchanged

    def test_summary_message(self):
        report = AutoFixReport(fixes=[
            FixResult(fixed=True, file="a.js", description="missing_semicolon", original_line=1, rule="missing_semicolon"),
            FixResult(fixed=False, file="b.js", description="trailing_comma", original_line=2, rule="trailing_comma"),
        ])
        assert report.any_fixed is True
        assert report.count == 1
        assert "Auto-Fix" in report.summary

    def test_empty_summary_when_no_fixes(self):
        report = AutoFixReport()
        assert "Nenhum" in report.summary
