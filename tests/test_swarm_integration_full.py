"""Integration tests for full swarm task lifecycle.

Tests the complete flow: post task → auction runs → persona bids → 
task assigned → agent executes → result returned.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture(autouse=True)
def _fast_auction():
    """Skip the 15-second auction wait in tests."""
    with patch("swarm.coordinator.AUCTION_DURATION_SECONDS", 0):
        yield


class TestFullSwarmLifecycle:
    """Integration tests for end-to-end swarm task lifecycle."""

    def test_post_task_creates_bidding_task(self, client):
        """Posting a task should create it in BIDDING status."""
        response = client.post("/swarm/tasks", data={"description": "Test integration task"})
        assert response.status_code == 200
        
        data = response.json()
        assert "task_id" in data
        assert data["status"] == "bidding"
        
        # Verify task exists and is in bidding status
        task_response = client.get(f"/swarm/tasks/{data['task_id']}")
        task = task_response.json()
        assert task["status"] == "bidding"

    def test_post_task_and_auction_assigns_winner(self, client):
        """Posting task with auction should assign it to a winner."""
        from swarm.coordinator import coordinator
        
        # Spawn an in-process agent that can bid
        coordinator.spawn_in_process_agent("TestBidder")
        
        # Post task with auction
        response = client.post("/swarm/tasks/auction", data={"description": "Task for auction"})
        assert response.status_code == 200
        
        data = response.json()
        assert data["status"] == "assigned"
        assert data["assigned_agent"] is not None
        assert data["winning_bid"] is not None

    def test_complete_task_endpoint_updates_status(self, client):
        """Complete endpoint should update task to COMPLETED status."""
        # Create and assign a task
        client.post("/swarm/spawn", data={"name": "TestWorker"})
        auction_resp = client.post("/swarm/tasks/auction", data={"description": "Task to complete"})
        task_id = auction_resp.json()["task_id"]
        
        # Complete the task
        complete_resp = client.post(
            f"/swarm/tasks/{task_id}/complete",
            data={"result": "Task completed successfully"},
        )
        assert complete_resp.status_code == 200
        
        # Verify task is completed
        task_resp = client.get(f"/swarm/tasks/{task_id}")
        task = task_resp.json()
        assert task["status"] == "completed"
        assert task["result"] == "Task completed successfully"

    def test_fail_task_endpoint_updates_status(self, client):
        """Fail endpoint should update task to FAILED status."""
        # Create and assign a task
        client.post("/swarm/spawn", data={"name": "TestWorker"})
        auction_resp = client.post("/swarm/tasks/auction", data={"description": "Task to fail"})
        task_id = auction_resp.json()["task_id"]
        
        # Fail the task
        fail_resp = client.post(
            f"/swarm/tasks/{task_id}/fail",
            data={"reason": "Task execution failed"},
        )
        assert fail_resp.status_code == 200
        
        # Verify task is failed
        task_resp = client.get(f"/swarm/tasks/{task_id}")
        task = task_resp.json()
        assert task["status"] == "failed"

    def test_agent_status_updated_on_assignment(self, client):
        """Agent status should change to busy when assigned a task."""
        from swarm.coordinator import coordinator
        
        # Spawn in-process agent
        result = coordinator.spawn_in_process_agent("StatusTestAgent")
        agent_id = result["agent_id"]
        
        # Verify idle status
        agents_resp = client.get("/swarm/agents")
        agent = next(a for a in agents_resp.json()["agents"] if a["id"] == agent_id)
        assert agent["status"] == "idle"
        
        # Assign task
        client.post("/swarm/tasks/auction", data={"description": "Task for status test"})
        
        # Verify busy status
        agents_resp = client.get("/swarm/agents")
        agent = next(a for a in agents_resp.json()["agents"] if a["id"] == agent_id)
        assert agent["status"] == "busy"

    def test_agent_status_updated_on_completion(self, client):
        """Agent status should return to idle when task completes."""
        # Spawn agent and assign task
        spawn_resp = client.post("/swarm/spawn", data={"name": "CompleteTestAgent"})
        agent_id = spawn_resp.json()["agent_id"]
        auction_resp = client.post("/swarm/tasks/auction", data={"description": "Task"})
        task_id = auction_resp.json()["task_id"]
        
        # Complete task
        client.post(f"/swarm/tasks/{task_id}/complete", data={"result": "Done"})
        
        # Verify idle status
        agents_resp = client.get("/swarm/agents")
        agent = next(a for a in agents_resp.json()["agents"] if a["id"] == agent_id)
        assert agent["status"] == "idle"


class TestSwarmPersonaLifecycle:
    """Integration tests for persona agent lifecycle."""

    def test_spawn_persona_registers_with_capabilities(self, client):
        """Spawning a persona should register with correct capabilities."""
        response = client.post("/swarm/spawn", data={"name": "Echo"})
        assert response.status_code == 200
        
        data = response.json()
        assert "agent_id" in data
        
        # Verify in agent list with correct capabilities
        agents_resp = client.get("/swarm/agents")
        agent = next(a for a in agents_resp.json()["agents"] if a["id"] == data["agent_id"])
        assert "echo" in agent.get("capabilities", "").lower() or agent["name"] == "Echo"

    def test_stop_agent_removes_from_registry(self, client):
        """Stopping an agent should remove it from the registry."""
        # Spawn agent
        spawn_resp = client.post("/swarm/spawn", data={"name": "TempAgent"})
        agent_id = spawn_resp.json()["agent_id"]
        
        # Verify exists
        agents_before = client.get("/swarm/agents").json()["agents"]
        assert any(a["id"] == agent_id for a in agents_before)
        
        # Stop agent
        client.delete(f"/swarm/agents/{agent_id}")
        
        # Verify removed
        agents_after = client.get("/swarm/agents").json()["agents"]
        assert not any(a["id"] == agent_id for a in agents_after)

    def test_persona_bids_on_relevant_task(self, client):
        """Persona should bid on tasks matching its specialty."""
        from swarm.coordinator import coordinator
        
        # Spawn a research persona (Echo) - this creates a bidding agent
        coordinator.spawn_persona("echo")
        
        # Post a research-related task
        response = client.post("/swarm/tasks", data={"description": "Research quantum computing"})
        task_id = response.json()["task_id"]
        
        # Run auction
        import asyncio
        asyncio.run(coordinator.run_auction_and_assign(task_id))
        
        # Verify task was assigned (someone bid)
        task_resp = client.get(f"/swarm/tasks/{task_id}")
        task = task_resp.json()
        assert task["status"] == "assigned"
        assert task["assigned_agent"] is not None


class TestSwarmTaskFiltering:
    """Integration tests for task filtering and listing."""

    def test_list_tasks_by_status(self, client):
        """Should be able to filter tasks by status."""
        # Create tasks in different statuses
        client.post("/swarm/spawn", data={"name": "Worker"})
        
        # Pending task (just created)
        pending_resp = client.post("/swarm/tasks", data={"description": "Pending task"})
        pending_id = pending_resp.json()["task_id"]
        
        # Completed task
        auction_resp = client.post("/swarm/tasks/auction", data={"description": "Completed task"})
        completed_id = auction_resp.json()["task_id"]
        client.post(f"/swarm/tasks/{completed_id}/complete", data={"result": "Done"})
        
        # Filter by status
        completed_list = client.get("/swarm/tasks?status=completed").json()["tasks"]
        assert any(t["id"] == completed_id for t in completed_list)
        
        bidding_list = client.get("/swarm/tasks?status=bidding").json()["tasks"]
        assert any(t["id"] == pending_id for t in bidding_list)

    def test_get_nonexistent_task_returns_error(self, client):
        """Getting a non-existent task should return appropriate error."""
        response = client.get("/swarm/tasks/nonexistent-id")
        assert response.status_code == 200  # Endpoint returns 200 with error body
        assert "error" in response.json()


class TestSwarmInsights:
    """Integration tests for swarm learning insights."""

    def test_swarm_insights_endpoint(self, client):
        """Insights endpoint should return agent metrics."""
        response = client.get("/swarm/insights")
        assert response.status_code == 200
        
        data = response.json()
        assert "agents" in data

    def test_agent_insights_endpoint(self, client):
        """Agent-specific insights should return metrics for that agent."""
        # Spawn an agent
        spawn_resp = client.post("/swarm/spawn", data={"name": "InsightsAgent"})
        agent_id = spawn_resp.json()["agent_id"]
        
        response = client.get(f"/swarm/insights/{agent_id}")
        assert response.status_code == 200
        
        data = response.json()
        assert data["agent_id"] == agent_id
        assert "total_bids" in data
