"""
Smart Prompt Compression — Roadmap #6 + v3 Item #4

Reduces prompt sizes sent to LLM agents by 30-50% through:
1. Code pruning (comments, blank lines, whitespace)
2. History summarization (full detail for recent, summary for older)
3. GDD compression (collapse verbose sections)
4. Smart truncation (trim least-relevant tail)
5. [v3] Context Manager delegation for relevance-based selection
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# ── Regex patterns for JS comment removal ────────────
_SINGLE_LINE_COMMENT = re.compile(r"^\s*//.*$", re.MULTILINE)
_MULTI_LINE_COMMENT = re.compile(r"/\*[\s\S]*?\*/")
_CONSECUTIVE_BLANK_LINES = re.compile(r"\n{3,}")


def compress_code_context(
    files: dict[str, str],
    max_chars: int = 5000,  # Reduced from 8000 to save tokens
    context_manager: Any = None,
    task_description: str = "",
) -> dict[str, str]:
    """Remove comments, blank lines, and truncate large files.

    If a context_manager is provided along with a task_description,
    relevance-based selection is used to prioritize important files
    before compression (Roadmap v3 Item #4).

    Each file gets an equal share of max_chars.  Files that are
    smaller than their share leave room for others.

    Args:
        files: mapping of filename → source code content.
        max_chars: total character budget across all files.
        context_manager: optional ContextManager for relevance ranking.
        task_description: what the agent is working on (for relevance).

    Returns:
        Compressed version of the files dict.
    """
    if not files:
        return {}

    # v3 Item #4: Delegate to context manager if available
    if context_manager and task_description and hasattr(context_manager, 'select_context'):
        try:
            selected = context_manager.select_context(
                task_description=task_description,
                available_context=files,
                max_chars=max_chars,
            )
            if selected:
                files = selected
        except Exception:
            pass  # Fall through to standard compression

    per_file_budget = max_chars // len(files)
    compressed: dict[str, str] = {}
    saved_chars = 0

    for fname, content in files.items():
        original_len = len(content)

        # Strip single-line comments
        cleaned = _SINGLE_LINE_COMMENT.sub("", content)
        # Strip multi-line comments
        cleaned = _MULTI_LINE_COMMENT.sub("", cleaned)
        # Collapse blank lines
        cleaned = _CONSECUTIVE_BLANK_LINES.sub("\n\n", cleaned)
        # Remove leading/trailing whitespace per line, drop empty lines
        lines = [l.rstrip() for l in cleaned.split("\n") if l.strip()]
        cleaned = "\n".join(lines)

        # Truncate to per-file budget
        if len(cleaned) > per_file_budget:
            cleaned = cleaned[:per_file_budget] + "\n// ...[truncated]"

        compressed[fname] = cleaned
        saved_chars += original_len - len(cleaned)

    if saved_chars > 0:
        logger.debug(
            "📦 Code compression: %d files, saved %d chars (%.0f%%)",
            len(files), saved_chars,
            (saved_chars / sum(len(v) for v in files.values()) * 100) if files else 0,
        )

    return compressed


def summarize_history(
    history: list[Any],
    keep_last: int = 3,
) -> list[Any]:
    """Full detail for recent iterations, summary for older ones.

    Items in ``history`` can be dicts or objects with ``.score`` / ``.number``
    attributes (like IterationState).

    For items beyond ``keep_last``, only a compact summary string is kept.
    Recent items are returned unchanged.

    Args:
        history: list of iteration history entries.
        keep_last: number of recent entries to keep in full.

    Returns:
        list mixing summary strings (old) and original objects (recent).
    """
    if not history or keep_last <= 0:
        return list(history) if history else []

    if len(history) <= keep_last:
        return list(history)

    summarized: list[Any] = []

    # Older entries → compact one-liners
    for h in history[:-keep_last]:
        if isinstance(h, dict):
            score = h.get("score", h.get("composite", "?"))
            number = h.get("iteration", h.get("number", "?"))
            focus = str(h.get("focus", h.get("focus_area", "")))[:50]
        else:
            score = getattr(h, "score", "?")
            number = getattr(h, "number", getattr(h, "iteration", "?"))
            focus = ""
            if hasattr(h, "critic_feedback") and isinstance(h.critic_feedback, dict):
                focus = str(h.critic_feedback.get("focus_area", ""))[:50]

        summary = f"Iter {number}: score={score}"
        if focus:
            summary += f", focus={focus}"
        summarized.append(summary)

    # Recent entries → full detail
    summarized.extend(history[-keep_last:])

    logger.debug(
        "📦 History compression: %d → %d summarized + %d full",
        len(history), len(history) - keep_last, keep_last,
    )
    return summarized


def compress_gdd(
    gdd: dict[str, Any],
    max_chars: int = 2500,  # Reduced from 4000 to save tokens
) -> dict[str, Any]:
    """Compress GDD by collapsing verbose sections.

    Keeps top-level keys and their structure, but truncates long
    string values and serializes nested objects compactly.

    Args:
        gdd: the GDD update dict.
        max_chars: maximum total characters for the serialized output.

    Returns:
        A compressed copy of the GDD dict.
    """
    if not gdd:
        return {}

    compressed: dict[str, Any] = {}
    per_key_budget = max_chars // max(len(gdd), 1)

    for key, value in gdd.items():
        if isinstance(value, str):
            if len(value) > per_key_budget:
                compressed[key] = value[:per_key_budget] + "...[truncated]"
            else:
                compressed[key] = value
        elif isinstance(value, dict):
            serialized = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
            if len(serialized) > per_key_budget:
                if "," in serialized[:per_key_budget]:
                    try:
                        compressed[key] = json.loads(
                            serialized[:per_key_budget].rsplit(",", 1)[0] + "}"
                        )
                    except json.JSONDecodeError:
                        compressed[key] = str(value)[:per_key_budget] + "...[truncated]"
                else:
                    compressed[key] = str(value)[:per_key_budget] + "...[truncated]"
            else:
                compressed[key] = value
        elif isinstance(value, list):
            serialized = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
            if len(serialized) > per_key_budget:
                # Keep first items that fit
                result: list[Any] = []
                chars_used = 2  # for [ ]
                for item in value:
                    item_str = json.dumps(item, ensure_ascii=False, separators=(",", ":"))
                    if chars_used + len(item_str) + 1 > per_key_budget:
                        break
                    result.append(item)
                    chars_used += len(item_str) + 1
                compressed[key] = result
            else:
                compressed[key] = value
        else:
            compressed[key] = value

    return compressed


def smart_truncate(text: str, max_chars: int = 2000) -> str:
    """Truncate text from the tail if it exceeds max_chars.

    Adds a ``...[truncated N chars]`` marker when truncation occurs.

    Args:
        text: the input text to potentially truncate.
        max_chars: maximum allowed characters.

    Returns:
        The original text if within budget, or a truncated version.
    """
    if not text or len(text) <= max_chars:
        return text

    truncated_count = len(text) - max_chars
    marker = f"\n...[truncated {truncated_count} chars]"
    return text[: max_chars - len(marker)] + marker
