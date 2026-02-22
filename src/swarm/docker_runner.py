"""Docker-backed agent runner — spawn swarm agents as isolated containers.

Drop-in complement to SwarmManager.  Instead of Python subprocesses,
DockerAgentRunner launches each agent as a Docker container that shares
the data volume and communicates with the coordinator over HTTP.

Requirements
------------
- Docker Engine running on the host (``docker`` CLI in PATH)
- The ``timmy-time:latest`` image already built (``make docker-build``)
- ``data/`` directory exists and is mounted at ``/app/data`` in each container

Communication
-------------
Container agents use the coordinator's internal HTTP API rather than the
in-memory SwarmComms channel::

    GET  /internal/tasks   → poll for tasks open for bidding
    POST /internal/bids    → submit a bid

The ``COORDINATOR_URL`` env var tells agents where to reach the coordinator.
Inside the docker-compose network this is ``http://dashboard:8000``.
From the host it is typically ``http://localhost:8000``.

Usage
-----
::

    from swarm.docker_runner import DockerAgentRunner

    runner = DockerAgentRunner()
    info   = runner.spawn("Echo", capabilities="summarise,translate")
    print(info)  # {"container_id": "...", "name": "Echo", "agent_id": "..."}

    runner.stop(info["container_id"])
    runner.stop_all()
"""

import logging
import subprocess
import uuid
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

DEFAULT_IMAGE = "timmy-time:latest"
DEFAULT_COORDINATOR_URL = "http://dashboard:8000"


@dataclass
class ManagedContainer:
    container_id: str
    agent_id: str
    name: str
    image: str
    capabilities: str = ""


class DockerAgentRunner:
    """Spawn and manage swarm agents as Docker containers."""

    def __init__(
        self,
        image: str = DEFAULT_IMAGE,
        coordinator_url: str = DEFAULT_COORDINATOR_URL,
        extra_env: Optional[dict] = None,
    ) -> None:
        self.image = image
        self.coordinator_url = coordinator_url
        self.extra_env = extra_env or {}
        self._containers: dict[str, ManagedContainer] = {}

    # ── Public API ────────────────────────────────────────────────────────────

    def spawn(
        self,
        name: str,
        agent_id: Optional[str] = None,
        capabilities: str = "",
        image: Optional[str] = None,
    ) -> dict:
        """Spawn a new agent container and return its info dict.

        The container runs ``python -m swarm.agent_runner`` and communicates
        with the coordinator over HTTP via ``COORDINATOR_URL``.
        """
        aid = agent_id or str(uuid.uuid4())
        img = image or self.image
        container_name = f"timmy-agent-{aid[:8]}"

        env_flags = self._build_env_flags(aid, name, capabilities)

        cmd = [
            "docker", "run",
            "--detach",
            "--name", container_name,
            "--network", "timmy-time_swarm-net",
            "--volume", "timmy-time_timmy-data:/app/data",
            "--extra-hosts", "host.docker.internal:host-gateway",
            *env_flags,
            img,
            "python", "-m", "swarm.agent_runner",
            "--agent-id", aid,
            "--name", name,
        ]

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=15
            )
            if result.returncode != 0:
                raise RuntimeError(result.stderr.strip())
            container_id = result.stdout.strip()
        except FileNotFoundError:
            raise RuntimeError(
                "Docker CLI not found.  Is Docker Desktop running?"
            )

        managed = ManagedContainer(
            container_id=container_id,
            agent_id=aid,
            name=name,
            image=img,
            capabilities=capabilities,
        )
        self._containers[container_id] = managed
        logger.info(
            "Docker agent %s (%s) started — container %s",
            name, aid, container_id[:12],
        )
        return {
            "container_id": container_id,
            "agent_id": aid,
            "name": name,
            "image": img,
            "capabilities": capabilities,
        }

    def stop(self, container_id: str) -> bool:
        """Stop and remove a container agent."""
        try:
            subprocess.run(
                ["docker", "rm", "-f", container_id],
                capture_output=True, timeout=10,
            )
            self._containers.pop(container_id, None)
            logger.info("Docker agent container %s stopped", container_id[:12])
            return True
        except Exception as exc:
            logger.error("Failed to stop container %s: %s", container_id[:12], exc)
            return False

    def stop_all(self) -> int:
        """Stop all containers managed by this runner."""
        ids = list(self._containers.keys())
        stopped = sum(1 for cid in ids if self.stop(cid))
        return stopped

    def list_containers(self) -> list[ManagedContainer]:
        return list(self._containers.values())

    def is_running(self, container_id: str) -> bool:
        """Return True if the container is currently running."""
        try:
            result = subprocess.run(
                ["docker", "inspect", "--format", "{{.State.Running}}", container_id],
                capture_output=True, text=True, timeout=5,
            )
            return result.stdout.strip() == "true"
        except Exception:
            return False

    # ── Internal ──────────────────────────────────────────────────────────────

    def _build_env_flags(self, agent_id: str, name: str, capabilities: str) -> list[str]:
        env = {
            "COORDINATOR_URL": self.coordinator_url,
            "AGENT_NAME": name,
            "AGENT_ID": agent_id,
            "AGENT_CAPABILITIES": capabilities,
            **self.extra_env,
        }
        flags = []
        for k, v in env.items():
            flags += ["--env", f"{k}={v}"]
        return flags
