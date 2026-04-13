"""Unit tests for PipelineJournal (Roadmap v3 Item #12)."""

from __future__ import annotations

import json
import pytest
from pathlib import Path
from backend.core.pipeline_journal import (
    PipelineJournal,
    StepEntry,
    IterationEntry,
)


# ── Fixtures ──────────────────────────────────────────


@pytest.fixture
def journal() -> PipelineJournal:
    """In-memory journal (no persistence)."""
    return PipelineJournal(journal_dir=None, enabled=True)


@pytest.fixture
def journal_with_data(journal: PipelineJournal) -> PipelineJournal:
    """Journal with 2 iterations already recorded."""
    journal.start_iteration(1)
    journal.record_step("research", {"topic": "platformer"}, {"ideas": 3})
    journal.record_step("design", {"gdd": "v1"}, {"gdd": "v2"})
    journal.record_step("develop", {"files": 3}, {"files": 5})
    journal.end_iteration(1, final_score=55.0)

    journal.start_iteration(2)
    journal.record_step("research", {"topic": "enemies"}, {"ideas": 2})
    journal.record_step("design", {"gdd": "v2"}, {"gdd": "v3"})
    journal.record_step("develop", {"files": 5}, {"files": 7})
    journal.record_step("test", {"suite": "unit"}, {"passed": 10, "failed": 1})
    journal.end_iteration(2, final_score=68.0)

    return journal


@pytest.fixture
def journal_on_disk(tmp_path: Path) -> PipelineJournal:
    """Journal with disk persistence."""
    return PipelineJournal(journal_dir=tmp_path / "journal", enabled=True)


# ── StepEntry & IterationEntry ────────────────────────


class TestStepEntry:
    def test_defaults(self):
        s = StepEntry(step_name="test")
        assert s.step_name == "test"
        assert s.input_summary == {}
        assert s.output_summary == {}
        assert s.prompt == ""
        assert s.response == ""
        assert s.timestamp > 0

    def test_with_data(self):
        s = StepEntry(
            step_name="develop",
            prompt="Write code",
            response="Here's code",
            duration_ms=150.0,
        )
        assert s.prompt == "Write code"
        assert s.duration_ms == 150.0


class TestIterationEntry:
    def test_defaults(self):
        e = IterationEntry(iteration=1)
        assert e.iteration == 1
        assert e.steps == []
        assert e.final_score == 0.0
        assert e.step_count == 0

    def test_duration(self):
        e = IterationEntry(iteration=1, start_time=100.0, end_time=105.0)
        assert e.duration_ms == pytest.approx(5000.0)

    def test_to_dict(self):
        e = IterationEntry(iteration=1, final_score=72.0, start_time=100.0, end_time=105.0)
        e.steps.append(StepEntry(step_name="test"))
        d = e.to_dict()
        assert d["iteration"] == 1
        assert d["final_score"] == 72.0
        assert d["step_count"] == 1
        assert len(d["steps"]) == 1


# ── PipelineJournal Basic ─────────────────────────────


class TestJournalBasic:
    def test_enabled_default(self, journal: PipelineJournal):
        assert journal.enabled is True

    def test_toggle_enabled(self, journal: PipelineJournal):
        journal.enabled = False
        assert journal.enabled is False
        journal.enabled = True
        assert journal.enabled is True

    def test_disabled_no_recording(self):
        j = PipelineJournal(enabled=False)
        j.start_iteration(1)
        j.record_step("test", {"a": 1}, {"b": 2})
        j.end_iteration(1, final_score=50.0)
        assert j.total_iterations == 0

    def test_total_iterations(self, journal_with_data: PipelineJournal):
        assert journal_with_data.total_iterations == 2


# ── Recording ─────────────────────────────────────────


class TestRecording:
    def test_start_end(self, journal: PipelineJournal):
        journal.start_iteration(1)
        journal.record_step("step1", {"in": 1}, {"out": 1})
        journal.end_iteration(1, final_score=50.0)
        assert journal.total_iterations == 1

    def test_multiple_steps(self, journal: PipelineJournal):
        journal.start_iteration(1)
        journal.record_step("a", {}, {})
        journal.record_step("b", {}, {})
        journal.record_step("c", {}, {})
        journal.end_iteration(1, final_score=60.0)
        entry = journal.get_iteration(1)
        assert entry is not None
        assert entry.step_count == 3

    def test_record_llm_call(self, journal: PipelineJournal):
        journal.start_iteration(1)
        journal.record_llm_call("developer", "Write code", "Here's code", 150.0)
        journal.end_iteration(1, final_score=55.0)
        entry = journal.get_iteration(1)
        assert entry is not None
        assert entry.step_count == 1
        assert entry.steps[0].step_name == "llm:developer"
        assert entry.steps[0].prompt == "Write code"

    def test_prompt_truncation(self, journal: PipelineJournal):
        journal._max_prompt_chars = 10
        journal.start_iteration(1)
        journal.record_step("test", prompt="A" * 100, response="B" * 100)
        journal.end_iteration(1)
        entry = journal.get_iteration(1)
        assert entry is not None
        assert len(entry.steps[0].prompt) == 10

    def test_end_with_metadata(self, journal: PipelineJournal):
        journal.start_iteration(1)
        journal.end_iteration(1, final_score=70.0, metadata={"build": True})
        entry = journal.get_iteration(1)
        assert entry is not None
        assert entry.metadata["build"] is True

    def test_no_current_step_ignored(self, journal: PipelineJournal):
        # recording without start_iteration should be silently ignored
        journal.record_step("test", {}, {})
        assert journal.total_iterations == 0


# ── Replay ────────────────────────────────────────────


class TestReplay:
    def test_replay_existing(self, journal_with_data: PipelineJournal):
        result = journal_with_data.replay(1)
        assert result["iteration"] == 1
        assert result["final_score"] == 55.0
        assert "steps" in result
        assert "research" in result["steps"]

    def test_replay_nonexistent(self, journal_with_data: PipelineJournal):
        result = journal_with_data.replay(999)
        assert "error" in result

    def test_list_iterations(self, journal_with_data: PipelineJournal):
        iters = journal_with_data.list_iterations()
        assert len(iters) == 2
        assert iters[0]["iteration"] == 1
        assert iters[1]["iteration"] == 2
        assert iters[1]["final_score"] == 68.0


# ── Stats ─────────────────────────────────────────────


class TestJournalStats:
    def test_stats_structure(self, journal_with_data: PipelineJournal):
        stats = journal_with_data.get_stats()
        assert stats["enabled"] is True
        assert stats["total_iterations"] == 2
        assert stats["total_steps"] == 7  # 3 + 4
        assert stats["has_persistence"] is False

    def test_empty_stats(self, journal: PipelineJournal):
        stats = journal.get_stats()
        assert stats["total_iterations"] == 0
        assert stats["total_steps"] == 0


# ── Persistence ───────────────────────────────────────


class TestPersistence:
    def test_save_and_load(self, journal_on_disk: PipelineJournal, tmp_path: Path):
        journal_on_disk.start_iteration(1)
        journal_on_disk.record_step("develop", {"files": 3}, {"files": 5})
        journal_on_disk.end_iteration(1, final_score=60.0)

        # Check file was created
        journal_dir = tmp_path / "journal"
        assert (journal_dir / "iteration_0001.json").exists()
        assert (journal_dir / "index.json").exists()

        # Load in a new journal instance
        journal2 = PipelineJournal(journal_dir=journal_dir)
        entry = journal2.get_iteration(1)
        assert entry is not None
        assert entry.final_score == 60.0
        assert entry.step_count == 1

    def test_index_file(self, journal_on_disk: PipelineJournal, tmp_path: Path):
        journal_on_disk.start_iteration(1)
        journal_on_disk.end_iteration(1, final_score=50.0)
        journal_on_disk.start_iteration(2)
        journal_on_disk.end_iteration(2, final_score=60.0)

        index_path = tmp_path / "journal" / "index.json"
        assert index_path.exists()
        index = json.loads(index_path.read_text())
        assert index["iterations"] == [1, 2]
        assert index["total"] == 2


# ── Summarizer ────────────────────────────────────────


class TestSummarize:
    def test_summarize_strings(self):
        data = {"short": "hello", "long": "x" * 1000}
        summary = PipelineJournal._summarize(data, max_str_len=50)
        assert summary["short"] == "hello"
        assert len(summary["long"]) == 50

    def test_summarize_types(self):
        data = {
            "num": 42,
            "flag": True,
            "items": [1, 2, 3],
            "nested": {"a": 1},
            "_private": "skip",
        }
        summary = PipelineJournal._summarize(data)
        assert summary["num"] == 42
        assert summary["flag"] is True
        assert "[list: 3 items]" in summary["items"]
        assert "[dict: 1 keys]" in summary["nested"]
        assert "_private" not in summary
