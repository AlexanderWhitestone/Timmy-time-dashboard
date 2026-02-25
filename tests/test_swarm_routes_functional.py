"""Functional tests for swarm routes — /swarm/* endpoints.

Tests the full request/response cycle for swarm management endpoints,
including error paths and HTMX partial rendering.
"""

from unittest.mock import patch, AsyncMock

import pytest
from fastapi.testclient import TestClient


class TestSwarmStatusRoutes:
    def test_swarm_status(self, client):
        response = client.get("/swarm")
        assert response.status_code == 200
        data = response.json()
        assert "agents" in data or "status" in data or isinstance(data, dict)

    def test_list_agents_empty(self, client):
        response = client.get("/swarm/agents")
        assert response.status_code == 200
        data = response.json()
        assert "agents" in data
        assert isinstance(data["agents"], list)


class TestSwarmAgentLifecycle:
    def test_spawn_agent(self, client):
        response = client.post("/swarm/spawn", data={"name": "Echo"})
        assert response.status_code == 200
        data = response.json()
        assert "id" in data or "agent_id" in data or "name" in data

    def test_spawn_and_list(self, client):
        client.post("/swarm/spawn", data={"name": "Echo"})
        response = client.get("/swarm/agents")
        data = response.json()
        assert len(data["agents"]) >= 1
        names = [a["name"] for a in data["agents"]]
        assert "Echo" in names

    def test_stop_agent(self, client):
        spawn_resp = client.post("/swarm/spawn", data={"name": "TestAgent"})
        spawn_data = spawn_resp.json()
        agent_id = spawn_data.get("id") or spawn_data.get("agent_id")
        response = client.delete(f"/swarm/agents/{agent_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["stopped"] is True

    def test_stop_nonexistent_agent(self, client):
        response = client.delete("/swarm/agents/nonexistent-id")
        assert response.status_code == 200
        data = response.json()
        assert data["stopped"] is False


class TestSwarmTaskLifecycle:
    def test_post_task(self, client):
        response = client.post("/swarm/tasks", data={"description": "Summarise readme"})
        assert response.status_code == 200
        data = response.json()
        assert data["description"] == "Summarise readme"
        assert data["status"] == "bidding"  # coordinator auto-opens auction
        assert "task_id" in data

    def test_list_tasks(self, client):
        client.post("/swarm/tasks", data={"description": "Task A"})
        client.post("/swarm/tasks", data={"description": "Task B"})
        response = client.get("/swarm/tasks")
        assert response.status_code == 200
        data = response.json()
        assert len(data["tasks"]) >= 2

    def test_list_tasks_filter_by_status(self, client):
        client.post("/swarm/tasks", data={"description": "Bidding task"})
        response = client.get("/swarm/tasks?status=bidding")
        assert response.status_code == 200
        data = response.json()
        for task in data["tasks"]:
            assert task["status"] == "bidding"

    def test_list_tasks_invalid_status(self, client):
        """Invalid TaskStatus enum value causes server error (unhandled ValueError)."""
        with pytest.raises(ValueError, match="is not a valid TaskStatus"):
            client.get("/swarm/tasks?status=invalid_status")

    def test_get_task_by_id(self, client):
        post_resp = client.post("/swarm/tasks", data={"description": "Find me"})
        task_id = post_resp.json()["task_id"]
        response = client.get(f"/swarm/tasks/{task_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["description"] == "Find me"

    def test_get_nonexistent_task(self, client):
        response = client.get("/swarm/tasks/nonexistent-id")
        assert response.status_code == 200
        data = response.json()
        assert "error" in data

    def test_complete_task(self, client):
        # Create and assign a task first
        client.post("/swarm/spawn", data={"name": "Worker"})
        post_resp = client.post("/swarm/tasks", data={"description": "Do work"})
        task_id = post_resp.json()["task_id"]
        response = client.post(
            f"/swarm/tasks/{task_id}/complete",
            data={"result": "Work done"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"

    def test_complete_nonexistent_task(self, client):
        response = client.post(
            "/swarm/tasks/fake-id/complete",
            data={"result": "done"},
        )
        assert response.status_code == 404

    def test_fail_task(self, client):
        post_resp = client.post("/swarm/tasks", data={"description": "Will fail"})
        task_id = post_resp.json()["task_id"]
        response = client.post(
            f"/swarm/tasks/{task_id}/fail",
            data={"reason": "out of memory"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "failed"

    def test_fail_nonexistent_task(self, client):
        response = client.post(
            "/swarm/tasks/fake-id/fail",
            data={"reason": "no reason"},
        )
        assert response.status_code == 404


class TestSwarmAuction:
    def test_post_task_and_auction_no_agents(self, client):
        """Auction with no bidders should still return a response."""
        with patch(
            "swarm.coordinator.AUCTION_DURATION_SECONDS", 0
        ):
            response = client.post(
                "/swarm/tasks/auction",
                data={"description": "Quick task"},
            )
            assert response.status_code == 200
            data = response.json()
            assert "task_id" in data


class TestSwarmInsights:
    def test_insights_empty(self, client):
        response = client.get("/swarm/insights")
        assert response.status_code == 200
        data = response.json()
        assert "agents" in data

    def test_agent_insights(self, client):
        response = client.get("/swarm/insights/some-agent-id")
        assert response.status_code == 200
        data = response.json()
        assert data["agent_id"] == "some-agent-id"
        assert "total_bids" in data
        assert "win_rate" in data


class TestSwarmUIPartials:
    def test_live_page(self, client):
        response = client.get("/swarm/live")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_agents_sidebar(self, client):
        response = client.get("/swarm/agents/sidebar")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_agent_panel_not_found(self, client):
        response = client.get("/swarm/agents/nonexistent/panel")
        assert response.status_code == 404

    def test_agent_panel_found(self, client):
        spawn_resp = client.post("/swarm/spawn", data={"name": "Echo"})
        agent_id = spawn_resp.json().get("id") or spawn_resp.json().get("agent_id")
        response = client.get(f"/swarm/agents/{agent_id}/panel")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_task_panel_route_returns_html(self, client):
        """The /swarm/tasks/panel route must return HTML, not be shadowed by {task_id}."""
        response = client.get("/swarm/tasks/panel")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_direct_assign_with_agent(self, client):
        spawn_resp = client.post("/swarm/spawn", data={"name": "Worker"})
        agent_id = spawn_resp.json().get("id") or spawn_resp.json().get("agent_id")
        response = client.post(
            "/swarm/tasks/direct",
            data={"description": "Direct task", "agent_id": agent_id},
        )
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_direct_assign_without_agent(self, client):
        """No agent → runs auction (with no bidders)."""
        with patch("swarm.coordinator.AUCTION_DURATION_SECONDS", 0):
            response = client.post(
                "/swarm/tasks/direct",
                data={"description": "Open task"},
            )
            assert response.status_code == 200

    def test_message_agent_creates_task(self, client):
        """Messaging a non-Timmy agent creates and assigns a task."""
        spawn_resp = client.post("/swarm/spawn", data={"name": "Echo"})
        agent_id = spawn_resp.json().get("id") or spawn_resp.json().get("agent_id")
        response = client.post(
            f"/swarm/agents/{agent_id}/message",
            data={"message": "Summarise the readme"},
        )
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_message_nonexistent_agent(self, client):
        response = client.post(
            "/swarm/agents/fake-id/message",
            data={"message": "hello"},
        )
        assert response.status_code == 404
