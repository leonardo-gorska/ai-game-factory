"""
Unit tests for backend.core.prompt_compressor.

Covers all four compression functions:
  - compress_code_context
  - summarize_history
  - compress_gdd
  - smart_truncate
"""

import pytest

from backend.core.prompt_compressor import (
    compress_code_context,
    compress_gdd,
    smart_truncate,
    summarize_history,
)


# ── compress_code_context ────────────────────────────────────────────────


class TestCompressCodeContext:
    def test_empty_input(self):
        assert compress_code_context({}) == {}

    def test_strips_single_line_comments(self):
        files = {"main.js": "// this is a comment\nconst x = 1;\n// another comment\nconst y = 2;"}
        result = compress_code_context(files)
        assert "//" not in result["main.js"]
        assert "const x = 1;" in result["main.js"]
        assert "const y = 2;" in result["main.js"]

    def test_strips_multiline_comments(self):
        files = {"app.js": "/* block\n   comment */\nlet a = 5;"}
        result = compress_code_context(files)
        assert "block" not in result["app.js"]
        assert "let a = 5;" in result["app.js"]

    def test_collapses_blank_lines(self):
        files = {"a.js": "x = 1\n\n\n\n\ny = 2"}
        result = compress_code_context(files)
        # Should not have more than one newline between lines
        assert "\n\n\n" not in result["a.js"]

    def test_truncates_large_files(self):
        # Each file gets max_chars // len(files) budget
        files = {"big.js": "a" * 5000}
        result = compress_code_context(files, max_chars=100)
        assert len(result["big.js"]) <= 120  # 100 + marker

    def test_preserves_code_structure(self):
        code = "function hello() {\n  return 'world';\n}\n"
        files = {"mod.js": code}
        result = compress_code_context(files, max_chars=5000)
        assert "function hello()" in result["mod.js"]
        assert "return 'world'" in result["mod.js"]

    def test_multiple_files_share_budget(self):
        files = {"a.js": "x" * 3000, "b.js": "y" * 3000}
        result = compress_code_context(files, max_chars=200)
        # Each gets 100 chars max
        assert len(result["a.js"]) <= 120
        assert len(result["b.js"]) <= 120


# ── summarize_history ────────────────────────────────────────────────────


class TestSummarizeHistory:
    def test_empty_list(self):
        assert summarize_history([]) == []

    def test_short_history_unchanged(self):
        history = [{"score": 70}, {"score": 80}]
        result = summarize_history(history, keep_last=3)
        assert len(result) == 2
        # All items should be original dicts
        assert all(isinstance(h, dict) for h in result)

    def test_older_items_summarized(self):
        history = [
            {"score": 50, "iteration": 1, "focus": "stability"},
            {"score": 60, "iteration": 2, "focus": "balance"},
            {"score": 70, "iteration": 3, "focus": "fun"},
            {"score": 80, "iteration": 4, "focus": "novelty"},
            {"score": 90, "iteration": 5, "focus": "performance"},
        ]
        result = summarize_history(history, keep_last=2)
        # First 3 should be summary strings
        assert all(isinstance(r, str) for r in result[:3])
        # Last 2 should be original dicts
        assert all(isinstance(r, dict) for r in result[3:])
        assert "Iter 1" in result[0]
        assert "score=50" in result[0]

    def test_keep_last_equals_length(self):
        history = [{"score": 1}, {"score": 2}, {"score": 3}]
        result = summarize_history(history, keep_last=3)
        assert len(result) == 3
        assert all(isinstance(r, dict) for r in result)

    def test_summary_includes_focus(self):
        history = [
            {"score": 50, "iteration": 1, "focus_area": "balance"},
            {"score": 90, "iteration": 2},
        ]
        result = summarize_history(history, keep_last=1)
        assert "focus=balance" in result[0]

    def test_dict_with_composite_key(self):
        history = [
            {"composite": 65, "number": 1},
            {"composite": 85, "number": 2},
        ]
        result = summarize_history(history, keep_last=1)
        assert "score=65" in result[0]
        assert "Iter 1" in result[0]


# ── compress_gdd ─────────────────────────────────────────────────────────


class TestCompressGDD:
    def test_empty_gdd(self):
        assert compress_gdd({}) == {}

    def test_short_values_unchanged(self):
        gdd = {"title": "My Game", "genre": "RPG"}
        result = compress_gdd(gdd, max_chars=5000)
        assert result == gdd

    def test_long_string_truncated(self):
        gdd = {"description": "x" * 10000}
        result = compress_gdd(gdd, max_chars=500)
        assert len(result["description"]) < 10000
        assert "truncated" in result["description"]

    def test_preserves_structure(self):
        gdd = {
            "title": "Game",
            "mechanics": {"combat": "turn-based", "crafting": "simple"},
        }
        result = compress_gdd(gdd, max_chars=10000)
        assert result["title"] == "Game"
        assert result["mechanics"]["combat"] == "turn-based"

    def test_list_values_trimmed(self):
        gdd = {"features": [f"feature_{i}" for i in range(100)]}
        result = compress_gdd(gdd, max_chars=200)
        assert len(result["features"]) < 100


# ── smart_truncate ───────────────────────────────────────────────────────


class TestSmartTruncate:
    def test_no_truncation_needed(self):
        text = "short text"
        assert smart_truncate(text, max_chars=100) == text

    def test_empty_string(self):
        assert smart_truncate("", max_chars=100) == ""

    def test_none_input(self):
        assert smart_truncate(None, max_chars=100) is None

    def test_truncates_long_text(self):
        text = "a" * 5000
        result = smart_truncate(text, max_chars=100)
        assert len(result) <= 100
        assert "truncated" in result

    def test_truncation_marker_shows_count(self):
        text = "a" * 200
        result = smart_truncate(text, max_chars=100)
        assert "truncated" in result
        # The marker should mention how many chars were removed
        assert "100" in result  # ~100 chars truncated

    def test_exactly_at_limit(self):
        text = "x" * 100
        assert smart_truncate(text, max_chars=100) == text

    def test_one_over_limit(self):
        text = "x" * 101
        result = smart_truncate(text, max_chars=100)
        assert "truncated" in result
