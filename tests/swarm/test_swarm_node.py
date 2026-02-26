"""TDD tests for SwarmNode — agent's view of the swarm.

Written RED-first: define expected behaviour, then make it pass.
"""

import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture(autouse=True)
def tmp_swarm_db(tmp_path, monkeypatch):
    """Point swarm SQLite to a temp directory for test isolation."""
    db_path = tmp_path / "swarm.db"
    monkeypatch.setattr("swarm.tasks.DB_PATH", db_path)
    monkeypatch.setattr("swarm.registry.DB_PATH", db_path)
    yield db_path


def _make_node(agent_id="node-1", name="TestNode"):
    from swarm.comms import SwarmComms
    from swarm.swarm_node import SwarmNode
    comms = SwarmComms(redis_url="redis://localhost:9999")  # in-memory fallback
    return SwarmNode(agent_id=agent_id, name=name, comms=comms)


# ── Initial state ───────────────────────────────────────────────────────────

def test_node_not_joined_initially():
    node = _make_node()
    assert node.is_joined is False


def test_node_has_agent_id():
    node = _make_node(agent_id="abc-123")
    assert node.agent_id == "abc-123"


def test_node_has_name():
    node = _make_node(name="Echo")
    assert node.name == "Echo"


# ── Join lifecycle ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_node_join_registers_in_registry():
    from swarm import registry
    node = _make_node(agent_id="join-1", name="JoinMe")
    await node.join()
    assert node.is_joined is True
    # Should appear in the registry
    agents = registry.list_agents()
    assert any(a.id == "join-1" for a in agents)


@pytest.mark.asyncio
async def test_node_join_subscribes_to_tasks():
    from swarm.comms import CHANNEL_TASKS
    node = _make_node()
    await node.join()
    # The comms should have a listener on the tasks channel
    assert CHANNEL_TASKS in node._comms._listeners
    assert len(node._comms._listeners[CHANNEL_TASKS]) >= 1


# ── Leave lifecycle ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_node_leave_sets_offline():
    from swarm import registry
    node = _make_node(agent_id="leave-1", name="LeaveMe")
    await node.join()
    await node.leave()
    assert node.is_joined is False
    agent = registry.get_agent("leave-1")
    assert agent is not None
    assert agent.status == "offline"


# ── Task bidding ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_node_bids_on_task_posted():
    from swarm.comms import SwarmComms, CHANNEL_TASKS, CHANNEL_BIDS
    comms = SwarmComms(redis_url="redis://localhost:9999")

    from swarm.swarm_node import SwarmNode
    node = SwarmNode(agent_id="bidder-1", name="Bidder", comms=comms)
    await node.join()

    # Capture bids
    bids_received = []
    comms.subscribe(CHANNEL_BIDS, lambda msg: bids_received.append(msg))

    # Simulate a task being posted
    comms.post_task("task-abc", "Do something")

    # The node should have submitted a bid
    assert len(bids_received) == 1
    assert bids_received[0].data["agent_id"] == "bidder-1"
    assert bids_received[0].data["task_id"] == "task-abc"
    assert 10 <= bids_received[0].data["bid_sats"] <= 100


@pytest.mark.asyncio
async def test_node_ignores_task_without_id():
    from swarm.comms import SwarmComms, SwarmMessage, CHANNEL_BIDS
    comms = SwarmComms(redis_url="redis://localhost:9999")

    from swarm.swarm_node import SwarmNode
    node = SwarmNode(agent_id="ignore-1", name="Ignorer", comms=comms)
    await node.join()

    bids_received = []
    comms.subscribe(CHANNEL_BIDS, lambda msg: bids_received.append(msg))

    # Send a malformed task message (no task_id)
    msg = SwarmMessage(channel="swarm:tasks", event="task_posted", data={}, timestamp="t")
    node._on_task_posted(msg)

    assert len(bids_received) == 0


# ── Capabilities ────────────────────────────────────────────────────────────

def test_node_stores_capabilities():
    from swarm.swarm_node import SwarmNode
    node = SwarmNode(
        agent_id="cap-1", name="Capable",
        capabilities="research,coding",
    )
    assert node.capabilities == "research,coding"


@pytest.mark.asyncio
async def test_node_capabilities_in_registry():
    from swarm import registry
    from swarm.swarm_node import SwarmNode
    from swarm.comms import SwarmComms
    comms = SwarmComms(redis_url="redis://localhost:9999")
    node = SwarmNode(
        agent_id="cap-reg-1", name="CapReg",
        capabilities="security,monitoring", comms=comms,
    )
    await node.join()
    agent = registry.get_agent("cap-reg-1")
    assert agent is not None
    assert agent.capabilities == "security,monitoring"
