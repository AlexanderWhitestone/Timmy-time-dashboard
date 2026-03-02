"""Tests for serve endpoints merged into the dashboard app.

TDD: The timmy_serve endpoints (/serve/chat, /serve/status) are now
served by the main dashboard app, eliminating the need for a separate
FastAPI application.
"""

import os
from unittest.mock import MagicMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def serve_client():
    """Dashboard test client bypassing proxy for localhost."""
    from dashboard.app import app
    transport = httpx.WSGITransport(app=app)
    client = httpx.Client(transport=transport, base_url="http://testserver")
    yield client
    client.close()


class TestServeStatusMerged:
    """Test /serve/status endpoint in dashboard app."""

    def test_serve_status_returns_200(self, serve_client):
        resp = serve_client.get("/serve/status")
        assert resp.status_code == 200

    def test_serve_status_shows_active(self, serve_client):
        resp = serve_client.get("/serve/status")
        data = resp.json()
        assert data["status"] == "active"

    def test_serve_status_includes_backend(self, serve_client):
        resp = serve_client.get("/serve/status")
        data = resp.json()
        assert "backend" in data


class TestServeChatMerged:
    """Test /serve/chat endpoint in dashboard app."""

    @patch("dashboard.routes.serve.create_timmy")
    def test_serve_chat_returns_response(self, mock_create, serve_client):
        mock_agent = MagicMock()
        mock_result = MagicMock()
        mock_result.content = "Test response"
        mock_agent.run.return_value = mock_result
        mock_create.return_value = mock_agent

        resp = serve_client.post("/serve/chat", json={"message": "Hello"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["response"] == "Test response"

    def test_serve_chat_rejects_empty_message(self, serve_client):
        resp = serve_client.post("/serve/chat", json={"message": ""})
        assert resp.status_code == 422
