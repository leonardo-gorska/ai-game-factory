"""
Tests for API Server endpoints — server.py
Uses httpx.AsyncClient to test FastAPI endpoints.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.api.server import create_app


# ── Fixtures ─────────────────────────────────────────

@pytest.fixture
def mock_pipeline():
    """Create a mock Pipeline for endpoint tests."""
    pipeline = MagicMock()
    pipeline.state = MagicMock()
    pipeline.state.is_running = False
    pipeline.state.is_paused = False
    pipeline.state.current_iteration = 0
    pipeline.state.best_score = 0
    pipeline.state.total_iterations = 0
    pipeline.state.to_dict.return_value = {
        "is_running": False,
        "is_paused": False,
        "current_iteration": 0,
        "best_score": 0,
        "total_iterations": 0,
    }
    pipeline.cost_guard = MagicMock()
    pipeline.cost_guard.get_stats.return_value = {"total_cost_usd": 0.0}
    pipeline.llm_router = MagicMock()
    pipeline.llm_router.available_providers = ["mock"]
    pipeline.llm_router.get_routing_info.return_value = {}
    pipeline.experiment_tracker = MagicMock()
    pipeline.experiment_tracker.get_experiments.return_value = []
    pipeline.exploration_controller = MagicMock()
    pipeline.exploration_controller.get_stats.return_value = {}
    pipeline._last_heatmap = {}
    pipeline.start = AsyncMock()
    pipeline.stop = AsyncMock()
    pipeline.pause = AsyncMock()
    pipeline.resume = AsyncMock()

    # Health endpoint calls pipeline.watchdog.get_health().to_dict()
    health_mock = MagicMock()
    health_mock.to_dict.return_value = {"status": "ok", "alerts": []}
    pipeline.watchdog = MagicMock()
    pipeline.watchdog.get_health.return_value = health_mock

    # Quality trend
    pipeline.quality_engine = MagicMock()
    pipeline.quality_engine.get_trend.return_value = []

    return pipeline


@pytest.fixture
def app(mock_pipeline):
    """Create a FastAPI app with mocked pipeline and auth bypassed."""
    with patch("backend.api.server._pipeline", mock_pipeline), \
         patch("backend.api.auth.API_KEY_HASH", ""):
        application = create_app()
        yield application


# ── Health Endpoint ──────────────────────────────────

class TestHealthEndpoint:
    @pytest.mark.asyncio
    async def test_health_returns_200(self, app, mock_pipeline):
        """GET /api/v1/health should return 200 with status dict."""
        from httpx import AsyncClient, ASGITransport

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/health")
            assert response.status_code == 200
            data = response.json()
            assert "status" in data


# ── Status Endpoint ──────────────────────────────────

class TestStatusEndpoint:
    @pytest.mark.asyncio
    async def test_status_returns_data(self, app, mock_pipeline):
        """GET /api/v1/status should return pipeline state data."""
        from httpx import AsyncClient, ASGITransport

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/status")
            assert response.status_code == 200
            data = response.json()
            assert "status" in data
            assert "pipeline" in data


# ── Project Options Endpoint ─────────────────────────

class TestProjectEndpoint:
    @pytest.mark.asyncio
    async def test_get_project_returns_options(self, app):
        """GET /api/v1/project should return current config + valid options."""
        from httpx import AsyncClient, ASGITransport

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/project")
            assert response.status_code == 200
            data = response.json()
            # Should contain both current config and options
            assert "engine" in data
            assert "genre" in data
            assert "options" in data
            # Options should list valid values
            assert "engines" in data["options"]
            assert "genres" in data["options"]


# ── Project Validation ───────────────────────────────

class TestProjectValidation:
    @pytest.mark.asyncio
    async def test_rejects_invalid_engine(self, app):
        """POST /api/v1/project with invalid engine should return success=False."""
        from httpx import AsyncClient, ASGITransport

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/v1/project", json={
                "game_name": "Test Game",
                "engine": "INVALID_ENGINE",
                "genre": "platformer",
                "platform": "web",
            })
            data = response.json()
            assert data.get("success") is False
            assert any("engine" in e.lower() for e in data.get("errors", []))

    @pytest.mark.asyncio
    async def test_rejects_invalid_genre(self, app):
        """POST /api/v1/project with invalid genre should return success=False."""
        from httpx import AsyncClient, ASGITransport

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/v1/project", json={
                "game_name": "Test Game",
                "engine": "phaser",
                "genre": "INVALID_GENRE",
                "platform": "web",
            })
            data = response.json()
            assert data.get("success") is False
            assert any("genre" in e.lower() for e in data.get("errors", []))

    @pytest.mark.asyncio
    async def test_rejects_missing_game_name(self, app):
        """POST /api/v1/project without game_name should return error."""
        from httpx import AsyncClient, ASGITransport

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/v1/project", json={
                "game_name": "",
                "engine": "phaser",
                "genre": "platformer",
                "platform": "web",
            })
            data = response.json()
            assert data.get("success") is False
