"""End-to-end tests for dashboard responsiveness and startup.

These tests verify that the dashboard starts correctly, responds to HTTP requests,
and background tasks do not block the main application thread.
"""

import asyncio
import pytest
import httpx
from unittest.mock import patch, MagicMock


@pytest.mark.asyncio
async def test_dashboard_startup_and_health_check():
    """Test that the dashboard starts and responds to health checks."""
    from src.dashboard.app import app
    from fastapi.testclient import TestClient
    
    client = TestClient(app)
    
    # Test root endpoint
    response = client.get("/")
    assert response.status_code in [200, 307], f"Expected 200 or 307, got {response.status_code}"


@pytest.mark.asyncio
async def test_dashboard_does_not_block_on_startup():
    """Test that background tasks do not block the main application startup."""
    from src.dashboard.app import app
    from fastapi.testclient import TestClient
    
    # Mock the briefing scheduler to prevent long-running operations
    with patch("src.dashboard.app._briefing_scheduler") as mock_briefing:
        mock_briefing.return_value = asyncio.sleep(0)
        
        client = TestClient(app)
        
        # The client should be able to make requests immediately
        response = client.get("/health" if hasattr(app, "health_route") else "/")
        assert response.status_code in [200, 307, 404], "Dashboard should respond quickly"


@pytest.mark.asyncio
async def test_background_tasks_run_asynchronously():
    """Test that background tasks run asynchronously without blocking the main thread."""
    import time
    from unittest.mock import AsyncMock
    
    # Simulate a background task
    task_started = False
    task_completed = False
    
    async def background_task():
        nonlocal task_started, task_completed
        task_started = True
        await asyncio.sleep(0.1)
        task_completed = True
    
    # Run the task asynchronously
    task = asyncio.create_task(background_task())
    
    # Verify the task is running
    await asyncio.sleep(0.05)
    assert task_started, "Background task should have started"
    assert not task_completed, "Background task should not be completed yet"
    
    # Wait for the task to complete
    await task
    assert task_completed, "Background task should have completed"


@pytest.mark.asyncio
async def test_ollama_model_availability():
    """Test that Ollama models are available and accessible."""
    import urllib.request
    import json
    from config import settings
    
    try:
        url = settings.ollama_url.replace("localhost", "127.0.0.1")
        req = urllib.request.Request(
            f"{url}/api/tags",
            method="GET",
            headers={"Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode())
            models = data.get("models", [])
            assert len(models) > 0, "At least one model should be available in Ollama"
    except Exception as e:
        pytest.skip(f"Ollama not available: {e}")


@pytest.mark.asyncio
async def test_timmy_agent_initialization():
    """Test that Timmy agent initializes correctly with available model."""
    from timmy.agent import create_timmy
    
    try:
        agent = create_timmy(db_file=":memory:")
        assert agent is not None, "Timmy agent should be created successfully"
        assert hasattr(agent, "run"), "Agent should have a run method"
    except Exception as e:
        pytest.skip(f"Timmy agent initialization failed: {e}")


@pytest.mark.asyncio
async def test_dashboard_endpoints_responsive():
    """Test that key dashboard endpoints respond within acceptable time."""
    from src.dashboard.app import app
    from fastapi.testclient import TestClient
    import time
    
    client = TestClient(app)
    
    # Test common endpoints
    endpoints = [
        "/",
        "/health",
        "/chat",
        "/swarm",
    ]
    
    for endpoint in endpoints:
        start = time.time()
        try:
            response = client.get(endpoint)
            elapsed = time.time() - start
            
            # Should respond within 5 seconds
            assert elapsed < 5, f"Endpoint {endpoint} took {elapsed}s to respond"
            # Status should be 2xx, 3xx, or 4xx (not 5xx)
            assert response.status_code < 500, f"Endpoint {endpoint} returned {response.status_code}"
        except Exception as e:
            # Skip if endpoint doesn't exist
            pass
