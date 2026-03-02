"""Tests for timmy_serve/app.py — Serve FastAPI app and endpoints."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def serve_client():
    """Create a TestClient for the timmy-serve app."""
    from timmy_serve.app import create_timmy_serve_app

    app = create_timmy_serve_app()
    return TestClient(app)


class TestHealthEndpoint:
    def test_health_returns_ok(self, serve_client):
        resp = serve_client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["service"] == "timmy-serve"


class TestServeStatus:
    def test_status_returns_info(self, serve_client):
        resp = serve_client.get("/serve/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "active"


class TestServeChatEndpoint:
    @patch("timmy_serve.app.create_timmy")
    def test_chat_returns_response(self, mock_create, serve_client):
        mock_agent = MagicMock()
        mock_result = MagicMock()
        mock_result.content = "I am Timmy."
        mock_agent.run.return_value = mock_result
        mock_create.return_value = mock_agent

        resp = serve_client.post(
            "/serve/chat",
            json={"message": "Who are you?"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["response"] == "I am Timmy."
        mock_agent.run.assert_called_once_with("Who are you?", stream=False)
