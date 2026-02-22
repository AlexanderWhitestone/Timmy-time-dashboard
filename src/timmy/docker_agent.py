"""Timmy — standalone Docker container entry point.

Runs Timmy as an independent swarm participant:
  1. Registers "timmy" in the SQLite registry with capabilities
  2. Sends heartbeats every 30 s so the dashboard can track liveness
  3. Polls the coordinator for tasks assigned to "timmy"
  4. Executes them through the Agno/Ollama backend
  5. Marks each task COMPLETED (or FAILED) via the internal HTTP API

Usage (Docker)::

    COORDINATOR_URL=http://dashboard:8000 \
    OLLAMA_URL=http://host.docker.internal:11434 \
        python -m timmy.docker_agent

Environment variables
---------------------
COORDINATOR_URL   Where to reach the dashboard (required)
OLLAMA_URL        Ollama base URL (default: http://localhost:11434)
TIMMY_AGENT_ID    Override the registry ID (default: "timmy")
"""

import asyncio
import logging
import os
import signal

import httpx

from swarm import registry

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

AGENT_ID       = os.environ.get("TIMMY_AGENT_ID", "timmy")
COORDINATOR    = os.environ.get("COORDINATOR_URL", "").rstrip("/")
POLL_INTERVAL  = 5    # seconds between task polls
HEARTBEAT_INTERVAL = 30


async def _run_task(task_id: str, description: str, client: httpx.AsyncClient) -> None:
    """Execute a task using Timmy's AI backend and report the result."""
    logger.info("Timmy executing task %s: %s", task_id, description[:60])
    result = None
    try:
        from timmy.agent import create_timmy
        agent = create_timmy()
        run = agent.run(description, stream=False)
        result = run.content if hasattr(run, "content") else str(run)
        logger.info("Task %s completed", task_id)
    except Exception as exc:
        result = f"Timmy error: {exc}"
        logger.warning("Task %s failed: %s", task_id, exc)

    # Report back to coordinator via HTTP
    try:
        await client.post(
            f"{COORDINATOR}/swarm/tasks/{task_id}/complete",
            data={"result": result or "(no output)"},
        )
    except Exception as exc:
        logger.error("Could not report task %s result: %s", task_id, exc)


async def _heartbeat_loop(stop: asyncio.Event) -> None:
    while not stop.is_set():
        try:
            registry.heartbeat(AGENT_ID)
        except Exception as exc:
            logger.warning("Heartbeat error: %s", exc)
        try:
            await asyncio.wait_for(stop.wait(), timeout=HEARTBEAT_INTERVAL)
        except asyncio.TimeoutError:
            pass


async def _task_loop(stop: asyncio.Event) -> None:
    seen: set[str] = set()
    async with httpx.AsyncClient(timeout=10.0) as client:
        while not stop.is_set():
            try:
                resp = await client.get(f"{COORDINATOR}/swarm/tasks?status=assigned")
                if resp.status_code == 200:
                    for task in resp.json().get("tasks", []):
                        if task.get("assigned_agent") != AGENT_ID:
                            continue
                        task_id = task["id"]
                        if task_id in seen:
                            continue
                        seen.add(task_id)
                        asyncio.create_task(
                            _run_task(task_id, task["description"], client)
                        )
            except Exception as exc:
                logger.warning("Task poll error: %s", exc)

            try:
                await asyncio.wait_for(stop.wait(), timeout=POLL_INTERVAL)
            except asyncio.TimeoutError:
                pass


async def main() -> None:
    if not COORDINATOR:
        logger.error("COORDINATOR_URL is not set — exiting")
        return

    # Register Timmy in the shared SQLite registry
    registry.register(
        name="Timmy",
        capabilities="chat,reasoning,research,planning",
        agent_id=AGENT_ID,
    )
    logger.info("Timmy registered (id=%s) — coordinator: %s", AGENT_ID, COORDINATOR)

    stop = asyncio.Event()

    def _handle_signal(*_):
        logger.info("Timmy received shutdown signal")
        stop.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, _handle_signal)

    await asyncio.gather(
        _heartbeat_loop(stop),
        _task_loop(stop),
    )

    registry.update_status(AGENT_ID, "offline")
    logger.info("Timmy shut down")


if __name__ == "__main__":
    asyncio.run(main())
