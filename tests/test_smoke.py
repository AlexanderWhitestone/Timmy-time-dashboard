"""Smoke tests — verify every major page loads without uncaught exceptions.

These tests catch regressions that unit tests miss: import errors,
template rendering failures, database schema mismatches, and startup
crashes.  They run fast (no Ollama needed) and should stay green on
every commit.
"""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from dashboard.app import app
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


# ---------------------------------------------------------------------------
# Core pages — these MUST return 200
# ---------------------------------------------------------------------------

class TestCorePages:
    """Every core dashboard page loads without error."""

    def test_index(self, client):
        r = client.get("/")
        assert r.status_code == 200

    def test_health(self, client):
        r = client.get("/health")
        assert r.status_code == 200

    def test_health_status(self, client):
        r = client.get("/health/status")
        assert r.status_code == 200

    def test_agent_panel(self, client):
        r = client.get("/agents/default/panel")
        assert r.status_code == 200

    def test_agent_history(self, client):
        r = client.get("/agents/default/history")
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# Feature pages — should return 200 (or 307 redirect, never 500)
# ---------------------------------------------------------------------------

class TestFeaturePages:
    """Feature pages load without 500 errors."""

    def test_briefing(self, client):
        r = client.get("/briefing")
        assert r.status_code in (200, 307)

    def test_thinking(self, client):
        r = client.get("/thinking")
        assert r.status_code == 200

    def test_tools(self, client):
        r = client.get("/tools")
        assert r.status_code == 200

    def test_memory(self, client):
        r = client.get("/memory")
        assert r.status_code == 200

    def test_calm(self, client):
        r = client.get("/calm")
        assert r.status_code == 200

    def test_tasks(self, client):
        r = client.get("/tasks")
        assert r.status_code == 200

    def test_work_orders_queue(self, client):
        r = client.get("/work-orders/queue")
        assert r.status_code == 200

    def test_mobile(self, client):
        r = client.get("/mobile")
        assert r.status_code == 200

    def test_spark(self, client):
        r = client.get("/spark")
        assert r.status_code in (200, 307)

    def test_models(self, client):
        r = client.get("/models")
        assert r.status_code == 200

    def test_swarm_live(self, client):
        r = client.get("/swarm/live")
        assert r.status_code == 200

    def test_swarm_events(self, client):
        r = client.get("/swarm/events")
        assert r.status_code == 200

    def test_marketplace(self, client):
        r = client.get("/marketplace")
        assert r.status_code in (200, 307)


# ---------------------------------------------------------------------------
# JSON API endpoints — should return valid JSON, never 500
# ---------------------------------------------------------------------------

class TestAPIEndpoints:
    """API endpoints return valid JSON without server errors."""

    def test_health_json(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        data = r.json()
        assert "status" in data

    def test_health_components(self, client):
        r = client.get("/health/components")
        assert r.status_code == 200

    def test_health_sovereignty(self, client):
        r = client.get("/health/sovereignty")
        assert r.status_code == 200

    def test_queue_status(self, client):
        r = client.get("/api/queue/status")
        assert r.status_code == 200

    def test_tasks_api(self, client):
        r = client.get("/api/tasks")
        assert r.status_code == 200

    def test_chat_history(self, client):
        r = client.get("/api/chat/history")
        assert r.status_code == 200

    def test_tools_stats(self, client):
        r = client.get("/tools/api/stats")
        assert r.status_code == 200

    def test_thinking_api(self, client):
        r = client.get("/thinking/api")
        assert r.status_code == 200

    def test_notifications_api(self, client):
        r = client.get("/api/notifications")
        assert r.status_code == 200

    def test_providers_api(self, client):
        r = client.get("/router/api/providers")
        assert r.status_code == 200

    def test_mobile_status(self, client):
        r = client.get("/mobile/status")
        assert r.status_code == 200

    def test_discord_status(self, client):
        r = client.get("/discord/status")
        assert r.status_code == 200

    def test_telegram_status(self, client):
        r = client.get("/telegram/status")
        assert r.status_code == 200

    def test_grok_status(self, client):
        r = client.get("/grok/status")
        assert r.status_code == 200

    def test_paperclip_status(self, client):
        r = client.get("/api/paperclip/status")
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# No 500s — every GET route should survive without server error
# ---------------------------------------------------------------------------

class TestNo500:
    """Verify that no page returns a 500 Internal Server Error."""

    @pytest.mark.parametrize("path", [
        "/",
        "/health",
        "/health/status",
        "/health/sovereignty",
        "/health/components",
        "/agents/default/panel",
        "/agents/default/history",
        "/briefing",
        "/thinking",
        "/thinking/api",
        "/tools",
        "/tools/api/stats",
        "/memory",
        "/calm",
        "/tasks",
        "/tasks/pending",
        "/tasks/active",
        "/tasks/completed",
        "/work-orders/queue",
        "/work-orders/queue/pending",
        "/work-orders/queue/active",
        "/mobile",
        "/mobile/status",
        "/spark",
        "/models",
        "/swarm/live",
        "/swarm/events",
        "/marketplace",
        "/api/queue/status",
        "/api/tasks",
        "/api/chat/history",
        "/api/notifications",
        "/router/api/providers",
        "/discord/status",
        "/telegram/status",
        "/grok/status",
        "/grok/stats",
        "/api/paperclip/status",
    ])
    def test_no_500(self, client, path):
        r = client.get(path)
        assert r.status_code != 500, f"GET {path} returned 500"
