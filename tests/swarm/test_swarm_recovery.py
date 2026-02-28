"""Tests for swarm.recovery — startup reconciliation logic."""

import pytest


@pytest.fixture(autouse=True)
def tmp_swarm_db(tmp_path, monkeypatch):
    """Isolate SQLite writes to a temp directory."""
    db = tmp_path / "swarm.db"
    monkeypatch.setattr("swarm.tasks.DB_PATH", db)
    monkeypatch.setattr("swarm.registry.DB_PATH", db)
    monkeypatch.setattr("swarm.stats.DB_PATH", db)
    yield db


# ── reconcile_on_startup: return shape ───────────────────────────────────────

def test_reconcile_returns_summary_keys():
    from swarm.recovery import reconcile_on_startup
    result = reconcile_on_startup()
    assert "tasks_failed" in result
    assert "agents_offlined" in result


def test_reconcile_empty_db_returns_zeros():
    from swarm.recovery import reconcile_on_startup
    result = reconcile_on_startup()
    assert result["tasks_failed"] == 0
    assert result["agents_offlined"] == 0


# ── Orphaned task rescue ──────────────────────────────────────────────────────

def test_reconcile_fails_bidding_task():
    from swarm.tasks import create_task, get_task, update_task, TaskStatus
    from swarm.recovery import reconcile_on_startup

    task = create_task("Orphaned bidding task")
    update_task(task.id, status=TaskStatus.BIDDING)

    result = reconcile_on_startup()

    assert result["tasks_failed"] == 1
    rescued = get_task(task.id)
    assert rescued.status == TaskStatus.FAILED
    assert rescued.result is not None
    assert rescued.completed_at is not None


def test_reconcile_fails_running_task():
    from swarm.tasks import create_task, get_task, update_task, TaskStatus
    from swarm.recovery import reconcile_on_startup

    task = create_task("Orphaned running task")
    update_task(task.id, status=TaskStatus.RUNNING)

    result = reconcile_on_startup()
    assert result["tasks_failed"] == 1
    assert get_task(task.id).status == TaskStatus.FAILED


def test_reconcile_fails_assigned_task():
    from swarm.tasks import create_task, get_task, update_task, TaskStatus
    from swarm.recovery import reconcile_on_startup

    task = create_task("Orphaned assigned task")
    update_task(task.id, status=TaskStatus.ASSIGNED, assigned_agent="agent-x")

    result = reconcile_on_startup()
    assert result["tasks_failed"] == 1
    assert get_task(task.id).status == TaskStatus.FAILED


def test_reconcile_leaves_pending_task_untouched():
    from swarm.tasks import create_task, get_task, TaskStatus
    from swarm.recovery import reconcile_on_startup

    task = create_task("Pending task — should survive")
    # status is PENDING by default
    reconcile_on_startup()
    assert get_task(task.id).status == TaskStatus.PENDING


def test_reconcile_leaves_completed_task_untouched():
    from swarm.tasks import create_task, update_task, get_task, TaskStatus
    from swarm.recovery import reconcile_on_startup

    task = create_task("Completed task")
    update_task(task.id, status=TaskStatus.COMPLETED, result="done")

    reconcile_on_startup()
    assert get_task(task.id).status == TaskStatus.COMPLETED


def test_reconcile_counts_multiple_orphans():
    from swarm.tasks import create_task, update_task, TaskStatus
    from swarm.recovery import reconcile_on_startup

    for status in (TaskStatus.BIDDING, TaskStatus.RUNNING, TaskStatus.ASSIGNED):
        t = create_task(f"Orphan {status}")
        update_task(t.id, status=status)

    result = reconcile_on_startup()
    assert result["tasks_failed"] == 3


# ── Stale agent offlined ──────────────────────────────────────────────────────

def test_reconcile_offlines_idle_agent():
    from swarm import registry
    from swarm.recovery import reconcile_on_startup

    agent = registry.register("IdleAgent")
    assert agent.status == "idle"

    result = reconcile_on_startup()
    assert result["agents_offlined"] == 1
    assert registry.get_agent(agent.id).status == "offline"


def test_reconcile_offlines_busy_agent():
    from swarm import registry
    from swarm.recovery import reconcile_on_startup

    agent = registry.register("BusyAgent")
    registry.update_status(agent.id, "busy")

    result = reconcile_on_startup()
    assert result["agents_offlined"] == 1
    assert registry.get_agent(agent.id).status == "offline"


def test_reconcile_skips_already_offline_agent():
    from swarm import registry
    from swarm.recovery import reconcile_on_startup

    agent = registry.register("OfflineAgent")
    registry.update_status(agent.id, "offline")

    result = reconcile_on_startup()
    assert result["agents_offlined"] == 0


def test_reconcile_counts_multiple_stale_agents():
    from swarm import registry
    from swarm.recovery import reconcile_on_startup

    registry.register("AgentA")
    registry.register("AgentB")
    registry.register("AgentC")

    result = reconcile_on_startup()
    assert result["agents_offlined"] == 3


# ── Coordinator integration ───────────────────────────────────────────────────

def test_coordinator_runs_recovery_on_init():
    """Coordinator.initialize() populates _recovery_summary."""
    from swarm.coordinator import SwarmCoordinator
    coord = SwarmCoordinator()
    coord.initialize()
    assert hasattr(coord, "_recovery_summary")
    assert "tasks_failed" in coord._recovery_summary
    assert "agents_offlined" in coord._recovery_summary
    coord.manager.stop_all()


def test_coordinator_recovery_cleans_stale_task():
    """End-to-end: task left in BIDDING is cleaned up after initialize()."""
    from swarm.tasks import create_task, get_task, update_task, TaskStatus
    from swarm.coordinator import SwarmCoordinator

    task = create_task("Stale bidding task")
    update_task(task.id, status=TaskStatus.BIDDING)

    coord = SwarmCoordinator()
    coord.initialize()
    assert get_task(task.id).status == TaskStatus.FAILED
    assert coord._recovery_summary["tasks_failed"] >= 1
    coord.manager.stop_all()
