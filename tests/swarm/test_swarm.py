"""Tests for the swarm subsystem: tasks, registry, bidder, comms, manager, coordinator."""

import os
import sqlite3
import tempfile
from unittest.mock import MagicMock, patch

import pytest


# ── Tasks CRUD ───────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def tmp_swarm_db(tmp_path, monkeypatch):
    """Point swarm SQLite to a temp directory for test isolation."""
    db_path = tmp_path / "swarm.db"
    monkeypatch.setattr("swarm.tasks.DB_PATH", db_path)
    monkeypatch.setattr("swarm.registry.DB_PATH", db_path)
    yield db_path


def test_create_task():
    from swarm.tasks import create_task
    task = create_task("Test task")
    assert task.description == "Test task"
    assert task.id is not None
    assert task.status.value == "pending"


def test_get_task():
    from swarm.tasks import create_task, get_task
    task = create_task("Find me")
    found = get_task(task.id)
    assert found is not None
    assert found.description == "Find me"


def test_get_task_not_found():
    from swarm.tasks import get_task
    assert get_task("nonexistent-id") is None


def test_list_tasks():
    from swarm.tasks import create_task, list_tasks
    create_task("Task A")
    create_task("Task B")
    tasks = list_tasks()
    assert len(tasks) >= 2


def test_list_tasks_by_status():
    from swarm.tasks import create_task, list_tasks, update_task, TaskStatus
    t = create_task("Filtered task")
    update_task(t.id, status=TaskStatus.COMPLETED)
    completed = list_tasks(status=TaskStatus.COMPLETED)
    assert any(task.id == t.id for task in completed)


def test_update_task():
    from swarm.tasks import create_task, update_task, TaskStatus
    task = create_task("Update me")
    updated = update_task(task.id, status=TaskStatus.RUNNING, assigned_agent="agent-1")
    assert updated.status == TaskStatus.RUNNING
    assert updated.assigned_agent == "agent-1"


def test_delete_task():
    from swarm.tasks import create_task, delete_task, get_task
    task = create_task("Delete me")
    assert delete_task(task.id) is True
    assert get_task(task.id) is None


def test_delete_task_not_found():
    from swarm.tasks import delete_task
    assert delete_task("nonexistent") is False


# ── Registry ─────────────────────────────────────────────────────────────────

def test_register_agent():
    from swarm.registry import register
    record = register("TestAgent", "chat,research")
    assert record.name == "TestAgent"
    assert record.capabilities == "chat,research"
    assert record.status == "idle"


def test_get_agent():
    from swarm.registry import register, get_agent
    record = register("FindMe")
    found = get_agent(record.id)
    assert found is not None
    assert found.name == "FindMe"


def test_get_agent_not_found():
    from swarm.registry import get_agent
    assert get_agent("nonexistent") is None


def test_list_agents():
    from swarm.registry import register, list_agents
    register("Agent1")
    register("Agent2")
    agents = list_agents()
    assert len(agents) >= 2


def test_unregister_agent():
    from swarm.registry import register, unregister, get_agent
    record = register("RemoveMe")
    assert unregister(record.id) is True
    assert get_agent(record.id) is None


def test_update_status():
    from swarm.registry import register, update_status
    record = register("StatusAgent")
    updated = update_status(record.id, "busy")
    assert updated.status == "busy"


def test_heartbeat():
    from swarm.registry import register, heartbeat
    record = register("HeartbeatAgent")
    updated = heartbeat(record.id)
    assert updated is not None
    assert updated.last_seen >= record.last_seen


# ── Bidder ───────────────────────────────────────────────────────────────────

def test_auction_submit_bid():
    from swarm.bidder import Auction
    auction = Auction(task_id="t1")
    assert auction.submit("agent-1", 50) is True
    assert len(auction.bids) == 1


def test_auction_close_picks_lowest():
    from swarm.bidder import Auction
    auction = Auction(task_id="t2")
    auction.submit("agent-1", 100)
    auction.submit("agent-2", 30)
    auction.submit("agent-3", 75)
    winner = auction.close()
    assert winner is not None
    assert winner.agent_id == "agent-2"
    assert winner.bid_sats == 30


def test_auction_close_no_bids():
    from swarm.bidder import Auction
    auction = Auction(task_id="t3")
    winner = auction.close()
    assert winner is None


def test_auction_reject_after_close():
    from swarm.bidder import Auction
    auction = Auction(task_id="t4")
    auction.close()
    assert auction.submit("agent-1", 50) is False


def test_auction_manager_open_and_close():
    from swarm.bidder import AuctionManager
    mgr = AuctionManager()
    mgr.open_auction("t5")
    mgr.submit_bid("t5", "agent-1", 40)
    winner = mgr.close_auction("t5")
    assert winner.agent_id == "agent-1"


def test_auction_manager_active_auctions():
    from swarm.bidder import AuctionManager
    mgr = AuctionManager()
    mgr.open_auction("t6")
    mgr.open_auction("t7")
    assert len(mgr.active_auctions) == 2
    mgr.close_auction("t6")
    assert len(mgr.active_auctions) == 1


# ── Comms ────────────────────────────────────────────────────────────────────

def test_comms_fallback_mode():
    from swarm.comms import SwarmComms
    comms = SwarmComms(redis_url="redis://localhost:9999")  # intentionally bad
    assert comms.connected is False


def test_comms_in_memory_publish():
    from swarm.comms import SwarmComms, CHANNEL_TASKS
    comms = SwarmComms(redis_url="redis://localhost:9999")
    received = []
    comms.subscribe(CHANNEL_TASKS, lambda msg: received.append(msg))
    comms.publish(CHANNEL_TASKS, "test_event", {"key": "value"})
    assert len(received) == 1
    assert received[0].event == "test_event"
    assert received[0].data["key"] == "value"


def test_comms_post_task():
    from swarm.comms import SwarmComms, CHANNEL_TASKS
    comms = SwarmComms(redis_url="redis://localhost:9999")
    received = []
    comms.subscribe(CHANNEL_TASKS, lambda msg: received.append(msg))
    comms.post_task("task-123", "Do something")
    assert len(received) == 1
    assert received[0].data["task_id"] == "task-123"


def test_comms_submit_bid():
    from swarm.comms import SwarmComms, CHANNEL_BIDS
    comms = SwarmComms(redis_url="redis://localhost:9999")
    received = []
    comms.subscribe(CHANNEL_BIDS, lambda msg: received.append(msg))
    comms.submit_bid("task-1", "agent-1", 50)
    assert len(received) == 1
    assert received[0].data["bid_sats"] == 50


# ── Manager ──────────────────────────────────────────────────────────────────

def test_manager_spawn_and_list():
    from swarm.manager import SwarmManager
    mgr = SwarmManager()
    managed = mgr.spawn("TestAgent")
    assert managed.agent_id is not None
    assert managed.name == "TestAgent"
    assert mgr.count == 1
    # Clean up
    mgr.stop_all()


def test_manager_stop():
    from swarm.manager import SwarmManager
    mgr = SwarmManager()
    managed = mgr.spawn("StopMe")
    assert mgr.stop(managed.agent_id) is True
    assert mgr.count == 0


def test_manager_stop_nonexistent():
    from swarm.manager import SwarmManager
    mgr = SwarmManager()
    assert mgr.stop("nonexistent") is False


# ── SwarmMessage serialization ───────────────────────────────────────────────

def test_swarm_message_roundtrip():
    from swarm.comms import SwarmMessage
    msg = SwarmMessage(
        channel="test", event="ping", data={"x": 1},
        timestamp="2026-01-01T00:00:00Z",
    )
    json_str = msg.to_json()
    restored = SwarmMessage.from_json(json_str)
    assert restored.channel == "test"
    assert restored.event == "ping"
    assert restored.data["x"] == 1
