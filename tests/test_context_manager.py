"""
Tests for ContextManager — Smart Context Window Manager (Roadmap v3 Item #4).
"""

import pytest

from backend.llm.context_manager import (
    ContextManager,
    ContextChunk,
    ContextStats,
    DEFAULT_MAX_CONTEXT_CHARS,
)


# ── ContextChunk ────────────────────────────────────────

class TestContextChunk:
    def test_creation(self):
        c = ContextChunk(key="test.js", content="function foo() {}")
        assert c.key == "test.js"
        assert c.char_count == len("function foo() {}")
        assert c.relevance == 0.0

    def test_char_count_auto_calculated(self):
        c = ContextChunk(key="x", content="hello world")
        assert c.char_count == 11

    def test_explicit_char_count(self):
        c = ContextChunk(key="x", content="abc", char_count=999)
        assert c.char_count == 999


# ── ContextManager — Basic ──────────────────────────────

class TestSelectContextBasic:
    def test_empty_context_returns_empty(self):
        cm = ContextManager()
        result = cm.select_context("task", {})
        assert result == {}

    def test_whitespace_only_context_filtered(self):
        cm = ContextManager()
        result = cm.select_context("task", {"a": "   ", "b": "\n\n"})
        assert result == {}

    def test_all_items_returned_when_fewer_than_top_k(self):
        cm = ContextManager()
        ctx = {"a.js": "function a() {}", "b.js": "function b() {}"}
        result = cm.select_context("fix function", ctx, top_k=5)
        assert len(result) == 2
        assert "a.js" in result
        assert "b.js" in result

    def test_single_item_context(self):
        cm = ContextManager()
        result = cm.select_context("task", {"file.js": "code here"})
        assert "file.js" in result


# ── ContextManager — Ranking ────────────────────────────

class TestSelectContextRanking:
    def test_relevant_items_ranked_higher(self):
        cm = ContextManager()
        ctx = {
            "combat.js": "function calculateDamage(attack, defense) { return attack - defense; }",
            "ui.js": "function renderMenu() { display.show('menu'); }",
            "inventory.js": "function addItem(item) { bag.push(item); }",
        }
        result = cm.select_context("fix damage calculation", ctx, top_k=1)
        assert len(result) == 1
        # combat.js should be ranked highest due to keyword overlap
        assert "combat.js" in result

    def test_top_k_limits_results(self):
        cm = ContextManager()
        ctx = {f"file{i}.js": f"function func{i}() {{ }}" for i in range(10)}
        result = cm.select_context("task description", ctx, top_k=3)
        assert len(result) <= 3


# ── ContextManager — Character Budget ──────────────────

class TestCharacterBudget:
    def test_respects_max_chars(self):
        cm = ContextManager(max_context_chars=100)
        ctx = {
            "a.js": "x" * 50,
            "b.js": "y" * 50,
            "c.js": "z" * 50,
        }
        result = cm.select_context("task", ctx)
        total_chars = sum(len(v) for v in result.values())
        assert total_chars <= 100

    def test_override_max_chars(self):
        cm = ContextManager(max_context_chars=10000)
        ctx = {"a.js": "x" * 200}
        result = cm.select_context("task", ctx, max_chars=50)
        # The content is truncated (shorter than original) even
        # though the truncation marker adds a few chars over budget
        assert len(result["a.js"]) < 200
        assert "truncated" in result["a.js"]

    def test_large_context_gets_truncated(self):
        cm = ContextManager(max_context_chars=30)
        ctx = {"big.js": "a" * 100}
        result = cm.select_context("task", ctx)
        # Content was cut; truncation marker is appended
        assert len(result["big.js"]) < 100
        assert "truncated" in result["big.js"]


# ── ContextManager — Compress with Relevance ───────────

class TestCompressWithRelevance:
    def test_combines_files_and_history(self):
        cm = ContextManager(max_context_chars=10000)
        result = cm.compress_with_relevance(
            task_description="fix bug",
            files={"main.js": "code here"},
            history=["iter 1: score=50", "iter 2: score=60"],
        )
        assert len(result) == 3  # 1 file + 2 history entries

    def test_files_only(self):
        cm = ContextManager(max_context_chars=10000)
        result = cm.compress_with_relevance(
            task_description="task",
            files={"a.js": "code1", "b.js": "code2"},
        )
        assert len(result) == 2

    def test_empty_files(self):
        cm = ContextManager()
        result = cm.compress_with_relevance("task", {})
        assert result == {}


# ── ContextManager — Stats ──────────────────────────────

class TestStats:
    def test_initial_stats(self):
        cm = ContextManager()
        stats = cm.get_stats()
        assert stats["total_chunks"] == 0
        assert stats["has_vector_store"] is False

    def test_stats_updated_after_selection(self):
        cm = ContextManager(max_context_chars=50)
        ctx = {
            "a.js": "x" * 30,
            "b.js": "y" * 30,
            "c.js": "z" * 30,
        }
        cm.select_context("task", ctx, top_k=2)
        stats = cm.get_stats()
        assert stats["total_chunks"] == 3
        assert stats["selected_chunks"] <= 2
        # total_chars_after may slightly exceed budget due to truncation marker
        assert stats["total_chars_after"] < stats["total_chars_before"]

    def test_compression_ratio(self):
        cm = ContextManager(max_context_chars=20)
        ctx = {"file.js": "x" * 100}
        cm.select_context("task", ctx)
        stats = cm.get_stats()
        assert stats["compression_ratio"] > 0


# ── ContextManager — Fallback (no VectorStore) ─────────

class TestFallbackMode:
    def test_works_without_vector_store(self):
        cm = ContextManager(vector_store=None)
        assert cm.has_vector_store is False
        ctx = {"a.js": "function combat() {}", "b.js": "function menu() {}"}
        result = cm.select_context("fix combat", ctx)
        assert len(result) > 0

    def test_keyword_ranking_produces_ordered_results(self):
        cm = ContextManager()
        ctx = {
            "combat.js": "attack defense damage health combat battle",
            "ui.js": "button menu render display screen layout",
            "audio.js": "sound music volume mute play stop",
        }
        result = cm.select_context("combat damage attack", ctx, top_k=1)
        # Should pick the file with most keyword overlap
        assert "combat.js" in result


# ── ContextManager — has_vector_store property ─────────

class TestHasVectorStore:
    def test_none_vector_store(self):
        cm = ContextManager(vector_store=None)
        assert cm.has_vector_store is False

    def test_unavailable_vector_store(self):
        class FakeStore:
            is_available = False
        cm = ContextManager(vector_store=FakeStore())
        assert cm.has_vector_store is False

    def test_available_vector_store(self):
        class FakeStore:
            is_available = True
        cm = ContextManager(vector_store=FakeStore())
        assert cm.has_vector_store is True
