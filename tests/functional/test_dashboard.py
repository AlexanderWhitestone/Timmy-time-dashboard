"""Functional tests for the dashboard — real HTTP requests, no mocking.

The dashboard runs with Ollama offline (graceful degradation).
These tests verify what a real user sees when they open the browser.
"""

import pytest


class TestDashboardLoads:
    """Verify the dashboard serves real HTML pages."""

    def test_index_page(self, app_client):
        response = app_client.get("/")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        # The real rendered page should have the base HTML structure
        assert "<html" in response.text
        assert "Timmy" in response.text

    def test_health_endpoint(self, app_client):
        response = app_client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data or "ollama" in data

    def test_agents_json(self, app_client):
        response = app_client.get("/agents")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, (dict, list))

    def test_swarm_live_page(self, app_client):
        response = app_client.get("/swarm/live")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "WebSocket" in response.text or "swarm" in response.text.lower()

    def test_mobile_endpoint(self, app_client):
        response = app_client.get("/mobile/status")
        assert response.status_code == 200


class TestChatFlowOffline:
    """Test the chat flow when Ollama is not running.

    This is a real user scenario — they start the dashboard before Ollama.
    The app should degrade gracefully, not crash.
    """

    def test_chat_with_ollama_offline(self, app_client):
        """POST to chat endpoint — should return HTML with an error message,
        not a 500 server error."""
        response = app_client.post(
            "/agents/timmy/chat",
            data={"message": "hello timmy"},
        )
        # The route catches exceptions and returns them in the template
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        # Should contain either the error message or the response
        assert "hello timmy" in response.text or "offline" in response.text.lower() or "error" in response.text.lower()

    def test_chat_requires_message_field(self, app_client):
        """POST without the message field should fail."""
        response = app_client.post("/agents/timmy/chat", data={})
        assert response.status_code == 422

    def test_history_starts_empty(self, app_client):
        response = app_client.get("/agents/timmy/history")
        assert response.status_code == 200

    def test_chat_then_history(self, app_client):
        """After chatting, history should contain the message."""
        app_client.post("/agents/timmy/chat", data={"message": "test message"})
        response = app_client.get("/agents/timmy/history")
        assert response.status_code == 200
        assert "test message" in response.text

    def test_clear_history(self, app_client):
        app_client.post("/agents/timmy/chat", data={"message": "ephemeral"})
        response = app_client.delete("/agents/timmy/history")
        assert response.status_code == 200


class TestSwarmLifecycle:
    """Full swarm lifecycle: spawn → post task → bid → assign → complete.

    No mocking.  Real coordinator, real SQLite, real in-process agents.
    """

    def test_spawn_agent_and_list(self, app_client):
        spawn = app_client.post("/swarm/spawn", data={"name": "Echo"})
        assert spawn.status_code == 200
        spawn_data = spawn.json()
        agent_id = spawn_data.get("id") or spawn_data.get("agent_id")
        assert agent_id

        agents = app_client.get("/swarm/agents")
        assert agents.status_code == 200
        agent_names = [a["name"] for a in agents.json()["agents"]]
        assert "Echo" in agent_names

    def test_post_task_opens_auction(self, app_client):
        resp = app_client.post("/swarm/tasks", data={"description": "Summarize README"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["description"] == "Summarize README"
        assert data["status"] == "bidding"

    def test_task_persists_in_list(self, app_client):
        app_client.post("/swarm/tasks", data={"description": "Task Alpha"})
        app_client.post("/swarm/tasks", data={"description": "Task Beta"})
        resp = app_client.get("/swarm/tasks")
        descriptions = [t["description"] for t in resp.json()["tasks"]]
        assert "Task Alpha" in descriptions
        assert "Task Beta" in descriptions

    def test_complete_task(self, app_client):
        post = app_client.post("/swarm/tasks", data={"description": "Quick job"})
        task_id = post.json()["task_id"]
        resp = app_client.post(
            f"/swarm/tasks/{task_id}/complete",
            data={"result": "Done."},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "completed"

        # Verify the result persisted
        task = app_client.get(f"/swarm/tasks/{task_id}")
        assert task.json()["result"] == "Done."

    def test_fail_task_feeds_learner(self, app_client):
        post = app_client.post("/swarm/tasks", data={"description": "Doomed job"})
        task_id = post.json()["task_id"]
        resp = app_client.post(
            f"/swarm/tasks/{task_id}/fail",
            data={"reason": "OOM"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "failed"

    def test_stop_agent(self, app_client):
        spawn = app_client.post("/swarm/spawn", data={"name": "Disposable"})
        agent_id = spawn.json().get("id") or spawn.json().get("agent_id")
        resp = app_client.delete(f"/swarm/agents/{agent_id}")
        assert resp.status_code == 200
        assert resp.json()["stopped"] is True

    def test_insights_endpoint(self, app_client):
        resp = app_client.get("/swarm/insights")
        assert resp.status_code == 200
        assert "agents" in resp.json()

    def test_websocket_connects(self, app_client):
        """Real WebSocket connection to /swarm/live."""
        with app_client.websocket_connect("/swarm/live") as ws:
            ws.send_text("ping")
            # Connection holds — the endpoint just logs, doesn't echo back.
            # The point is it doesn't crash.


class TestSwarmUIPartials:
    """HTMX partial endpoints — verify they return real rendered HTML."""

    def test_agents_sidebar_html(self, app_client):
        app_client.post("/swarm/spawn", data={"name": "Echo"})
        resp = app_client.get("/swarm/agents/sidebar")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert "echo" in resp.text.lower()

    def test_agent_panel_html(self, app_client):
        spawn = app_client.post("/swarm/spawn", data={"name": "Echo"})
        agent_id = spawn.json().get("id") or spawn.json().get("agent_id")
        resp = app_client.get(f"/swarm/agents/{agent_id}/panel")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert "echo" in resp.text.lower()

    def test_message_agent_creates_task(self, app_client):
        spawn = app_client.post("/swarm/spawn", data={"name": "Worker"})
        agent_id = spawn.json().get("id") or spawn.json().get("agent_id")
        resp = app_client.post(
            f"/swarm/agents/{agent_id}/message",
            data={"message": "Summarise the codebase"},
        )
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    def test_direct_assign_to_agent(self, app_client):
        spawn = app_client.post("/swarm/spawn", data={"name": "Worker"})
        agent_id = spawn.json().get("id") or spawn.json().get("agent_id")
        resp = app_client.post(
            "/swarm/tasks/direct",
            data={"description": "Direct job", "agent_id": agent_id},
        )
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
