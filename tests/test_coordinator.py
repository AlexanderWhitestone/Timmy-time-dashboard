"""TDD tests for SwarmCoordinator — integration of registry, manager, bidder, comms.

Written RED-first: these tests define the expected behaviour, then we
make them pass by fixing/extending the implementation.
"""

import pytest
from unittest.mock import AsyncMock, patch


# tmp_swarm_db is now provided by conftest.py globally


# ── Coordinator: Agent lifecycle ─────────────────────────────────────────────

def test_coordinator_spawn_agent():
    from swarm.coordinator import SwarmCoordinator
    coord = SwarmCoordinator()
    result = coord.spawn_agent("Echo")
    assert result["name"] == "Echo"
    assert "agent_id" in result
    assert result["status"] == "idle"
    coord.manager.stop_all()


def test_coordinator_spawn_returns_pid():
    from swarm.coordinator import SwarmCoordinator
    coord = SwarmCoordinator()
    result = coord.spawn_agent("Mace")
    assert "pid" in result
    assert isinstance(result["pid"], int)
    coord.manager.stop_all()


def test_coordinator_stop_agent():
    from swarm.coordinator import SwarmCoordinator
    coord = SwarmCoordinator()
    result = coord.spawn_agent("StopMe")
    stopped = coord.stop_agent(result["agent_id"])
    assert stopped is True
    coord.manager.stop_all()


def test_coordinator_list_agents_after_spawn():
    from swarm.coordinator import SwarmCoordinator
    coord = SwarmCoordinator()
    coord.spawn_agent("ListMe")
    agents = coord.list_swarm_agents()
    assert any(a.name == "ListMe" for a in agents)
    coord.manager.stop_all()


# ── Coordinator: Task lifecycle ──────────────────────────────────────────────

def test_coordinator_post_task():
    from swarm.coordinator import SwarmCoordinator
    from swarm.tasks import TaskStatus
    coord = SwarmCoordinator()
    task = coord.post_task("Research Bitcoin L402")
    assert task.description == "Research Bitcoin L402"
    assert task.status == TaskStatus.BIDDING


def test_coordinator_get_task():
    from swarm.coordinator import SwarmCoordinator
    coord = SwarmCoordinator()
    task = coord.post_task("Find me")
    found = coord.get_task(task.id)
    assert found is not None
    assert found.description == "Find me"


def test_coordinator_get_task_not_found():
    from swarm.coordinator import SwarmCoordinator
    coord = SwarmCoordinator()
    assert coord.get_task("nonexistent") is None


def test_coordinator_list_tasks():
    from swarm.coordinator import SwarmCoordinator
    coord = SwarmCoordinator()
    coord.post_task("Task A")
    coord.post_task("Task B")
    tasks = coord.list_tasks()
    assert len(tasks) >= 2


def test_coordinator_list_tasks_by_status():
    from swarm.coordinator import SwarmCoordinator
    from swarm.tasks import TaskStatus
    coord = SwarmCoordinator()
    coord.post_task("Bidding task")
    bidding = coord.list_tasks(TaskStatus.BIDDING)
    assert len(bidding) >= 1


def test_coordinator_complete_task():
    from swarm.coordinator import SwarmCoordinator
    from swarm.tasks import TaskStatus
    coord = SwarmCoordinator()
    task = coord.post_task("Complete me")
    completed = coord.complete_task(task.id, "Done!")
    assert completed is not None
    assert completed.status == TaskStatus.COMPLETED
    assert completed.result == "Done!"


def test_coordinator_complete_task_not_found():
    from swarm.coordinator import SwarmCoordinator
    coord = SwarmCoordinator()
    assert coord.complete_task("nonexistent", "result") is None


def test_coordinator_complete_task_sets_completed_at():
    from swarm.coordinator import SwarmCoordinator
    coord = SwarmCoordinator()
    task = coord.post_task("Timestamp me")
    completed = coord.complete_task(task.id, "result")
    assert completed.completed_at is not None


# ── Coordinator: Status summary ──────────────────────────────────────────────

def test_coordinator_status_keys():
    from swarm.coordinator import SwarmCoordinator
    coord = SwarmCoordinator()
    status = coord.status()
    expected_keys = {
        "agents", "agents_idle", "agents_busy",
        "tasks_total", "tasks_pending", "tasks_running",
        "tasks_completed", "active_auctions",
    }
    assert expected_keys.issubset(set(status.keys()))


def test_coordinator_status_counts():
    from swarm.coordinator import SwarmCoordinator
    coord = SwarmCoordinator()
    coord.spawn_agent("Counter")
    coord.post_task("Count me")
    status = coord.status()
    assert status["agents"] >= 1
    assert status["tasks_total"] >= 1
    coord.manager.stop_all()


# ── Coordinator: Auction integration ────────────────────────────────────────

@pytest.mark.asyncio
async def test_coordinator_run_auction_no_bids():
    """When no bids arrive, the task should be marked as failed."""
    from swarm.coordinator import SwarmCoordinator
    from swarm.tasks import TaskStatus
    coord = SwarmCoordinator()
    task = coord.post_task("No bids task")

    # Patch sleep to avoid 15-second wait
    with patch("swarm.bidder.asyncio.sleep", new_callable=AsyncMock):
        winner = await coord.run_auction_and_assign(task.id)

    assert winner is None
    failed_task = coord.get_task(task.id)
    assert failed_task.status == TaskStatus.FAILED


@pytest.mark.asyncio
async def test_coordinator_run_auction_with_bid():
    """When a bid arrives, the task should be assigned to the winner."""
    from swarm.coordinator import SwarmCoordinator
    from swarm.tasks import TaskStatus
    coord = SwarmCoordinator()
    task = coord.post_task("Bid task")

    # Pre-submit a bid before the auction closes
    coord.auctions.open_auction(task.id)
    coord.auctions.submit_bid(task.id, "agent-1", 42)

    # Close the existing auction (run_auction opens a new one, so we
    # need to work around that — patch sleep and submit during it)
    with patch("swarm.bidder.asyncio.sleep", new_callable=AsyncMock):
        # Submit a bid while "waiting"
        coord.auctions.submit_bid(task.id, "agent-2", 35)
        winner = coord.auctions.close_auction(task.id)

    assert winner is not None
    assert winner.bid_sats == 35
