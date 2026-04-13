"""Tests for backend.llm.model_manager — Hot-Swap de Modelo (Roadmap v2 Item 11)"""

import json
import os
import tempfile
from pathlib import Path

import pytest

from backend.llm.model_manager import ModelManager


class TestModelManagerCheckForUpdates:
    """Tests for ModelManager.check_for_updates()."""

    def _write_config(self, path: Path, data: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")

    def test_returns_none_when_file_missing(self, tmp_path):
        mgr = ModelManager(config_path=tmp_path / "nonexistent.json")
        assert mgr.check_for_updates() is None

    def test_returns_overrides_on_first_read(self, tmp_path):
        cfg = tmp_path / "overrides.json"
        self._write_config(cfg, {"developer": "sambanova", "critic": "gemini"})
        mgr = ModelManager(config_path=cfg)
        result = mgr.check_for_updates()
        assert result == {"developer": "sambanova", "critic": "gemini"}

    def test_returns_none_when_unchanged(self, tmp_path):
        cfg = tmp_path / "overrides.json"
        self._write_config(cfg, {"developer": "sambanova"})
        mgr = ModelManager(config_path=cfg)
        mgr.check_for_updates()  # First read
        assert mgr.check_for_updates() is None  # No change

    def test_detects_value_change(self, tmp_path):
        cfg = tmp_path / "overrides.json"
        self._write_config(cfg, {"developer": "sambanova"})
        mgr = ModelManager(config_path=cfg)
        mgr.check_for_updates()  # First read

        # Modify — need to force mtime change
        import time; time.sleep(0.05)
        self._write_config(cfg, {"developer": "openrouter"})
        result = mgr.check_for_updates()
        assert result == {"developer": "openrouter"}

    def test_detects_removal(self, tmp_path):
        cfg = tmp_path / "overrides.json"
        self._write_config(cfg, {"developer": "sambanova", "critic": "gemini"})
        mgr = ModelManager(config_path=cfg)
        mgr.check_for_updates()  # First read

        import time; time.sleep(0.05)
        self._write_config(cfg, {"developer": "sambanova"})  # Remove critic
        result = mgr.check_for_updates()
        assert result is not None
        assert result.get("critic") == ""  # Empty = removal

    def test_handles_invalid_json(self, tmp_path):
        cfg = tmp_path / "overrides.json"
        cfg.parent.mkdir(parents=True, exist_ok=True)
        cfg.write_text("not json{{{", encoding="utf-8")
        mgr = ModelManager(config_path=cfg)
        assert mgr.check_for_updates() is None

    def test_handles_non_dict_json(self, tmp_path):
        cfg = tmp_path / "overrides.json"
        cfg.parent.mkdir(parents=True, exist_ok=True)
        cfg.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
        mgr = ModelManager(config_path=cfg)
        assert mgr.check_for_updates() is None

    def test_handles_empty_file(self, tmp_path):
        cfg = tmp_path / "overrides.json"
        cfg.parent.mkdir(parents=True, exist_ok=True)
        cfg.write_text("", encoding="utf-8")
        mgr = ModelManager(config_path=cfg)
        assert mgr.check_for_updates() is None


class TestModelManagerApply:
    """Tests for ModelManager.apply()."""

    def test_apply_sets_overrides(self):
        """apply() should call set_agent_override on the router."""
        class FakeRouter:
            def __init__(self):
                self.overrides = {}
            def set_agent_override(self, agent, provider):
                self.overrides[agent] = provider
            def remove_agent_override(self, agent):
                self.overrides.pop(agent, None)

        mgr = ModelManager()
        router = FakeRouter()
        applied = mgr.apply(router, {"developer": "sambanova", "critic": "gemini"})
        assert applied == 2
        assert router.overrides == {"developer": "sambanova", "critic": "gemini"}

    def test_apply_removes_empty_overrides(self):
        """Empty string in overrides should remove the agent override."""
        class FakeRouter:
            def __init__(self):
                self.overrides = {"developer": "sambanova"}
            def set_agent_override(self, agent, provider):
                self.overrides[agent] = provider
            def remove_agent_override(self, agent):
                self.overrides.pop(agent, None)

        mgr = ModelManager()
        router = FakeRouter()
        applied = mgr.apply(router, {"developer": ""})
        assert applied == 1
        assert "developer" not in router.overrides

    def test_apply_handles_errors(self):
        """Apply should not crash on router errors."""
        class BrokenRouter:
            def set_agent_override(self, agent, provider):
                raise RuntimeError("test error")
            def remove_agent_override(self, agent):
                raise RuntimeError("test error")

        mgr = ModelManager()
        applied = mgr.apply(BrokenRouter(), {"developer": "sambanova"})
        assert applied == 0


class TestModelManagerStats:
    """Tests for ModelManager stats and state."""

    def test_get_current_overrides_empty(self):
        mgr = ModelManager()
        assert mgr.get_current_overrides() == {}

    def test_get_current_overrides_after_read(self, tmp_path):
        cfg = tmp_path / "overrides.json"
        cfg.parent.mkdir(parents=True, exist_ok=True)
        cfg.write_text(json.dumps({"developer": "sambanova"}), encoding="utf-8")
        mgr = ModelManager(config_path=cfg)
        mgr.check_for_updates()
        assert mgr.get_current_overrides() == {"developer": "sambanova"}

    def test_get_stats(self):
        mgr = ModelManager()
        stats = mgr.get_stats()
        assert "total_swaps" in stats
        assert stats["total_swaps"] == 0
        assert "active_overrides" in stats
