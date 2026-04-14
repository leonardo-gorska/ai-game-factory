"""
GORVAX GAME FACTORY — Model Hot-Swap Manager (Roadmap v2 Item 11)

Monitors `config/model_overrides.json` for runtime model changes.
When the file changes, it applies the new overrides to the LLMRouter
without requiring a pipeline restart.

File format:
{
  "developer": "sambanova",
  "designer": "openrouter",
  "critic": "gemini"
}
Keys are agent names, values are provider names.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from backend.llm.router import LLMRouter

logger = logging.getLogger(__name__)


class ModelManager:
    """Manages runtime model overrides via config file polling."""

    DEFAULT_CONFIG_PATH = Path("config/model_overrides.json")

    def __init__(
        self,
        config_path: Path | None = None,
    ) -> None:
        self._config_path = config_path or self.DEFAULT_CONFIG_PATH
        self._last_overrides: dict[str, str] = {}
        self._last_mtime: float = 0.0
        self._swap_count: int = 0

    def check_for_updates(self) -> dict[str, str] | None:
        """
        Check if the config file has been modified since last check.

        Returns:
            Dict of changed overrides (agent → provider), or None if
            no changes detected or file doesn't exist.
        """
        if not self._config_path.exists():
            return None

        try:
            mtime = self._config_path.stat().st_mtime
        except OSError:
            return None

        if mtime == self._last_mtime:
            return None

        self._last_mtime = mtime

        try:
            raw = self._config_path.read_text(encoding="utf-8").strip()
            if not raw:
                return None
            overrides = json.loads(raw)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning(
                "⚠️ ModelManager: invalid config file '%s': %s",
                self._config_path, exc,
            )
            return None

        if not isinstance(overrides, dict):
            logger.warning(
                "⚠️ ModelManager: config must be a JSON object, got %s",
                type(overrides).__name__,
            )
            return None

        # Filter to only valid string → string entries
        clean: dict[str, str] = {
            str(k): str(v)
            for k, v in overrides.items()
            if isinstance(k, str) and isinstance(v, str)
        }

        # Detect actual changes
        changed: dict[str, str] = {}
        for agent, provider in clean.items():
            if self._last_overrides.get(agent) != provider:
                changed[agent] = provider

        # Detect removals (agent was in last overrides but not in new config)
        for agent in list(self._last_overrides):
            if agent not in clean:
                changed[agent] = ""  # Empty string signals removal

        if not changed:
            return None

        self._last_overrides = clean.copy()

        logger.info(
            "🔄 ModelManager: detected %d override change(s): %s",
            len(changed), changed,
        )
        return changed

    def apply(
        self,
        router: LLMRouter,
        overrides: dict[str, str],
    ) -> int:
        """
        Apply runtime overrides to the LLM router.

        Args:
            router: The LLMRouter instance to update.
            overrides: Dict of agent → provider. Empty string removes override.

        Returns:
            Number of overrides actually applied.
        """
        applied = 0
        for agent, provider in overrides.items():
            try:
                if provider:
                    router.set_agent_override(agent, provider)
                    logger.info(
                        "🔄 Hot-swap: %s → %s",
                        agent, provider,
                    )
                else:
                    router.remove_agent_override(agent)
                    logger.info(
                        "🔄 Hot-swap: removed override for %s",
                        agent,
                    )
                applied += 1
            except Exception as exc:
                logger.warning(
                    "⚠️ Hot-swap failed for %s → %s: %s",
                    agent, provider, exc,
                )

        self._swap_count += applied
        return applied

    def get_current_overrides(self) -> dict[str, str]:
        """Return the currently active overrides."""
        return self._last_overrides.copy()

    def get_stats(self) -> dict[str, Any]:
        """Return statistics about model hot-swaps."""
        return {
            "config_path": str(self._config_path),
            "active_overrides": self._last_overrides.copy(),
            "total_swaps": self._swap_count,
        }
