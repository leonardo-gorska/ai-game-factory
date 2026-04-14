"""
GORVAX GAME FACTORY — Error Pattern Database

Persistent cross-session database of error patterns and their fixes.
When a build error is successfully fixed, the pattern is stored so that
future occurrences can be resolved without an LLM call.

Roadmap v3 Item #2.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Minimum similarity ratio for fuzzy match
_MATCH_THRESHOLD = 0.80

# Minimum success ratio before a pattern is pruned
_MIN_SUCCESS_RATIO = 0.30


@dataclass
class ErrorPattern:
    """A recorded error → fix mapping."""

    error_signature: str
    category: str
    fix_description: str
    fix_code: str = ""
    source_file: str = ""
    success_count: int = 0
    fail_count: int = 0
    last_seen: str = ""

    @property
    def total(self) -> int:
        return self.success_count + self.fail_count

    @property
    def success_ratio(self) -> float:
        if self.total == 0:
            return 0.0
        return self.success_count / self.total

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ErrorPattern:
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


class ErrorPatternDB:
    """JSON-backed persistent database of error → fix patterns.

    Usage::

        db = ErrorPatternDB(Path("data/error_patterns.json"))
        match = db.lookup("Cannot find module './Foo'", "import")
        if match:
            # Apply the known fix
            ...
        else:
            # Fall through to LLM
            ...

        # After a successful fix
        db.record_success(
            error_msg="Cannot find module './Foo'",
            category="import",
            fix_code="...",
            fix_description="Added missing import",
            file="src/main.js",
        )
        db.save()
    """

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path or Path("data/error_patterns.json")
        self._patterns: list[ErrorPattern] = []
        self._hits: int = 0
        self._misses: int = 0
        self._load()

    # ── Persistence ───────────────────────────────────────

    def _load(self) -> None:
        """Load patterns from JSON file."""
        if self._db_path.exists():
            try:
                raw = json.loads(self._db_path.read_text(encoding="utf-8"))
                self._patterns = [
                    ErrorPattern.from_dict(p) for p in raw.get("patterns", [])
                ]
                logger.info(
                    "📚 Error Pattern DB loaded: %d patterns from %s",
                    len(self._patterns), self._db_path,
                )
            except Exception as exc:
                logger.warning("Error loading pattern DB: %s", exc)
                self._patterns = []
        else:
            self._patterns = []

    def save(self) -> None:
        """Persist patterns to JSON file."""
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "version": 1,
            "patterns": [p.to_dict() for p in self._patterns],
        }
        self._db_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        logger.debug(
            "💾 Error Pattern DB saved: %d patterns to %s",
            len(self._patterns), self._db_path,
        )

    # ── Lookup ────────────────────────────────────────────

    def lookup(
        self, error_msg: str, category: str = "",
    ) -> ErrorPattern | None:
        """Find a known fix for an error message.

        Uses fuzzy matching (SequenceMatcher) with a threshold of 0.80.
        Category is used as a pre-filter if provided.

        Returns the best matching pattern, or None if no match found.
        """
        if not error_msg or not self._patterns:
            self._misses += 1
            return None

        # Normalize the error message
        normalized = self._normalize(error_msg)

        best_match: ErrorPattern | None = None
        best_ratio = 0.0

        for pattern in self._patterns:
            # Category pre-filter
            if category and pattern.category and pattern.category != category:
                continue

            # Skip patterns with low success ratio
            if pattern.total >= 3 and pattern.success_ratio < _MIN_SUCCESS_RATIO:
                continue

            ratio = SequenceMatcher(
                None,
                normalized,
                self._normalize(pattern.error_signature),
            ).ratio()

            if ratio >= _MATCH_THRESHOLD and ratio > best_ratio:
                best_ratio = ratio
                best_match = pattern

        if best_match:
            self._hits += 1
            logger.info(
                "📚 Error Pattern DB hit (%.0f%%): '%s' → '%s'",
                best_ratio * 100,
                error_msg[:80],
                best_match.fix_description[:80],
            )
            return best_match

        self._misses += 1
        return None

    # ── Recording ─────────────────────────────────────────

    def record_success(
        self,
        error_msg: str,
        category: str,
        fix_code: str = "",
        fix_description: str = "",
        file: str = "",
    ) -> None:
        """Record a successful error → fix mapping.

        If a similar pattern already exists, increment its success count.
        Otherwise, create a new pattern.
        """
        existing = self._find_exact_or_similar(error_msg, category)

        if existing:
            existing.success_count += 1
            existing.last_seen = self._timestamp()
            if fix_code and not existing.fix_code:
                existing.fix_code = fix_code
            if fix_description and not existing.fix_description:
                existing.fix_description = fix_description
        else:
            pattern = ErrorPattern(
                error_signature=error_msg,
                category=category,
                fix_code=fix_code,
                fix_description=fix_description,
                source_file=file,
                success_count=1,
                fail_count=0,
                last_seen=self._timestamp(),
            )
            self._patterns.append(pattern)

        self.save()

    def record_failure(
        self, error_msg: str, category: str = "",
    ) -> None:
        """Record a failed fix attempt.

        Increments the fail count.  If the success ratio drops below
        the minimum threshold (0.30) and we have enough data (>= 3),
        the pattern is pruned.
        """
        existing = self._find_exact_or_similar(error_msg, category)

        if existing:
            existing.fail_count += 1
            existing.last_seen = self._timestamp()

            # Prune unreliable patterns
            if existing.total >= 3 and existing.success_ratio < _MIN_SUCCESS_RATIO:
                self._patterns.remove(existing)
                logger.info(
                    "🗑️ Pruned unreliable pattern: '%s' (ratio=%.0f%%)",
                    existing.error_signature[:60],
                    existing.success_ratio * 100,
                )
            self.save()

    # ── Stats ─────────────────────────────────────────────

    def get_stats(self) -> dict[str, Any]:
        """Return DB statistics."""
        return {
            "total_patterns": len(self._patterns),
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": (
                self._hits / (self._hits + self._misses)
                if (self._hits + self._misses) > 0
                else 0.0
            ),
            "top_patterns": [
                {
                    "signature": p.error_signature[:80],
                    "success_count": p.success_count,
                    "ratio": round(p.success_ratio, 2),
                }
                for p in sorted(
                    self._patterns,
                    key=lambda p: p.success_count,
                    reverse=True,
                )[:5]
            ],
        }

    # ── Internal Helpers ──────────────────────────────────

    def _find_exact_or_similar(
        self, error_msg: str, category: str = "",
    ) -> ErrorPattern | None:
        """Find an existing pattern by exact or fuzzy match."""
        normalized = self._normalize(error_msg)

        for pattern in self._patterns:
            if category and pattern.category and pattern.category != category:
                continue
            if self._normalize(pattern.error_signature) == normalized:
                return pattern

        # Try fuzzy match
        for pattern in self._patterns:
            if category and pattern.category and pattern.category != category:
                continue
            ratio = SequenceMatcher(
                None, normalized, self._normalize(pattern.error_signature),
            ).ratio()
            if ratio >= _MATCH_THRESHOLD:
                return pattern

        return None

    @staticmethod
    def _normalize(msg: str) -> str:
        """Normalize error message for comparison.

        Strips file paths, line numbers, and excess whitespace.
        """
        import re
        # Remove file paths
        msg = re.sub(r"[A-Za-z]:[/\\]\S+", "<PATH>", msg)
        msg = re.sub(r"(?:src|game)[/\\]\S+\.js", "<FILE>", msg)
        # Remove line/col numbers
        msg = re.sub(r":\d+:\d+", "", msg)
        msg = re.sub(r"\(\d+,\s*\d+\)", "", msg)
        # Collapse whitespace
        msg = re.sub(r"\s+", " ", msg).strip()
        return msg

    @staticmethod
    def _timestamp() -> str:
        """ISO timestamp."""
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).isoformat()
