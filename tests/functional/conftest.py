"""Functional test fixtures — real services, no mocking.

These fixtures provide:
- TestClient hitting the real FastAPI app (singletons, SQLite, etc.)
- Typer CliRunner for CLI commands
- Real temporary SQLite for swarm state
- Real payment handler with mock lightning backend (LIGHTNING_BACKEND=mock)
- Docker compose lifecycle for container-level tests
"""

import os
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

# ── Stub heavy optional deps (same as root conftest) ─────────────────────────
# These aren't mocks — they're import compatibility shims for packages
# not installed in the test environment.  The code under test handles
# their absence via try/except ImportError.
for _mod in [
    "agno", "agno.agent", "agno.models", "agno.models.ollama",
    "agno.db", "agno.db.sqlite",
    "airllm",
    "telegram", "telegram.ext",
]:
    sys.modules.setdefault(_mod, MagicMock())

os.environ["TIMMY_TEST_MODE"] = "1"


# ── Isolation: fresh coordinator state per test ───────────────────────────────

@pytest.fixture(autouse=True)
def _isolate_state():
    """Reset all singleton state between tests so they can't leak."""
    from dashboard.store import message_log
    message_log.clear()
    yield
    message_log.clear()
    from swarm.coordinator import coordinator
    coordinator.auctions._auctions.clear()
    coordinator.comms._listeners.clear()
    coordinator._in_process_nodes.clear()
    coordinator.manager.stop_all()
    try:
        from swarm import routing
        routing.routing_engine._manifests.clear()
    except Exception:
        pass


# ── TestClient with real app, no patches ──────────────────────────────────────

@pytest.fixture
def app_client(tmp_path):
    """TestClient wrapping the real dashboard app.

    Uses a tmp_path for swarm SQLite so tests don't pollute each other.
    No mocking — Ollama is offline (graceful degradation), singletons are real.
    """
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    import swarm.tasks as tasks_mod
    import swarm.registry as registry_mod
    original_tasks_db = tasks_mod.DB_PATH
    original_reg_db = registry_mod.DB_PATH

    tasks_mod.DB_PATH = data_dir / "swarm.db"
    registry_mod.DB_PATH = data_dir / "swarm.db"

    from dashboard.app import app
    with TestClient(app) as c:
        yield c

    tasks_mod.DB_PATH = original_tasks_db
    registry_mod.DB_PATH = original_reg_db


# ── Timmy-serve TestClient ────────────────────────────────────────────────────

@pytest.fixture
def serve_client():
    """TestClient wrapping the timmy-serve L402 app.

    Uses real mock-lightning backend (LIGHTNING_BACKEND=mock).
    """
    from timmy_serve.app import create_timmy_serve_app

    app = create_timmy_serve_app(price_sats=100)
    with TestClient(app) as c:
        yield c


# ── CLI runners ───────────────────────────────────────────────────────────────

@pytest.fixture
def timmy_runner():
    """Typer CliRunner + app for the `timmy` CLI."""
    from typer.testing import CliRunner
    from timmy.cli import app
    return CliRunner(), app


@pytest.fixture
def serve_runner():
    """Typer CliRunner + app for the `timmy-serve` CLI."""
    from typer.testing import CliRunner
    from timmy_serve.cli import app
    return CliRunner(), app


@pytest.fixture
def tdd_runner():
    """Typer CliRunner + app for the `self-tdd` CLI."""
    from typer.testing import CliRunner
    from self_tdd.watchdog import app
    return CliRunner(), app


# ── Docker compose lifecycle ──────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).parent.parent.parent
COMPOSE_TEST = PROJECT_ROOT / "docker-compose.test.yml"


def _compose(*args, timeout=60):
    """Run a docker compose command against the test compose file."""
    cmd = ["docker", "compose", "-f", str(COMPOSE_TEST), "-p", "timmy-test", *args]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=str(PROJECT_ROOT))


def _wait_for_healthy(url: str, retries=30, interval=2):
    """Poll a URL until it returns 200 or we run out of retries."""
    import httpx
    for i in range(retries):
        try:
            r = httpx.get(url, timeout=5)
            if r.status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(interval)
    return False


@pytest.fixture(scope="session")
def docker_stack():
    """Spin up the test compose stack once per session.

    Yields a base URL (http://localhost:18000) to hit the dashboard.
    Tears down after all tests complete.

    Skipped unless FUNCTIONAL_DOCKER=1 is set.
    """
    if not COMPOSE_TEST.exists():
        pytest.skip("docker-compose.test.yml not found")
    if os.environ.get("FUNCTIONAL_DOCKER") != "1":
        pytest.skip("Set FUNCTIONAL_DOCKER=1 to run Docker tests")

    result = _compose("up", "-d", "--build", "--wait", timeout=300)
    if result.returncode != 0:
        pytest.fail(f"docker compose up failed:\n{result.stderr}")

    base_url = "http://localhost:18000"
    if not _wait_for_healthy(f"{base_url}/health"):
        logs = _compose("logs")
        _compose("down", "-v")
        pytest.fail(f"Dashboard never became healthy:\n{logs.stdout}")

    yield base_url

    _compose("down", "-v", timeout=60)
