"""Swarm coordinator — orchestrates registry, manager, and bidder.

The coordinator is the top-level entry point for swarm operations.
It ties together task creation, auction management, agent spawning,
and task assignment into a single cohesive API used by the dashboard
routes.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from swarm.bidder import AuctionManager, Bid
from swarm.comms import SwarmComms
from swarm.manager import SwarmManager
from swarm.registry import AgentRecord
from swarm import registry
from swarm import stats as swarm_stats
from swarm.tasks import (
    Task,
    TaskStatus,
    create_task,
    get_task,
    list_tasks,
    update_task,
)

logger = logging.getLogger(__name__)


class SwarmCoordinator:
    """High-level orchestrator for the swarm system."""

    def __init__(self) -> None:
        self.manager = SwarmManager()
        self.auctions = AuctionManager()
        self.comms = SwarmComms()
        self._in_process_nodes: list = []

    # ── Agent lifecycle ─────────────────────────────────────────────────────

    def spawn_agent(self, name: str, agent_id: Optional[str] = None) -> dict:
        """Spawn a new sub-agent and register it."""
        managed = self.manager.spawn(name, agent_id)
        record = registry.register(name=name, agent_id=managed.agent_id)
        return {
            "agent_id": managed.agent_id,
            "name": name,
            "pid": managed.pid,
            "status": record.status,
        }

    def stop_agent(self, agent_id: str) -> bool:
        """Stop a sub-agent and remove it from the registry."""
        registry.unregister(agent_id)
        return self.manager.stop(agent_id)

    def list_swarm_agents(self) -> list[AgentRecord]:
        return registry.list_agents()

    def spawn_persona(self, persona_id: str, agent_id: Optional[str] = None) -> dict:
        """Spawn one of the six built-in persona agents (Echo, Mace, etc.).

        The persona is registered in the SQLite registry with its full
        capabilities string and wired into the AuctionManager via the shared
        comms layer — identical to spawn_in_process_agent but with
        persona-aware bidding and a pre-defined capabilities tag.
        """
        from swarm.personas import PERSONAS
        from swarm.persona_node import PersonaNode

        if persona_id not in PERSONAS:
            raise ValueError(f"Unknown persona: {persona_id!r}. "
                             f"Choose from {list(PERSONAS)}")

        aid = agent_id or str(__import__("uuid").uuid4())
        node = PersonaNode(persona_id=persona_id, agent_id=aid, comms=self.comms)

        def _bid_and_register(msg):
            task_id = msg.data.get("task_id")
            if not task_id:
                return
            description = msg.data.get("description", "")
            # Use PersonaNode's smart bid computation
            bid_sats = node._compute_bid(description)
            self.auctions.submit_bid(task_id, aid, bid_sats)
            # Persist every bid for stats
            swarm_stats.record_bid(task_id, aid, bid_sats, won=False)
            logger.info(
                "Persona %s bid %d sats on task %s",
                node.name, bid_sats, task_id,
            )

        self.comms.subscribe("swarm:tasks", _bid_and_register)

        meta = PERSONAS[persona_id]
        record = registry.register(
            name=meta["name"],
            capabilities=meta["capabilities"],
            agent_id=aid,
        )
        self._in_process_nodes.append(node)
        logger.info("Spawned persona %s (%s)", node.name, aid)
        return {
            "agent_id": aid,
            "name": node.name,
            "persona_id": persona_id,
            "pid": None,
            "status": record.status,
        }

    def spawn_in_process_agent(
        self, name: str, agent_id: Optional[str] = None,
    ) -> dict:
        """Spawn a lightweight in-process agent that bids on tasks.

        Unlike spawn_agent (which launches a subprocess), this creates a
        SwarmNode in the current process sharing the coordinator's comms
        layer.  This means the in-memory pub/sub callbacks fire
        immediately when a task is posted, allowing the node to submit
        bids into the coordinator's AuctionManager.
        """
        from swarm.swarm_node import SwarmNode

        aid = agent_id or str(__import__("uuid").uuid4())
        node = SwarmNode(
            agent_id=aid,
            name=name,
            comms=self.comms,
        )
        # Wire the node's bid callback to feed into our AuctionManager
        original_on_task = node._on_task_posted

        def _bid_and_register(msg):
            """Intercept the task announcement, submit a bid to the auction."""
            task_id = msg.data.get("task_id")
            if not task_id:
                return
            import random
            bid_sats = random.randint(10, 100)
            self.auctions.submit_bid(task_id, aid, bid_sats)
            logger.info(
                "In-process agent %s bid %d sats on task %s",
                name, bid_sats, task_id,
            )

        # Subscribe to task announcements via shared comms
        self.comms.subscribe("swarm:tasks", _bid_and_register)

        record = registry.register(name=name, agent_id=aid)
        self._in_process_nodes.append(node)
        logger.info("Spawned in-process agent %s (%s)", name, aid)
        return {
            "agent_id": aid,
            "name": name,
            "pid": None,
            "status": record.status,
        }

    # ── Task lifecycle ──────────────────────────────────────────────────────

    def post_task(self, description: str) -> Task:
        """Create a task, open an auction, and announce it to the swarm.

        The auction is opened *before* the comms announcement so that
        in-process agents (whose callbacks fire synchronously) can
        submit bids into an already-open auction.
        """
        task = create_task(description)
        update_task(task.id, status=TaskStatus.BIDDING)
        task.status = TaskStatus.BIDDING
        # Open the auction first so bids from in-process agents land
        self.auctions.open_auction(task.id)
        self.comms.post_task(task.id, description)
        logger.info("Task posted: %s (%s)", task.id, description[:50])
        return task

    async def run_auction_and_assign(self, task_id: str) -> Optional[Bid]:
        """Wait for the bidding period, then close the auction and assign.

        The auction should already be open (via post_task).  This method
        waits the remaining bidding window and then closes it.
        """
        await asyncio.sleep(0)  # yield to let any pending callbacks fire
        winner = self.auctions.close_auction(task_id)
        if winner:
            update_task(
                task_id,
                status=TaskStatus.ASSIGNED,
                assigned_agent=winner.agent_id,
            )
            self.comms.assign_task(task_id, winner.agent_id)
            registry.update_status(winner.agent_id, "busy")
            # Mark winning bid in persistent stats
            swarm_stats.mark_winner(task_id, winner.agent_id)
            logger.info(
                "Task %s assigned to %s at %d sats",
                task_id, winner.agent_id, winner.bid_sats,
            )
        else:
            update_task(task_id, status=TaskStatus.FAILED)
            logger.warning("Task %s: no bids received, marked as failed", task_id)
        return winner

    def complete_task(self, task_id: str, result: str) -> Optional[Task]:
        """Mark a task as completed with a result."""
        task = get_task(task_id)
        if task is None:
            return None
        now = datetime.now(timezone.utc).isoformat()
        updated = update_task(
            task_id,
            status=TaskStatus.COMPLETED,
            result=result,
            completed_at=now,
        )
        if task.assigned_agent:
            registry.update_status(task.assigned_agent, "idle")
            self.comms.complete_task(task_id, task.assigned_agent, result)
        return updated

    def get_task(self, task_id: str) -> Optional[Task]:
        return get_task(task_id)

    def list_tasks(self, status: Optional[TaskStatus] = None) -> list[Task]:
        return list_tasks(status)

    # ── Convenience ─────────────────────────────────────────────────────────

    def status(self) -> dict:
        """Return a summary of the swarm state."""
        agents = registry.list_agents()
        tasks = list_tasks()
        return {
            "agents": len(agents),
            "agents_idle": sum(1 for a in agents if a.status == "idle"),
            "agents_busy": sum(1 for a in agents if a.status == "busy"),
            "tasks_total": len(tasks),
            "tasks_pending": sum(1 for t in tasks if t.status == TaskStatus.PENDING),
            "tasks_running": sum(1 for t in tasks if t.status == TaskStatus.RUNNING),
            "tasks_completed": sum(1 for t in tasks if t.status == TaskStatus.COMPLETED),
            "active_auctions": len(self.auctions.active_auctions),
        }


# Module-level singleton for use by dashboard routes
coordinator = SwarmCoordinator()
