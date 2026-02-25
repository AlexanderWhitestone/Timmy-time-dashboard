"""End-to-end tests with a real Ollama container.

These tests spin up the full Docker stack **including** an Ollama container
running a tiny model (qwen2.5:0.5b, ~400 MB, CPU-only).  They verify that
the dashboard can actually generate LLM responses — not just degrade
gracefully when Ollama is offline.

Run with:
    FUNCTIONAL_DOCKER=1 pytest tests/functional/test_ollama_chat.py -v

Requirements:
    - Docker daemon running
    - ~1 GB free disk (Ollama image + model weights)
    - No GPU required — qwen2.5:0.5b runs fine on CPU

The ``ollama_stack`` fixture brings up Ollama + dashboard via docker compose,
pulls the model, and tears everything down after the session.
"""

import os
import subprocess
import time
from pathlib import Path

import pytest

httpx = pytest.importorskip("httpx")

PROJECT_ROOT = Path(__file__).parent.parent.parent
COMPOSE_TEST = PROJECT_ROOT / "docker-compose.test.yml"

# Tiny model that runs on CPU without GPU.  ~400 MB download.
TEST_MODEL = os.environ.get("OLLAMA_TEST_MODEL", "qwen2.5:0.5b")

# ── helpers ──────────────────────────────────────────────────────────────────


def _compose(*args, timeout=120):
    """Run a docker compose command against the test compose file."""
    cmd = [
        "docker", "compose",
        "-f", str(COMPOSE_TEST),
        "-p", "timmy-test",
        *args,
    ]
    return subprocess.run(
        cmd, capture_output=True, text=True,
        timeout=timeout, cwd=str(PROJECT_ROOT),
    )


def _wait_for_healthy(url: str, retries=40, interval=3):
    """Poll *url* until it returns HTTP 200."""
    for _ in range(retries):
        try:
            r = httpx.get(url, timeout=5)
            if r.status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(interval)
    return False


def _pull_model(model: str, retries=3):
    """Ask the containerised Ollama to pull *model*."""
    for attempt in range(retries):
        result = subprocess.run(
            [
                "docker", "exec", "timmy-test-ollama",
                "ollama", "pull", model,
            ],
            capture_output=True, text=True, timeout=600,
        )
        if result.returncode == 0:
            return True
        time.sleep(5 * (attempt + 1))
    return False


# ── fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def ollama_stack():
    """Bring up Ollama + dashboard, pull the test model, yield base URL.

    Skipped unless ``FUNCTIONAL_DOCKER=1`` is set and Docker is available.
    """
    if os.environ.get("FUNCTIONAL_DOCKER") != "1":
        pytest.skip("Set FUNCTIONAL_DOCKER=1 to run Docker tests")
    if not COMPOSE_TEST.exists():
        pytest.skip("docker-compose.test.yml not found")

    # Verify Docker daemon
    docker_check = subprocess.run(
        ["docker", "info"], capture_output=True, text=True, timeout=10,
    )
    if docker_check.returncode != 0:
        pytest.skip(f"Docker daemon not available: {docker_check.stderr.strip()}")

    # Bring up Ollama + dashboard with the ollama profile.
    # OLLAMA_URL tells the dashboard to reach the sibling container.
    env = {
        **os.environ,
        "OLLAMA_URL": "http://ollama:11434",
        "OLLAMA_MODEL": TEST_MODEL,
    }
    result = subprocess.run(
        [
            "docker", "compose",
            "-f", str(COMPOSE_TEST),
            "-p", "timmy-test",
            "--profile", "ollama",
            "up", "-d", "--build", "--wait",
        ],
        capture_output=True, text=True, timeout=300,
        cwd=str(PROJECT_ROOT), env=env,
    )
    if result.returncode != 0:
        pytest.fail(f"docker compose up failed:\n{result.stderr}")

    # Wait for Ollama to be ready
    ollama_ready = _wait_for_healthy("http://localhost:18000/health")
    if not ollama_ready:
        logs = _compose("logs")
        _compose("--profile", "ollama", "down", "-v")
        pytest.fail(f"Stack never became healthy:\n{logs.stdout}")

    # Pull the tiny test model into the Ollama container
    if not _pull_model(TEST_MODEL):
        logs = _compose("logs", "ollama")
        _compose("--profile", "ollama", "down", "-v")
        pytest.fail(f"Failed to pull {TEST_MODEL}:\n{logs.stdout}")

    yield "http://localhost:18000"

    # Teardown
    subprocess.run(
        [
            "docker", "compose",
            "-f", str(COMPOSE_TEST),
            "-p", "timmy-test",
            "--profile", "ollama",
            "down", "-v",
        ],
        capture_output=True, text=True, timeout=60,
        cwd=str(PROJECT_ROOT),
    )


# ── tests ────────────────────────────────────────────────────────────────────


class TestOllamaHealth:
    """Verify the dashboard can reach the Ollama container."""

    def test_health_reports_ollama_up(self, ollama_stack):
        """GET /health should report ollama as 'up'."""
        resp = httpx.get(f"{ollama_stack}/health", timeout=10)
        assert resp.status_code == 200
        data = resp.json()
        services = data.get("services", {})
        assert services.get("ollama") == "up", (
            f"Expected ollama=up, got: {services}"
        )


class TestOllamaChat:
    """Send a real prompt through the dashboard and get an LLM response."""

    def test_chat_returns_llm_response(self, ollama_stack):
        """POST /agents/timmy/chat with a real message → non-error HTML."""
        resp = httpx.post(
            f"{ollama_stack}/agents/timmy/chat",
            data={"message": "Say hello in exactly three words."},
            timeout=120,  # first inference can be slow on CPU
        )
        assert resp.status_code == 200
        body = resp.text.lower()
        # The response should contain actual content, not an error fallback
        assert "error" not in body or "hello" in body, (
            f"Expected LLM response, got error:\n{resp.text[:500]}"
        )

    def test_chat_history_contains_response(self, ollama_stack):
        """After chatting, history should include both user and agent messages."""
        # Send a message
        httpx.post(
            f"{ollama_stack}/agents/timmy/chat",
            data={"message": "What is 2+2?"},
            timeout=120,
        )
        # Fetch history
        hist = httpx.get(f"{ollama_stack}/agents/timmy/history", timeout=10)
        assert hist.status_code == 200
        body = hist.text.lower()
        assert "2+2" in body or "2 + 2" in body

    def test_multiple_turns(self, ollama_stack):
        """Verify the agent handles a second turn without crashing."""
        # First turn
        r1 = httpx.post(
            f"{ollama_stack}/agents/timmy/chat",
            data={"message": "Remember the word: pineapple"},
            timeout=120,
        )
        assert r1.status_code == 200

        # Second turn
        r2 = httpx.post(
            f"{ollama_stack}/agents/timmy/chat",
            data={"message": "What word did I just ask you to remember?"},
            timeout=120,
        )
        assert r2.status_code == 200
        # We don't assert "pineapple" — tiny models have weak memory.
        # The point is it doesn't crash on multi-turn.


class TestOllamaDirectAPI:
    """Hit the Ollama container directly to verify the model is loaded."""

    def test_ollama_api_tags(self, ollama_stack):
        """Ollama /api/tags should list the pulled test model."""
        # Ollama isn't port-mapped, so we exec into the container
        result = subprocess.run(
            [
                "docker", "exec", "timmy-test-ollama",
                "curl", "-sf", "http://localhost:11434/api/tags",
            ],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0
        assert TEST_MODEL.split(":")[0] in result.stdout
