"""
GORVAX GAME FACTORY — Prompt Versioner (#17)
Tracks SHA-256 hashes of prompt templates to detect and log changes.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.config import PROMPTS_DIR

logger = logging.getLogger(__name__)

_VERSIONS_FILE = PROMPTS_DIR.parent / ".prompt_versions.json"


def get_prompt_hash(path: Path) -> str:
    """Return the first 12 chars of the SHA-256 hex digest of a file."""
    content = path.read_bytes()
    return hashlib.sha256(content).hexdigest()[:12]


def _load_versions() -> dict[str, Any]:
    """Load the existing prompt versions file, or return empty dict."""
    if _VERSIONS_FILE.exists():
        try:
            return json.loads(_VERSIONS_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_versions(data: dict[str, Any]) -> None:
    """Persist the prompt versions file."""
    _VERSIONS_FILE.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def check_and_log_changes() -> list[str]:
    """
    Compare current prompt hashes with stored versions.

    Returns:
        List of prompt names that changed (empty if none).
    """
    if not PROMPTS_DIR.exists():
        logger.warning("Prompts directory not found: %s", PROMPTS_DIR)
        return []

    versions = _load_versions()
    changed: list[str] = []
    now = datetime.now(timezone.utc).isoformat()

    for path in sorted(PROMPTS_DIR.iterdir()):
        if path.suffix not in (".md", ".txt"):
            continue

        name = path.stem
        current_hash = get_prompt_hash(path)
        stored = versions.get(name, {})

        if stored.get("hash") != current_hash:
            old_hash = stored.get("hash", "<new>")
            versions[name] = {
                "hash": current_hash,
                "updated_at": now,
                "previous_hash": old_hash if old_hash != "<new>" else None,
            }
            changed.append(name)
            logger.info(
                "📝 Prompt '%s' changed: %s → %s",
                name, old_hash, current_hash,
            )
        elif "hash" not in stored:
            # First time tracking this prompt
            versions[name] = {"hash": current_hash, "updated_at": now}
            changed.append(name)

    _save_versions(versions)

    if changed:
        logger.info("📝 #17: %d prompt(s) changed: %s", len(changed), ", ".join(changed))
    else:
        logger.debug("📝 #17: All prompts unchanged.")

    return changed
