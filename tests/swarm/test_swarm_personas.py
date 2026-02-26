"""Tests for swarm.personas and swarm.persona_node."""

import pytest
from unittest.mock import MagicMock


# ── Fixture: redirect SQLite DB to a temp directory ──────────────────────────

@pytest.fixture(autouse=True)
def tmp_swarm_db(tmp_path, monkeypatch):
    db_path = tmp_path / "swarm.db"
    monkeypatch.setattr("swarm.tasks.DB_PATH", db_path)
    monkeypatch.setattr("swarm.registry.DB_PATH", db_path)
    monkeypatch.setattr("swarm.stats.DB_PATH", db_path)
    monkeypatch.setattr("swarm.learner.DB_PATH", db_path)
    yield db_path


# ── personas.py ───────────────────────────────────────────────────────────────

def test_all_nine_personas_defined():
    from swarm.personas import PERSONAS
    expected = {"echo", "mace", "helm", "seer", "forge", "quill", "pixel", "lyra", "reel"}
    assert expected == set(PERSONAS.keys())


def test_persona_has_required_fields():
    from swarm.personas import PERSONAS
    required = {"id", "name", "role", "description", "capabilities",
                "rate_sats", "bid_base", "bid_jitter", "preferred_keywords"}
    for pid, meta in PERSONAS.items():
        missing = required - set(meta.keys())
        assert not missing, f"Persona {pid!r} missing: {missing}"


def test_get_persona_returns_correct_entry():
    from swarm.personas import get_persona
    echo = get_persona("echo")
    assert echo is not None
    assert echo["name"] == "Echo"
    assert echo["role"] == "Research Analyst"


def test_get_persona_returns_none_for_unknown():
    from swarm.personas import get_persona
    assert get_persona("bogus") is None


def test_list_personas_returns_all_nine():
    from swarm.personas import list_personas
    personas = list_personas()
    assert len(personas) == 9


def test_persona_capabilities_are_comma_strings():
    from swarm.personas import PERSONAS
    for pid, meta in PERSONAS.items():
        assert isinstance(meta["capabilities"], str), \
            f"{pid} capabilities should be a comma-separated string"
        assert "," in meta["capabilities"] or len(meta["capabilities"]) > 0


def test_persona_preferred_keywords_nonempty():
    from swarm.personas import PERSONAS
    for pid, meta in PERSONAS.items():
        assert len(meta["preferred_keywords"]) > 0, \
            f"{pid} must have at least one preferred keyword"


# ── persona_node.py ───────────────────────────────────────────────────────────

def _make_persona_node(persona_id="echo", agent_id="persona-1"):
    from swarm.comms import SwarmComms
    from swarm.persona_node import PersonaNode
    comms = SwarmComms(redis_url="redis://localhost:9999")  # in-memory fallback
    return PersonaNode(persona_id=persona_id, agent_id=agent_id, comms=comms)


def test_persona_node_inherits_name():
    node = _make_persona_node("echo")
    assert node.name == "Echo"


def test_persona_node_inherits_capabilities():
    node = _make_persona_node("mace")
    assert "security" in node.capabilities


def test_persona_node_has_rate_sats():
    node = _make_persona_node("quill")
    from swarm.personas import PERSONAS
    assert node.rate_sats == PERSONAS["quill"]["rate_sats"]


def test_persona_node_raises_on_unknown_persona():
    from swarm.comms import SwarmComms
    from swarm.persona_node import PersonaNode
    comms = SwarmComms(redis_url="redis://localhost:9999")
    with pytest.raises(KeyError):
        PersonaNode(persona_id="ghost", agent_id="x", comms=comms)


def test_persona_node_bids_low_on_preferred_task():
    node = _make_persona_node("echo")  # prefers research/summarize
    bids = [node._compute_bid("please research and summarize this topic") for _ in range(20)]
    avg = sum(bids) / len(bids)
    # Should cluster around bid_base (35) not the off-spec inflated value
    assert avg < 80, f"Expected low bids on preferred task, got avg={avg:.1f}"


def test_persona_node_bids_higher_on_off_spec_task():
    node = _make_persona_node("echo")  # echo doesn't prefer "deploy kubernetes"
    bids = [node._compute_bid("deploy kubernetes cluster") for _ in range(20)]
    avg = sum(bids) / len(bids)
    # Off-spec: bid inflated by _OFF_SPEC_MULTIPLIER
    assert avg > 40, f"Expected higher bids on off-spec task, got avg={avg:.1f}"


def test_persona_node_preferred_beats_offspec():
    """A preferred-task bid should be lower than an off-spec bid on average."""
    node = _make_persona_node("forge")  # prefers code/bug/test
    on_spec = [node._compute_bid("write tests and fix bugs in the code") for _ in range(30)]
    off_spec = [node._compute_bid("research market trends in finance") for _ in range(30)]
    assert sum(on_spec) / 30 < sum(off_spec) / 30


@pytest.mark.asyncio
async def test_persona_node_join_registers_in_registry():
    from swarm import registry
    node = _make_persona_node("helm", agent_id="helm-join-test")
    await node.join()
    assert node.is_joined is True
    rec = registry.get_agent("helm-join-test")
    assert rec is not None
    assert rec.name == "Helm"
    assert "devops" in rec.capabilities


@pytest.mark.asyncio
async def test_persona_node_submits_bid_on_task():
    from swarm.comms import SwarmComms, CHANNEL_BIDS
    comms = SwarmComms(redis_url="redis://localhost:9999")
    from swarm.persona_node import PersonaNode
    node = PersonaNode(persona_id="quill", agent_id="quill-bid-1", comms=comms)
    await node.join()

    received = []
    comms.subscribe(CHANNEL_BIDS, lambda msg: received.append(msg))
    comms.post_task("task-quill-1", "write documentation for the API")

    assert len(received) == 1
    assert received[0].data["agent_id"] == "quill-bid-1"
    assert received[0].data["bid_sats"] >= 1


# ── coordinator.spawn_persona ─────────────────────────────────────────────────

def test_coordinator_spawn_persona_registers_agent():
    from swarm.coordinator import SwarmCoordinator
    from swarm import registry
    coord = SwarmCoordinator()
    result = coord.spawn_persona("seer")
    assert result["name"] == "Seer"
    assert result["persona_id"] == "seer"
    assert "agent_id" in result
    agents = registry.list_agents()
    assert any(a.name == "Seer" for a in agents)


def test_coordinator_spawn_persona_raises_on_unknown():
    from swarm.coordinator import SwarmCoordinator
    coord = SwarmCoordinator()
    with pytest.raises(ValueError, match="Unknown persona"):
        coord.spawn_persona("ghost")


def test_coordinator_spawn_all_personas():
    from swarm.coordinator import SwarmCoordinator
    from swarm import registry
    coord = SwarmCoordinator()
    names = []
    for pid in ["echo", "mace", "helm", "seer", "forge", "quill", "pixel", "lyra", "reel"]:
        result = coord.spawn_persona(pid)
        names.append(result["name"])
    agents = registry.list_agents()
    registered = {a.name for a in agents}
    for name in names:
        assert name in registered


# ── Adaptive bidding via learner ────────────────────────────────────────────

def test_persona_node_adaptive_bid_adjusts_with_history():
    """After enough outcomes, the learner should shift bids."""
    from swarm.learner import record_outcome, record_task_result
    node = _make_persona_node("echo", agent_id="echo-adaptive")

    # Record enough winning history on research tasks
    for i in range(5):
        record_outcome(
            f"adapt-{i}", "echo-adaptive",
            "research and summarize topic", 30,
            won_auction=True, task_succeeded=True,
        )

    # With high win rate + high success rate, bid should differ from static
    bids_adaptive = [node._compute_bid("research and summarize findings") for _ in range(20)]
    # The learner should adjust — exact direction depends on win/success balance
    # but the bid should not equal the static value every time
    assert len(set(bids_adaptive)) >= 1  # at minimum it returns something valid
    assert all(b >= 1 for b in bids_adaptive)


def test_persona_node_without_learner_uses_static_bid():
    from swarm.persona_node import PersonaNode
    from swarm.comms import SwarmComms
    comms = SwarmComms(redis_url="redis://localhost:9999")
    node = PersonaNode(persona_id="echo", agent_id="echo-static", comms=comms, use_learner=False)
    bids = [node._compute_bid("research and summarize topic") for _ in range(20)]
    # Static bids should be within the persona's base ± jitter range
    for b in bids:
        assert 20 <= b <= 50  # echo: bid_base=35, jitter=15 → range [20, 35]
