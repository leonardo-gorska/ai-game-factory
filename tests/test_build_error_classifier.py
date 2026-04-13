"""
Tests for Build Error Classifier — diff_errors() and enhanced to_developer_prompt().

Covers:
- diff_errors() with various input combinations
- to_developer_prompt() with and without diff labels
"""

import pytest

from backend.core.build_error_classifier import (
    ClassifiedError,
    ClassificationResult,
    ErrorDiffResult,
    diff_errors,
)


# ── Helper factories ──────────────────────────────────

def _err(file: str = "src/Foo.js", line: int = 10, category: str = "import",
         message: str = "Cannot find module", fix_hint: str = "Fix it") -> ClassifiedError:
    return ClassifiedError(
        file=file, line=line, category=category,
        message=message, fix_hint=fix_hint,
    )


# ── diff_errors ───────────────────────────────────────

class TestDiffErrors:
    def test_empty_previous_all_new(self):
        """All current errors are 'new' when previous is empty."""
        current = [_err(line=1), _err(line=2)]
        result = diff_errors([], current)
        assert len(result.new) == 2
        assert len(result.persistent) == 0
        assert result.resolved_count == 0

    def test_same_errors_all_persistent(self):
        """When previous == current, all errors are persistent."""
        errors = [_err(line=1), _err(line=2)]
        result = diff_errors(errors, errors)
        assert len(result.new) == 0
        assert len(result.persistent) == 2
        assert result.resolved_count == 0

    def test_partial_overlap(self):
        """Mixed new, persistent, and resolved errors."""
        prev = [_err(line=1), _err(line=2), _err(line=3)]
        curr = [_err(line=2), _err(line=4)]
        result = diff_errors(prev, curr)
        assert len(result.new) == 1  # line=4
        assert result.new[0].line == 4
        assert len(result.persistent) == 1  # line=2
        assert result.persistent[0].line == 2
        assert result.resolved_count == 2  # lines 1 and 3

    def test_all_resolved(self):
        """Empty current means everything was resolved."""
        prev = [_err(line=1), _err(line=2)]
        result = diff_errors(prev, [])
        assert len(result.new) == 0
        assert len(result.persistent) == 0
        assert result.resolved_count == 2

    def test_both_empty(self):
        """No errors in either build."""
        result = diff_errors([], [])
        assert len(result.new) == 0
        assert len(result.persistent) == 0
        assert result.resolved_count == 0

    def test_different_categories_not_matched(self):
        """Same file+line but different category counts as new + resolved."""
        prev = [_err(line=10, category="import")]
        curr = [_err(line=10, category="syntax")]
        result = diff_errors(prev, curr)
        assert len(result.new) == 1
        assert len(result.persistent) == 0
        assert result.resolved_count == 1

    def test_different_files_not_matched(self):
        """Same line+category but different file counts as separate errors."""
        prev = [_err(file="src/A.js", line=10)]
        curr = [_err(file="src/B.js", line=10)]
        result = diff_errors(prev, curr)
        assert len(result.new) == 1
        assert len(result.persistent) == 0
        assert result.resolved_count == 1

    def test_returns_error_diff_result_type(self):
        """Return type is ErrorDiffResult."""
        result = diff_errors([], [])
        assert isinstance(result, ErrorDiffResult)


# ── to_developer_prompt with diff ─────────────────────

class TestToDeveloperPromptWithDiff:
    def test_without_diff_backward_compatible(self):
        """to_developer_prompt() without diff should NOT contain NOVO/PERSISTENTE labels."""
        cr = ClassificationResult(
            errors=[_err()],
            broken_files={"src/Foo.js"},
        )
        prompt = cr.to_developer_prompt()
        assert "[IMPORT]" in prompt
        assert "NOVO" not in prompt
        assert "PERSISTENTE" not in prompt

    def test_with_diff_labels_new(self):
        """New errors should be labeled with NOVO."""
        err = _err()
        cr = ClassificationResult(errors=[err], broken_files={"src/Foo.js"})
        diff = ErrorDiffResult(new=[err], persistent=[], resolved_count=0)
        prompt = cr.to_developer_prompt(diff=diff)
        assert "NOVO" in prompt
        assert "PERSISTENTE" not in prompt.split("###")[1]  # Only in error lines

    def test_with_diff_labels_persistent(self):
        """Persistent errors should be labeled with PERSISTENTE."""
        err = _err()
        cr = ClassificationResult(errors=[err], broken_files={"src/Foo.js"})
        diff = ErrorDiffResult(new=[], persistent=[err], resolved_count=0)
        prompt = cr.to_developer_prompt(diff=diff)
        assert "PERSISTENTE" in prompt

    def test_with_diff_resolved_count(self):
        """Prompt should show resolved count from diff."""
        err = _err()
        cr = ClassificationResult(errors=[err], broken_files={"src/Foo.js"})
        diff = ErrorDiffResult(new=[err], persistent=[], resolved_count=3)
        prompt = cr.to_developer_prompt(diff=diff)
        assert "Resolvidos: 3" in prompt

    def test_empty_errors_returns_empty(self):
        """No errors means empty prompt even with diff."""
        cr = ClassificationResult()
        diff = ErrorDiffResult(resolved_count=5)
        prompt = cr.to_developer_prompt(diff=diff)
        assert prompt == ""
