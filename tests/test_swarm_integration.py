"""Integration tests for swarm agent spawning and auction flow.

These tests verify that:
1. In-process agents can be spawned and register themselves.
2. When a task is posted, registered agents automatically bid.
3. The auction resolves with a winner when agents are present.
4. The post_task_and_auction route triggers the full flow.
"""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from swarm.coordinator import SwarmCoordinator
from swarm.tasks import TaskStatus


@pytest.fixture(autouse=True)
def _fast_auction():
    """Skip the 15-second auction wait in tests."""
    with patch("swarm.coordinator.AUCTION_DURATION_SECONDS", 0):
        yield


class TestSwarmInProcessAgents:
    """Test the in-process agent spawning and bidding flow."""

    def setup_method(self):
        self.coord = SwarmCoordinator()

    def test_spawn_agent_returns_agent_info(self):
        result = self.coord.spawn_agent("TestBot")
        assert "agent_id" in result
        assert result["name"] == "TestBot"
        assert result["status"] == "idle"

    def test_spawn_registers_in_registry(self):
        self.coord.spawn_agent("TestBot")
        agents = self.coord.list_swarm_agents()
        assert len(agents) >= 1
        names = [a.name for a in agents]
        assert "TestBot" in names

    def test_post_task_creates_task_in_bidding_status(self):
        task = self.coord.post_task("Test task description")
        assert task.status == TaskStatus.BIDDING
        assert task.description == "Test task description"

    @pytest.mark.asyncio
    async def test_auction_with_in_process_bidders(self):
        """When agents are spawned, they should auto-bid on posted tasks."""
        coord = SwarmCoordinator()
        # Spawn agents that share the coordinator's comms
        coord.spawn_in_process_agent("Alpha")
        coord.spawn_in_process_agent("Beta")

        task = coord.post_task("Research Bitcoin L2s")

        # Run auction — in-process agents should have submitted bids
        # via the comms callback
        winner = await coord.run_auction_and_assign(task.id)
        assert winner is not None
        assert winner.agent_id in [
            n.agent_id for n in coord._in_process_nodes
        ]

        # Task should now be assigned
        updated = coord.get_task(task.id)
        assert updated.status == TaskStatus.ASSIGNED
        assert updated.assigned_agent == winner.agent_id

    @pytest.mark.asyncio
    async def test_auction_no_agents_fails(self):
        """Auction with no agents should fail gracefully."""
        coord = SwarmCoordinator()
        task = coord.post_task("Lonely task")
        winner = await coord.run_auction_and_assign(task.id)
        assert winner is None
        updated = coord.get_task(task.id)
        assert updated.status == TaskStatus.FAILED

    @pytest.mark.asyncio
    async def test_complete_task_after_auction(self):
        """Full lifecycle: spawn → post → auction → complete."""
        coord = SwarmCoordinator()
        coord.spawn_in_process_agent("Worker")
        task = coord.post_task("Build a widget")
        winner = await coord.run_auction_and_assign(task.id)
        assert winner is not None

        completed = coord.complete_task(task.id, "Widget built successfully")
        assert completed is not None
        assert completed.status == TaskStatus.COMPLETED
        assert completed.result == "Widget built successfully"


class TestSwarmRouteAuction:
    """Test that the swarm route triggers auction flow."""

    def test_post_task_and_auction_endpoint(self, client):
        """POST /swarm/tasks/auction should create task and run auction."""
        # First spawn an agent
        resp = client.post("/swarm/spawn", data={"name": "RouteBot"})
        assert resp.status_code == 200

        # Post task with auction
        resp = client.post(
            "/swarm/tasks/auction",
            data={"description": "Route test task"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "task_id" in data
        assert data["status"] in ("assigned", "failed")
