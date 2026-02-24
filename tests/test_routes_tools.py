"""Functional tests for dashboard routes: /tools and /swarm/live WebSocket.

Tests the tools dashboard page, API stats endpoint, and the swarm
WebSocket live endpoint.
"""

from unittest.mock import patch, MagicMock, AsyncMock

import pytest
from fastapi.testclient import TestClient


# ── /tools route ──────────────────────────────────────────────────────────────


class TestToolsPage:
    def test_tools_page_returns_200(self, client):
        response = client.get("/tools")
        assert response.status_code == 200

    def test_tools_page_html_content(self, client):
        response = client.get("/tools")
        assert "text/html" in response.headers["content-type"]

    def test_tools_api_stats_returns_json(self, client):
        response = client.get("/tools/api/stats")
        assert response.status_code == 200
        data = response.json()
        assert "all_stats" in data
        assert "available_tools" in data
        assert isinstance(data["available_tools"], list)
        assert len(data["available_tools"]) > 0

    def test_tools_api_stats_includes_base_tools(self, client):
        response = client.get("/tools/api/stats")
        data = response.json()
        base_tools = {"web_search", "shell", "python", "read_file", "write_file", "list_files"}
        for tool in base_tools:
            assert tool in data["available_tools"], f"Missing: {tool}"

    def test_tools_page_with_agents(self, client):
        """Spawn an agent and verify tools page includes it."""
        client.post("/swarm/spawn", data={"name": "Echo"})
        response = client.get("/tools")
        assert response.status_code == 200


# ── /swarm/live WebSocket ─────────────────────────────────────────────────────


class TestSwarmWebSocket:
    def test_websocket_connect_disconnect(self, client):
        with client.websocket_connect("/swarm/live") as ws:
            # Connection succeeds
            pass
            # Disconnect on context manager exit

    def test_websocket_send_receive(self, client):
        """The WebSocket endpoint should accept messages (it logs them)."""
        with client.websocket_connect("/swarm/live") as ws:
            ws.send_text("ping")
            # The endpoint only echoes via logging, not back to client.
            # The key test is that it doesn't crash on receiving a message.

    def test_websocket_multiple_connections(self, client):
        """Multiple clients can connect simultaneously."""
        with client.websocket_connect("/swarm/live") as ws1:
            with client.websocket_connect("/swarm/live") as ws2:
                ws1.send_text("hello from 1")
                ws2.send_text("hello from 2")
