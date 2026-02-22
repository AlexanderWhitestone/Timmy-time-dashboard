"""Sub-agent runner — entry point for spawned swarm agents.

This module is executed as a subprocess (or Docker container) by
swarm.manager / swarm.docker_runner.  It creates a SwarmNode, joins the
registry, and waits for tasks.

Comms mode is detected automatically:

- **In-process / subprocess** (no ``COORDINATOR_URL`` env var):
  Uses the shared in-memory SwarmComms channel directly.

- **Docker container** (``COORDINATOR_URL`` is set):
  Polls ``GET /internal/tasks`` and submits bids via
  ``POST /internal/bids`` over HTTP.  No in-memory state is shared
  across the container boundary.

Usage
-----
::

    # Subprocess (existing behaviour — unchanged)
    python -m swarm.agent_runner --agent-id <id> --name <name>

    # Docker (coordinator_url injected via env)
    COORDINATOR_URL=http://dashboard:8000 \
        python -m swarm.agent_runner --agent-id <id> --name <name>
"""

import argparse
import asyncio
import logging
import os
import random
import signal

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# How often a Docker agent polls for open tasks (seconds)
_HTTP_POLL_INTERVAL = 5


# ── In-process mode ───────────────────────────────────────────────────────────

async def _run_inprocess(agent_id: str, name: str, stop: asyncio.Event) -> None:
    """Run the agent using the shared in-memory SwarmComms channel."""
    from swarm.swarm_node import SwarmNode

    node = SwarmNode(agent_id, name)
    await node.join()
    logger.info("Agent %s (%s) running (in-process mode) — waiting for tasks", name, agent_id)
    try:
        await stop.wait()
    finally:
        await node.leave()
        logger.info("Agent %s (%s) shut down", name, agent_id)


# ── HTTP (Docker) mode ────────────────────────────────────────────────────────

async def _run_http(
    agent_id: str,
    name: str,
    coordinator_url: str,
    capabilities: str,
    stop: asyncio.Event,
) -> None:
    """Run the agent by polling the coordinator's internal HTTP API."""
    try:
        import httpx
    except ImportError:
        logger.error("httpx is required for HTTP mode — install with: pip install httpx")
        return

    from swarm import registry

    # Register in SQLite so the coordinator can see us
    registry.register(name=name, capabilities=capabilities, agent_id=agent_id)
    logger.info(
        "Agent %s (%s) running (HTTP mode) — polling %s every %ds",
        name, agent_id, coordinator_url, _HTTP_POLL_INTERVAL,
    )

    base = coordinator_url.rstrip("/")
    seen_tasks: set[str] = set()

    async with httpx.AsyncClient(timeout=10.0) as client:
        while not stop.is_set():
            try:
                resp = await client.get(f"{base}/internal/tasks")
                if resp.status_code == 200:
                    tasks = resp.json()
                    for task in tasks:
                        task_id = task["task_id"]
                        if task_id in seen_tasks:
                            continue
                        seen_tasks.add(task_id)
                        bid_sats = random.randint(10, 100)
                        await client.post(
                            f"{base}/internal/bids",
                            json={
                                "task_id": task_id,
                                "agent_id": agent_id,
                                "bid_sats": bid_sats,
                                "capabilities": capabilities,
                            },
                        )
                        logger.info(
                            "Agent %s bid %d sats on task %s",
                            name, bid_sats, task_id,
                        )
            except Exception as exc:
                logger.warning("HTTP poll error: %s", exc)

            try:
                await asyncio.wait_for(stop.wait(), timeout=_HTTP_POLL_INTERVAL)
            except asyncio.TimeoutError:
                pass  # normal — just means the stop event wasn't set

    registry.update_status(agent_id, "offline")
    logger.info("Agent %s (%s) shut down", name, agent_id)


# ── Entry point ───────────────────────────────────────────────────────────────

async def main() -> None:
    parser = argparse.ArgumentParser(description="Swarm sub-agent runner")
    parser.add_argument("--agent-id", required=True, help="Unique agent identifier")
    parser.add_argument("--name", required=True, help="Human-readable agent name")
    args = parser.parse_args()

    agent_id = args.agent_id
    name = args.name
    coordinator_url = os.environ.get("COORDINATOR_URL", "")
    capabilities = os.environ.get("AGENT_CAPABILITIES", "")

    stop = asyncio.Event()

    def _handle_signal(*_):
        logger.info("Agent %s received shutdown signal", name)
        stop.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, _handle_signal)

    if coordinator_url:
        await _run_http(agent_id, name, coordinator_url, capabilities, stop)
    else:
        await _run_inprocess(agent_id, name, stop)


if __name__ == "__main__":
    asyncio.run(main())
