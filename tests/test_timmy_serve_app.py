"""Tests for timmy_serve/app.py — Serve FastAPI app and endpoints."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def serve_client():
    """Create a TestClient for the timmy-serve app."""
    from timmy_serve.app import create_timmy_serve_app

    app = create_timmy_serve_app(price_sats=100)
    return TestClient(app)


class TestHealthEndpoint:
    def test_health_returns_ok(self, serve_client):
        resp = serve_client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["service"] == "timmy-serve"


class TestServeStatus:
    def test_status_returns_pricing(self, serve_client):
        resp = serve_client.get("/serve/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["price_sats"] == 100
        assert "total_invoices" in data
        assert "total_earned_sats" in data


class TestServeChatEndpoint:
    """Regression tests for /serve/chat.

    The original implementation declared ``async def serve_chat(request: ChatRequest)``
    which shadowed FastAPI's ``Request`` object.  Calling ``request.headers`` on a
    Pydantic model raised ``AttributeError``.  The fix splits the parameters into
    ``request: Request`` (FastAPI) and ``body: ChatRequest`` (Pydantic).
    """

    def test_chat_without_auth_returns_402(self, serve_client):
        """Unauthenticated request should get a 402 challenge."""
        resp = serve_client.post(
            "/serve/chat",
            json={"message": "Hello"},
        )
        assert resp.status_code == 402
        data = resp.json()
        assert data["error"] == "Payment Required"
        assert "macaroon" in data
        assert "invoice" in data

    @patch("timmy_serve.app.create_timmy")
    @patch("timmy_serve.app.verify_l402_token", return_value=True)
    def test_chat_with_valid_l402_token(self, mock_verify, mock_create, serve_client):
        """Authenticated request should reach the chat handler without AttributeError."""
        mock_agent = MagicMock()
        mock_result = MagicMock()
        mock_result.content = "I am Timmy."
        mock_agent.run.return_value = mock_result
        mock_create.return_value = mock_agent

        resp = serve_client.post(
            "/serve/chat",
            json={"message": "Who are you?"},
            headers={"Authorization": "L402 fake-macaroon:fake-preimage"},
        )
        # The key assertion: we must NOT get a 500 from AttributeError
        assert resp.status_code == 200
        data = resp.json()
        assert data["response"] == "I am Timmy."
        mock_agent.run.assert_called_once_with("Who are you?", stream=False)

    @patch("timmy_serve.app.create_timmy")
    @patch("timmy_serve.app.verify_l402_token", return_value=True)
    def test_chat_reads_auth_header_from_request(
        self, mock_verify, mock_create, serve_client
    ):
        """Ensure auth header is read from the HTTP Request, not the JSON body."""
        mock_agent = MagicMock()
        mock_result = MagicMock()
        mock_result.content = "ok"
        mock_agent.run.return_value = mock_result
        mock_create.return_value = mock_agent

        resp = serve_client.post(
            "/serve/chat",
            json={"message": "test"},
            headers={"Authorization": "L402 abc:def"},
        )
        assert resp.status_code == 200
        # Should not raise AttributeError on request.headers
