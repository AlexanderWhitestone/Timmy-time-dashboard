"""Shared fixtures for functional/E2E tests."""

import os
import subprocess
import sys
import time
import urllib.request

import pytest

# Default dashboard URL - override with DASHBOARD_URL env var
DASHBOARD_URL = os.environ.get("DASHBOARD_URL", "http://localhost:8000")


def is_server_running():
    """Check if dashboard is already running."""
    try:
        urllib.request.urlopen(f"{DASHBOARD_URL}/health", timeout=2)
        return True
    except Exception:
        return False


@pytest.fixture(scope="session")
def live_server():
    """Start the real Timmy server for E2E tests.
    
    Yields the base URL (http://localhost:8000).
    Kills the server after tests complete.
    """
    # Check if server already running
    if is_server_running():
        print(f"\n📡 Using existing server at {DASHBOARD_URL}")
        yield DASHBOARD_URL
        return
    
    # Start server in subprocess
    print(f"\n🚀 Starting server on {DASHBOARD_URL}...")
    
    env = os.environ.copy()
    env["PYTHONPATH"] = "src"
    env["TIMMY_ENV"] = "test"  # Use test config if available
    
    # Determine project root
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "dashboard.app:app", 
         "--host", "127.0.0.1", "--port", "8000",
         "--log-level", "warning"],
        cwd=project_root,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    
    # Wait for server to start
    max_retries = 30
    for i in range(max_retries):
        if is_server_running():
            print(f"✅ Server ready!")
            break
        time.sleep(1)
        print(f"⏳ Waiting for server... ({i+1}/{max_retries})")
    else:
        proc.terminate()
        proc.wait()
        raise RuntimeError("Server failed to start")
    
    yield DASHBOARD_URL
    
    # Cleanup
    print("\n🛑 Stopping server...")
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
    print("✅ Server stopped")


@pytest.fixture
def app_client():
    """FastAPI test client for functional tests.
    
    Same as the 'client' fixture in root conftest but available here.
    """
    from fastapi.testclient import TestClient
    from dashboard.app import app
    with TestClient(app) as c:
        yield c


@pytest.fixture
def timmy_runner():
    """Typer CLI runner for timmy CLI tests."""
    from typer.testing import CliRunner
    from timmy.cli import app
    yield CliRunner(), app


@pytest.fixture
def serve_runner():
    """Typer CLI runner for timmy-serve CLI tests."""
    from typer.testing import CliRunner
    from timmy_serve.cli import app
    yield CliRunner(), app


@pytest.fixture
def docker_stack():
    """Docker stack URL for container-level tests.
    
    Skips if FUNCTIONAL_DOCKER env var is not set to "1".
    """
    import os
    if os.environ.get("FUNCTIONAL_DOCKER") != "1":
        pytest.skip("Set FUNCTIONAL_DOCKER=1 to run Docker tests")
    yield "http://localhost:18000"


@pytest.fixture
def serve_client():
    """FastAPI test client for timmy-serve app."""
    pytest.importorskip("timmy_serve.app", reason="timmy_serve not available")
    from timmy_serve.app import create_timmy_serve_app
    from fastapi.testclient import TestClient
    app = create_timmy_serve_app()
    with TestClient(app) as c:
        yield c


# Add custom pytest option for headed mode
def pytest_addoption(parser):
    parser.addoption(
        "--headed",
        action="store_true",
        default=False,
        help="Run browser in non-headless mode (visible)",
    )


@pytest.fixture
def headed_mode(request):
    """Check if --headed flag was passed."""
    return request.config.getoption("--headed")


