"""Swarm manager — spawn and manage sub-agent processes.

Each sub-agent runs as a separate Python process executing agent_runner.py.
The manager tracks PIDs and provides lifecycle operations (spawn, stop, list).
"""

import logging
import subprocess
import sys
import uuid
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class ManagedAgent:
    agent_id: str
    name: str
    process: Optional[subprocess.Popen] = None
    pid: Optional[int] = None

    @property
    def alive(self) -> bool:
        if self.process is None:
            return False
        return self.process.poll() is None


class SwarmManager:
    """Manages the lifecycle of sub-agent processes."""

    def __init__(self) -> None:
        self._agents: dict[str, ManagedAgent] = {}

    def spawn(self, name: str, agent_id: Optional[str] = None) -> ManagedAgent:
        """Spawn a new sub-agent process."""
        aid = agent_id or str(uuid.uuid4())
        try:
            proc = subprocess.Popen(
                [
                    sys.executable, "-m", "swarm.agent_runner",
                    "--agent-id", aid,
                    "--name", name,
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            managed = ManagedAgent(agent_id=aid, name=name, process=proc, pid=proc.pid)
            self._agents[aid] = managed
            logger.info("Spawned agent %s (%s) — PID %d", name, aid, proc.pid)
            return managed
        except Exception as exc:
            logger.error("Failed to spawn agent %s: %s", name, exc)
            managed = ManagedAgent(agent_id=aid, name=name)
            self._agents[aid] = managed
            return managed

    def stop(self, agent_id: str) -> bool:
        """Stop a running sub-agent process."""
        managed = self._agents.get(agent_id)
        if managed is None:
            return False
        if managed.process and managed.alive:
            managed.process.terminate()
            try:
                managed.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                managed.process.kill()
            # Close pipes to avoid ResourceWarning
            if managed.process.stdout:
                managed.process.stdout.close()
            if managed.process.stderr:
                managed.process.stderr.close()
            logger.info("Stopped agent %s (%s)", managed.name, agent_id)
        del self._agents[agent_id]
        return True

    def stop_all(self) -> int:
        """Stop all running sub-agents.  Returns count of agents stopped."""
        ids = list(self._agents.keys())
        count = 0
        for aid in ids:
            if self.stop(aid):
                count += 1
        return count

    def list_agents(self) -> list[ManagedAgent]:
        return list(self._agents.values())

    def get_agent(self, agent_id: str) -> Optional[ManagedAgent]:
        return self._agents.get(agent_id)

    @property
    def count(self) -> int:
        return len(self._agents)
