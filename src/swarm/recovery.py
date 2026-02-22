"""Swarm startup recovery — reconcile SQLite state after a restart.

When the server stops unexpectedly, tasks may be left in BIDDING, ASSIGNED,
or RUNNING states, and agents may still appear as 'idle' or 'busy' in the
registry even though no live process backs them.

``reconcile_on_startup()`` is called once during coordinator initialisation.
It performs two lightweight SQLite operations:

1. **Orphaned tasks** — any task in BIDDING, ASSIGNED, or RUNNING is moved
   to FAILED with a ``result`` explaining the reason.  PENDING tasks are left
   alone (they haven't been touched yet and can be re-auctioned).

2. **Stale agents** — every agent record that is not already 'offline' is
   marked 'offline'.  Agents re-register themselves when they re-spawn; the
   coordinator singleton stays the source of truth for which nodes are live.

The function returns a summary dict useful for logging and tests.
"""

import logging
from datetime import datetime, timezone

from swarm import registry
from swarm.tasks import TaskStatus, list_tasks, update_task

logger = logging.getLogger(__name__)

#: Task statuses that indicate in-flight work that can't resume after restart.
_ORPHAN_STATUSES = {TaskStatus.BIDDING, TaskStatus.ASSIGNED, TaskStatus.RUNNING}


def reconcile_on_startup() -> dict:
    """Reconcile swarm SQLite state after a server restart.

    Returns a dict with keys:
        tasks_failed  - number of orphaned tasks moved to FAILED
        agents_offlined - number of stale agent records marked offline
    """
    tasks_failed = _rescue_orphaned_tasks()
    agents_offlined = _offline_stale_agents()

    summary = {"tasks_failed": tasks_failed, "agents_offlined": agents_offlined}

    if tasks_failed or agents_offlined:
        logger.info(
            "Swarm recovery: %d task(s) failed, %d agent(s) offlined",
            tasks_failed,
            agents_offlined,
        )
    else:
        logger.debug("Swarm recovery: nothing to reconcile")

    return summary


# ── Internal helpers ──────────────────────────────────────────────────────────


def _rescue_orphaned_tasks() -> int:
    """Move BIDDING / ASSIGNED / RUNNING tasks to FAILED.

    Returns the count of tasks updated.
    """
    now = datetime.now(timezone.utc).isoformat()
    count = 0
    for task in list_tasks():
        if task.status in _ORPHAN_STATUSES:
            update_task(
                task.id,
                status=TaskStatus.FAILED,
                result="Server restarted — task did not complete.",
                completed_at=now,
            )
            count += 1
    return count


def _offline_stale_agents() -> int:
    """Mark every non-offline agent as 'offline'.

    Returns the count of agent records updated.
    """
    agents = registry.list_agents()
    count = 0
    for agent in agents:
        if agent.status != "offline":
            registry.update_status(agent.id, "offline")
            count += 1
    return count
