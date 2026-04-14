"""Tests for backend.core.quality_gate"""

import pytest
from backend.core.quality_gate import (
    run_quality_gate,
    GateResult,
    GateIssue,
    SEVERITY_ERROR,
    SEVERITY_WARNING,
    _strip_strings_and_comments,
    _check_bracket_balance,
    _check_import_resolution,
    _check_duplicate_declarations,
    _check_syntax_basics,
)


# ── Bracket Balance ───────────────────────────────────────

class TestBracketBalance:
    def test_balanced_code(self):
        code = "function foo() { return [1, 2, (3 + 4)]; }"
        issues = _check_bracket_balance("test.js", code)
        assert issues == []

    def test_unclosed_brace(self):
        code = "function foo() {\n  return 1;\n"
        issues = _check_bracket_balance("test.js", code)
        assert len(issues) == 1
        assert issues[0].rule == "bracket_balance"
        assert issues[0].severity == SEVERITY_ERROR

    def test_unclosed_paren(self):
        code = "const x = foo(\n  bar\n"
        issues = _check_bracket_balance("test.js", code)
        assert len(issues) == 1
        assert issues[0].rule == "bracket_balance"

    def test_extra_closing(self):
        code = "const x = 1; }"
        issues = _check_bracket_balance("test.js", code)
        assert len(issues) == 1
        assert "}" in issues[0].message

    def test_mismatched(self):
        code = "function foo() { return [1, 2); }"
        issues = _check_bracket_balance("test.js", code)
        assert len(issues) >= 1

    def test_empty_file(self):
        issues = _check_bracket_balance("test.js", "")
        assert issues == []

    def test_brackets_in_strings_ignored(self):
        code = 'const x = "{ [ ( } ] )";\n'
        issues = _check_bracket_balance("test.js", code)
        assert issues == []

    def test_brackets_in_comments_ignored(self):
        code = "// this has { unbalanced [\nconst x = 1;\n"
        issues = _check_bracket_balance("test.js", code)
        assert issues == []


# ── Import Resolution ─────────────────────────────────────

class TestImportResolution:
    def test_resolved_import(self):
        files = {
            "src/main.js": 'import { foo } from "./utils";\n',
            "src/utils.js": "export const foo = 1;\n",
        }
        issues = _check_import_resolution("src/main.js", files["src/main.js"], files)
        assert issues == []

    def test_unresolved_import(self):
        files = {
            "src/main.js": 'import { foo } from "./nonexistent";\n',
        }
        issues = _check_import_resolution("src/main.js", files["src/main.js"], files)
        assert len(issues) == 1
        assert issues[0].rule == "unresolved_import"
        assert "nonexistent" in issues[0].message

    def test_package_import_not_checked(self):
        files = {
            "src/main.js": 'import React from "react";\n',
        }
        issues = _check_import_resolution("src/main.js", files["src/main.js"], files)
        assert issues == []

    def test_no_imports(self):
        files = {
            "src/main.js": "const x = 1;\n",
        }
        issues = _check_import_resolution("src/main.js", files["src/main.js"], files)
        assert issues == []


# ── Duplicate Declarations ────────────────────────────────

class TestDuplicateDeclarations:
    def test_no_duplicates(self):
        code = "const a = 1;\nconst b = 2;\nfunction foo() {}\n"
        issues = _check_duplicate_declarations("test.js", code)
        assert issues == []

    def test_duplicate_const(self):
        code = "const x = 1;\nconst y = 2;\nconst x = 3;\n"
        issues = _check_duplicate_declarations("test.js", code)
        assert len(issues) == 1
        assert issues[0].rule == "duplicate_declaration"
        assert "x" in issues[0].message

    def test_duplicate_function(self):
        code = "function foo() {}\nfunction foo() {}\n"
        issues = _check_duplicate_declarations("test.js", code)
        assert len(issues) == 1

    def test_different_kinds_same_name(self):
        code = "const foo = 1;\nfunction foo() {}\n"
        issues = _check_duplicate_declarations("test.js", code)
        assert len(issues) == 1


# ── Syntax Basics ─────────────────────────────────────────

class TestSyntaxBasics:
    def test_clean_code(self):
        code = "const x = 1;\nif (x === 1) { return; }\n"
        issues = _check_syntax_basics("test.js", code)
        assert issues == []

    def test_double_semicolon(self):
        code = "const x = 1;;\n"
        issues = _check_syntax_basics("test.js", code)
        assert len(issues) == 1
        assert issues[0].rule == "double_semicolon"
        assert issues[0].severity == SEVERITY_WARNING

    def test_double_semicolon_in_for_loop_ok(self):
        code = "for (let i = 0;; i++) {}\n"
        issues = _check_syntax_basics("test.js", code)
        assert issues == []

    def test_assignment_in_condition(self):
        code = "if (x = 5) { doStuff(); }\n"
        issues = _check_syntax_basics("test.js", code)
        assert len(issues) == 1
        assert issues[0].rule == "assignment_in_condition"

    def test_equality_in_condition_ok(self):
        code = "if (x === 5) { doStuff(); }\n"
        issues = _check_syntax_basics("test.js", code)
        assert issues == []


# ── String/Comment Stripping ──────────────────────────────

class TestStripStringsAndComments:
    def test_strips_single_line_comment(self):
        result = _strip_strings_and_comments("const x = 1; // comment\n")
        assert "//" not in result
        assert "comment" not in result
        assert "const" in result

    def test_strips_multiline_comment(self):
        result = _strip_strings_and_comments("const x = /* { } */ 1;\n")
        assert "{" not in result or result.index("{") > result.index("x")

    def test_strips_string_contents(self):
        result = _strip_strings_and_comments('const x = "hello { world }";\n')
        assert "hello" not in result
        assert "const" in result

    def test_preserves_line_count(self):
        source = "line1\nline2\n/* multi\nline\ncomment */\nline6\n"
        result = _strip_strings_and_comments(source)
        assert result.count("\n") == source.count("\n")


# ── Full Gate Integration ─────────────────────────────────

class TestRunQualityGate:
    def test_clean_files_pass(self):
        files = {
            "src/main.js": "const x = 1;\nconsole.log(x);\n",
        }
        result = run_quality_gate(files)
        assert result.passed is True
        assert result.issues == []

    def test_error_files_fail(self):
        files = {
            "src/main.js": "function foo() {\n  return 1;\n",
        }
        result = run_quality_gate(files)
        assert result.passed is False
        assert len(result.blocking) >= 1

    def test_non_js_files_ignored(self):
        files = {
            "src/readme.md": "{ unclosed bracket",
            "src/data.json": '{ "key": "value"',
        }
        result = run_quality_gate(files)
        assert result.passed is True

    def test_to_developer_prompt_empty(self):
        result = GateResult(passed=True, issues=[])
        assert result.to_developer_prompt() == ""

    def test_to_developer_prompt_with_issues(self):
        result = GateResult(
            passed=False,
            issues=[
                GateIssue(
                    file="test.js", line=5, severity=SEVERITY_ERROR,
                    rule="bracket_balance", message="'{' nunca fechado",
                ),
            ],
        )
        prompt = result.to_developer_prompt()
        assert "Quality Gate" in prompt
        assert "test.js:5" in prompt
        assert "bracket_balance" in prompt
