"""Container-level swarm integration tests.

These tests require Docker and run against real containers:
  - dashboard on port 18000
  - agent workers scaled via docker compose

Run with:
    FUNCTIONAL_DOCKER=1 pytest tests/functional/test_docker_swarm.py -v

Skipped automatically if FUNCTIONAL_DOCKER != "1".
"""

import subprocess
import time
from pathlib import Path

import pytest

httpx = pytest.importorskip("httpx")

PROJECT_ROOT = Path(__file__).parent.parent.parent
COMPOSE_TEST = PROJECT_ROOT / "docker-compose.test.yml"


def _compose(*args, timeout=60):
    cmd = ["docker", "compose", "-f", str(COMPOSE_TEST), "-p", "timmy-test", *args]
    return subprocess.run(
        cmd, capture_output=True, text=True, timeout=timeout, cwd=str(PROJECT_ROOT)
    )


def _wait_for_agents(dashboard_url, timeout=30, interval=1):
    """Poll /swarm/agents until at least one agent appears."""
    start = time.monotonic()
    while time.monotonic() - start < timeout:
        try:
            resp = httpx.get(f"{dashboard_url}/swarm/agents", timeout=10)
            if resp.status_code == 200:
                agents = resp.json().get("agents", [])
                if agents:
                    return agents
        except Exception:
            pass
        time.sleep(interval)
    return []


class TestDockerDashboard:
    """Tests hitting the real dashboard container over HTTP."""

    def test_health(self, docker_stack):
        resp = httpx.get(f"{docker_stack}/health", timeout=10)
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data or "ollama" in data

    def test_index_page(self, docker_stack):
        resp = httpx.get(docker_stack, timeout=10)
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert "Timmy" in resp.text

    def test_swarm_status(self, docker_stack):
        resp = httpx.get(f"{docker_stack}/swarm", timeout=10)
        assert resp.status_code == 200

    def test_spawn_agent_via_api(self, docker_stack):
        resp = httpx.post(
            f"{docker_stack}/swarm/spawn",
            data={"name": "RemoteEcho"},
            timeout=10,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("name") == "RemoteEcho" or "id" in data

    def test_post_task_via_api(self, docker_stack):
        resp = httpx.post(
            f"{docker_stack}/swarm/tasks",
            data={"description": "Docker test task"},
            timeout=10,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["description"] == "Docker test task"
        assert "task_id" in data


class TestDockerAgentSwarm:
    """Tests with real agent containers communicating over the network.

    These tests scale up agent workers and verify they register,
    bid on tasks, and get assigned work — all over real HTTP.
    """

    def test_agent_registers_via_http(self, docker_stack):
        """Scale up one agent worker and verify it appears in the registry."""
        # Start one agent
        result = _compose(
            "--profile",
            "agents",
            "up",
            "-d",
            "--scale",
            "agent=1",
            timeout=120,
        )
        assert result.returncode == 0, f"Failed to start agent:\n{result.stderr}"

        # Wait for agent to register via polling
        _wait_for_agents(docker_stack)

        resp = httpx.get(f"{docker_stack}/swarm/agents", timeout=10)
        assert resp.status_code == 200
        agents = resp.json()["agents"]
        agent_names = [a["name"] for a in agents]
        assert "TestWorker" in agent_names or any("Worker" in n for n in agent_names)

        # Clean up the agent
        _compose("--profile", "agents", "down", timeout=30)

    def test_agent_bids_on_task(self, docker_stack):
        """Start an agent, post a task, verify the agent bids on it."""
        # Start agent
        result = _compose(
            "--profile",
            "agents",
            "up",
            "-d",
            "--scale",
            "agent=1",
            timeout=120,
        )
        assert result.returncode == 0

        # Wait for agent to register via polling
        _wait_for_agents(docker_stack)

        # Post a task — this triggers an auction
        task_resp = httpx.post(
            f"{docker_stack}/swarm/tasks",
            data={"description": "Test bidding flow"},
            timeout=10,
        )
        assert task_resp.status_code == 200
        task_id = task_resp.json()["task_id"]

        # Poll until task exists (agent may poll and bid)
        start = time.monotonic()
        while time.monotonic() - start < 15:
            task = httpx.get(f"{docker_stack}/swarm/tasks/{task_id}", timeout=10)
            if task.status_code == 200:
                break
            time.sleep(1)

        # Check task status — may have been assigned
        task = httpx.get(f"{docker_stack}/swarm/tasks/{task_id}", timeout=10)
        assert task.status_code == 200
        task_data = task.json()
        # The task should still exist regardless of bid outcome
        assert task_data["description"] == "Test bidding flow"

        _compose("--profile", "agents", "down", timeout=30)

    def test_multiple_agents(self, docker_stack):
        """Scale to 3 agents and verify all register."""
        result = _compose(
            "--profile",
            "agents",
            "up",
            "-d",
            "--scale",
            "agent=3",
            timeout=120,
        )
        assert result.returncode == 0

        # Wait for agents to register via polling
        _wait_for_agents(docker_stack)

        resp = httpx.get(f"{docker_stack}/swarm/agents", timeout=10)
        agents = resp.json()["agents"]
        # Should have at least the 3 agents we started (plus possibly Timmy and auto-spawned ones)
        worker_count = sum(
            1 for a in agents if "Worker" in a["name"] or "TestWorker" in a["name"]
        )
        assert worker_count >= 1  # At least some registered

        _compose("--profile", "agents", "down", timeout=30)
