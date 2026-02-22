"""Tests for swarm.stats — bid history persistence."""

import pytest


@pytest.fixture(autouse=True)
def tmp_swarm_db(tmp_path, monkeypatch):
    db_path = tmp_path / "swarm.db"
    monkeypatch.setattr("swarm.stats.DB_PATH", db_path)
    yield db_path


# ── record_bid ────────────────────────────────────────────────────────────────

def test_record_bid_returns_id():
    from swarm.stats import record_bid
    row_id = record_bid("task-1", "agent-1", 42)
    assert isinstance(row_id, str)
    assert len(row_id) > 0


def test_record_multiple_bids():
    from swarm.stats import record_bid, list_bids
    record_bid("task-2", "agent-A", 30)
    record_bid("task-2", "agent-B", 50)
    bids = list_bids("task-2")
    assert len(bids) == 2
    agent_ids = {b["agent_id"] for b in bids}
    assert "agent-A" in agent_ids
    assert "agent-B" in agent_ids


def test_bid_not_won_by_default():
    from swarm.stats import record_bid, list_bids
    record_bid("task-3", "agent-1", 20)
    bids = list_bids("task-3")
    assert bids[0]["won"] == 0


def test_record_bid_won_flag():
    from swarm.stats import record_bid, list_bids
    record_bid("task-4", "agent-1", 10, won=True)
    bids = list_bids("task-4")
    assert bids[0]["won"] == 1


# ── mark_winner ───────────────────────────────────────────────────────────────

def test_mark_winner_updates_row():
    from swarm.stats import record_bid, mark_winner, list_bids
    record_bid("task-5", "agent-X", 55)
    record_bid("task-5", "agent-Y", 30)
    updated = mark_winner("task-5", "agent-Y")
    assert updated >= 1
    bids = {b["agent_id"]: b for b in list_bids("task-5")}
    assert bids["agent-Y"]["won"] == 1
    assert bids["agent-X"]["won"] == 0


def test_mark_winner_nonexistent_task_returns_zero():
    from swarm.stats import mark_winner
    updated = mark_winner("no-such-task", "no-such-agent")
    assert updated == 0


# ── get_agent_stats ───────────────────────────────────────────────────────────

def test_get_agent_stats_no_bids():
    from swarm.stats import get_agent_stats
    stats = get_agent_stats("ghost-agent")
    assert stats["total_bids"] == 0
    assert stats["tasks_won"] == 0
    assert stats["total_earned"] == 0


def test_get_agent_stats_after_bids():
    from swarm.stats import record_bid, mark_winner, get_agent_stats
    record_bid("t10", "agent-Z", 40)
    record_bid("t11", "agent-Z", 55, won=True)
    mark_winner("t11", "agent-Z")
    stats = get_agent_stats("agent-Z")
    assert stats["total_bids"] == 2
    assert stats["tasks_won"] >= 1
    assert stats["total_earned"] >= 55


def test_get_agent_stats_isolates_by_agent():
    from swarm.stats import record_bid, mark_winner, get_agent_stats
    record_bid("t20", "agent-A", 20, won=True)
    record_bid("t20", "agent-B", 30)
    mark_winner("t20", "agent-A")
    stats_a = get_agent_stats("agent-A")
    stats_b = get_agent_stats("agent-B")
    assert stats_a["total_earned"] >= 20
    assert stats_b["total_earned"] == 0


# ── get_all_agent_stats ───────────────────────────────────────────────────────

def test_get_all_agent_stats_empty():
    from swarm.stats import get_all_agent_stats
    assert get_all_agent_stats() == {}


def test_get_all_agent_stats_multiple_agents():
    from swarm.stats import record_bid, get_all_agent_stats
    record_bid("t30", "alice", 10)
    record_bid("t31", "bob", 20)
    record_bid("t32", "alice", 15)
    all_stats = get_all_agent_stats()
    assert "alice" in all_stats
    assert "bob" in all_stats
    assert all_stats["alice"]["total_bids"] == 2
    assert all_stats["bob"]["total_bids"] == 1


# ── list_bids ─────────────────────────────────────────────────────────────────

def test_list_bids_all():
    from swarm.stats import record_bid, list_bids
    record_bid("t40", "a1", 10)
    record_bid("t41", "a2", 20)
    all_bids = list_bids()
    assert len(all_bids) >= 2


def test_list_bids_filtered_by_task():
    from swarm.stats import record_bid, list_bids
    record_bid("task-filter", "a1", 10)
    record_bid("task-other", "a2", 20)
    filtered = list_bids("task-filter")
    assert len(filtered) == 1
    assert filtered[0]["task_id"] == "task-filter"
