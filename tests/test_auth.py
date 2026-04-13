"""
Tests for API Key Authentication — auth.py
"""

import hashlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.api.auth import _hash_key, validate_api_key, EXEMPT_PATHS


# ── Hash Function ────────────────────────────────────

class TestHashKey:
    def test_returns_hex_string(self):
        """_hash_key should return a 64-character hex SHA-256 digest."""
        result = _hash_key("test-key-123")
        assert isinstance(result, str)
        assert len(result) == 64
        # Verify it's valid hex
        int(result, 16)

    def test_deterministic(self):
        """Same input should always produce the same hash."""
        assert _hash_key("my-secret") == _hash_key("my-secret")

    def test_different_keys_different_hashes(self):
        """Different inputs should produce different hashes."""
        assert _hash_key("key-a") != _hash_key("key-b")

    def test_matches_hashlib(self):
        """Output should match direct hashlib computation."""
        key = "gorvax-factory-key"
        expected = hashlib.sha256(key.encode()).hexdigest()
        assert _hash_key(key) == expected


# ── Key Validation ───────────────────────────────────

class TestValidateApiKey:
    def test_accepts_valid_key(self):
        """Should return True when the provided key's hash matches."""
        with patch("backend.api.auth.API_KEY_HASH", _hash_key("correct-key")):
            assert validate_api_key("correct-key") is True

    def test_rejects_invalid_key(self):
        """Should return False when the provided key's hash doesn't match."""
        with patch("backend.api.auth.API_KEY_HASH", _hash_key("correct-key")):
            assert validate_api_key("wrong-key") is False

    def test_rejects_none(self):
        """Should return False when no key is provided."""
        with patch("backend.api.auth.API_KEY_HASH", _hash_key("some-key")):
            assert validate_api_key(None) is False

    def test_rejects_empty_string(self):
        """Should return False when an empty string is provided."""
        with patch("backend.api.auth.API_KEY_HASH", _hash_key("some-key")):
            assert validate_api_key("") is False

    def test_open_access_when_no_hash(self):
        """Should return True when API_KEY_HASH is empty (dev fallback)."""
        with patch("backend.api.auth.API_KEY_HASH", ""):
            assert validate_api_key(None) is True
            assert validate_api_key("anything") is True


# ── Exempt Paths ─────────────────────────────────────

class TestExemptPaths:
    def test_docs_exempt(self):
        assert "/docs" in EXEMPT_PATHS

    def test_ws_exempt(self):
        assert "/ws" in EXEMPT_PATHS

    def test_game_exempt(self):
        assert "/game" in EXEMPT_PATHS


# ── WebSocket Token Validation ───────────────────────

class TestValidateWsToken:
    @pytest.mark.asyncio
    async def test_valid_ws_token(self):
        """Should return True for a valid WebSocket token."""
        from backend.api.auth import validate_ws_token

        ws = MagicMock()
        ws.query_params = {"token": "valid-key"}
        with patch("backend.api.auth.API_KEY_HASH", _hash_key("valid-key")):
            result = await validate_ws_token(ws)
            assert result is True

    @pytest.mark.asyncio
    async def test_invalid_ws_token(self):
        """Should return False for an invalid WebSocket token."""
        from backend.api.auth import validate_ws_token

        ws = MagicMock()
        ws.query_params = {"token": "bad-key"}
        with patch("backend.api.auth.API_KEY_HASH", _hash_key("correct-key")):
            result = await validate_ws_token(ws)
            assert result is False

    @pytest.mark.asyncio
    async def test_missing_ws_token(self):
        """Should return False when no token query param is present."""
        from backend.api.auth import validate_ws_token

        ws = MagicMock()
        ws.query_params = {}
        with patch("backend.api.auth.API_KEY_HASH", _hash_key("some-key")):
            result = await validate_ws_token(ws)
            assert result is False
