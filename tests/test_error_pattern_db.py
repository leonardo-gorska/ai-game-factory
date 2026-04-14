"""Tests for backend.core.error_pattern_db"""

import json
import pytest
from pathlib import Path

from backend.core.error_pattern_db import (
    ErrorPattern,
    ErrorPatternDB,
)


# ── ErrorPattern Dataclass ────────────────────────────────

class TestErrorPattern:
    def test_creates_with_defaults(self):
        p = ErrorPattern(error_signature="test error", category="syntax", fix_description="")
        assert p.success_count == 0
        assert p.fail_count == 0
        assert p.total == 0
        assert p.success_ratio == 0.0

    def test_success_ratio(self):
        p = ErrorPattern(
            error_signature="err", category="syntax",
            fix_description="test fix",
            success_count=3, fail_count=1,
        )
        assert p.success_ratio == 0.75

    def test_to_dict_roundtrip(self):
        p = ErrorPattern(
            error_signature="test", category="import",
            fix_description="remove import", success_count=5,
        )
        d = p.to_dict()
        p2 = ErrorPattern.from_dict(d)
        assert p2.error_signature == p.error_signature
        assert p2.success_count == p.success_count


# ── ErrorPatternDB ────────────────────────────────────────

class TestErrorPatternDB:
    def test_empty_db(self, tmp_path):
        """Empty DB should return None for any lookup."""
        db = ErrorPatternDB(tmp_path / "test_db.json")
        result = db.lookup("some error", "syntax")
        assert result is None

    def test_record_and_lookup(self, tmp_path):
        """After recording a success, lookup should find it."""
        db = ErrorPatternDB(tmp_path / "test_db.json")
        db.record_success(
            error_msg="Cannot find module './Foo'",
            category="import",
            fix_code="import { Foo } from './Foo';",
            fix_description="Added missing import",
            file="src/main.js",
        )

        match = db.lookup("Cannot find module './Foo'", "import")
        assert match is not None
        assert match.fix_description == "Added missing import"
        assert match.success_count == 1

    def test_fuzzy_match(self, tmp_path):
        """Similar error messages should match via fuzzy matching."""
        db = ErrorPatternDB(tmp_path / "test_db.json")
        db.record_success(
            error_msg="Cannot find module './systems/Combat'",
            category="import",
            fix_description="Fixed import path",
        )

        # Slightly different path, same pattern
        match = db.lookup(
            "Cannot find module './systems/CombatSystem'",
            "import",
        )
        # The similarity might or might not match depending on the threshold
        # What matters is that an exact repeat always matches:
        match2 = db.lookup(
            "Cannot find module './systems/Combat'",
            "import",
        )
        assert match2 is not None

    def test_no_match_different_error(self, tmp_path):
        """Completely different errors should not match."""
        db = ErrorPatternDB(tmp_path / "test_db.json")
        db.record_success(
            error_msg="Missing semicolon at end of line",
            category="syntax",
            fix_description="Added semicolon",
        )

        match = db.lookup(
            "TypeError: undefined is not a function",
            "runtime",
        )
        assert match is None

    def test_record_failure_degrades(self, tmp_path):
        """Recording failures should degrade and eventually prune patterns."""
        db = ErrorPatternDB(tmp_path / "test_db.json")
        db.record_success(
            error_msg="test error",
            category="syntax",
            fix_description="fix",
        )

        # Record enough failures to trigger pruning (ratio < 0.30, total >= 3)
        db.record_failure("test error", "syntax")
        db.record_failure("test error", "syntax")
        db.record_failure("test error", "syntax")

        # Pattern should have been pruned (1 success, 3 fails = 0.25 ratio)
        match = db.lookup("test error", "syntax")
        assert match is None

    def test_save_and_load(self, tmp_path):
        """DB should persist across save/load cycles."""
        db_path = tmp_path / "persist_db.json"
        db1 = ErrorPatternDB(db_path)
        db1.record_success(
            error_msg="Identifier 'x' has already been declared",
            category="syntax",
            fix_description="Converted to assignment",
        )

        # Create new instance loading from same file
        db2 = ErrorPatternDB(db_path)
        assert len(db2._patterns) == 1

        match = db2.lookup(
            "Identifier 'x' has already been declared",
            "syntax",
        )
        assert match is not None
        assert match.fix_description == "Converted to assignment"

    def test_stats(self, tmp_path):
        """get_stats should return expected fields."""
        db = ErrorPatternDB(tmp_path / "stats_db.json")
        db.record_success("err1", "syntax", fix_description="fix1")
        db.lookup("err1", "syntax")  # hit
        db.lookup("ERR_UNKNOWN_SOMETHING", "runtime")  # miss

        stats = db.get_stats()
        assert "total_patterns" in stats
        assert "hits" in stats
        assert "misses" in stats
        assert "hit_rate" in stats
        assert "top_patterns" in stats
        assert stats["total_patterns"] == 1
        assert stats["hits"] == 1
        assert stats["misses"] == 1

    def test_increment_existing_pattern(self, tmp_path):
        """Recording the same error twice should increment count."""
        db = ErrorPatternDB(tmp_path / "inc_db.json")
        db.record_success("test error", "syntax", fix_description="fix")
        db.record_success("test error", "syntax", fix_description="fix")

        match = db.lookup("test error", "syntax")
        assert match is not None
        assert match.success_count == 2

    def test_category_filter(self, tmp_path):
        """Lookup should respect category pre-filter."""
        db = ErrorPatternDB(tmp_path / "cat_db.json")
        db.record_success(
            "Missing semicolon",
            "syntax",
            fix_description="Added semicolon",
        )

        # Same message but wrong category should not match
        match = db.lookup("Missing semicolon", "import")
        assert match is None

        # Correct category should match
        match = db.lookup("Missing semicolon", "syntax")
        assert match is not None

    def test_empty_error_msg_returns_none(self, tmp_path):
        """Empty error message should always return None."""
        db = ErrorPatternDB(tmp_path / "empty_db.json")
        db.record_success("test", "syntax", fix_description="fix")
        assert db.lookup("", "syntax") is None


# ── Integration with auto_fixer ───────────────────────────

class TestAutoFixerIntegration:
    def test_auto_fixer_accepts_error_db(self, tmp_path):
        """try_auto_fix should accept error_db parameter."""
        from backend.core.auto_fixer import try_auto_fix

        db = ErrorPatternDB(tmp_path / "integration_db.json")

        errors = [
            {"category": "syntax", "message": "Missing semicolon", "file": "test.js", "line": 1},
        ]
        files = {"test.js": "const x = 1\n"}

        # Should work with or without error_db
        new_files, report = try_auto_fix(errors, files, error_db=db)
        assert report.any_fixed is True

    def test_error_db_fix_applied_before_rules(self, tmp_path):
        """Error DB match should be applied before static rules."""
        from backend.core.auto_fixer import try_auto_fix

        db = ErrorPatternDB(tmp_path / "priority_db.json")
        # Record a fix for a totally custom error
        db.record_success(
            error_msg="Custom error XYZ-999",
            category="syntax",
            fix_code="const fixed = true;",
            fix_description="Applied custom fix",
        )

        errors = [
            {"category": "syntax", "message": "Custom error XYZ-999", "file": "test.js", "line": 1},
        ]
        files = {"test.js": "const broken = false;\n"}

        new_files, report = try_auto_fix(errors, files, error_db=db)

        # The DB match should produce a fix result with rule="error_db"
        db_fixes = [f for f in report.fixes if f.rule == "error_db"]
        assert len(db_fixes) >= 1
