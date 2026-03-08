"""End-to-end tests for Round 4 bug fixes.

Covers: /calm, /api/queue/status, creative tabs, swarm live WS,
agent tools on /tools, notification bell /api/notifications,
and Ollama timeout parameter.
"""

from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# Fix 1: /calm no longer returns 500
# ---------------------------------------------------------------------------

def test_calm_page_returns_200(client):
    """GET /calm should render without error now that tables are created."""
    response = client.get("/calm")
    assert response.status_code == 200
    assert "Timmy Calm" in response.text


def test_calm_morning_ritual_form_returns_200(client):
    """GET /calm/ritual/morning loads the morning ritual form."""
    response = client.get("/calm/ritual/morning")
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# Fix 2: /api/queue/status endpoint exists
# ---------------------------------------------------------------------------

def test_queue_status_returns_json(client):
    """GET /api/queue/status returns valid JSON instead of 404."""
    response = client.get("/api/queue/status?assigned_to=default")
    assert response.status_code == 200
    data = response.json()
    assert "is_working" in data
    assert "current_task" in data
    assert "tasks_ahead" in data


def test_queue_status_default_idle(client):
    """Queue status shows idle when no tasks are running."""
    response = client.get("/api/queue/status")
    data = response.json()
    assert data["is_working"] is False
    assert data["current_task"] is None


def test_queue_status_reflects_running_task(client):
    """Queue status shows working when a task is running."""
    # Create a task and set it to running
    create = client.post("/api/tasks", json={
        "title": "Running task",
        "assigned_to": "default",
    })
    task_id = create.json()["id"]
    client.patch(f"/api/tasks/{task_id}/status", json={"status": "approved"})
    client.patch(f"/api/tasks/{task_id}/status", json={"status": "running"})

    response = client.get("/api/queue/status?assigned_to=default")
    data = response.json()
    assert data["is_working"] is True
    assert data["current_task"]["title"] == "Running task"


# ---------------------------------------------------------------------------
# Fix 3: Bootstrap JS present in base.html (creative tabs)
# ---------------------------------------------------------------------------

def test_base_html_has_bootstrap_js(client):
    """base.html should include bootstrap.bundle.min.js for tab switching."""
    response = client.get("/")
    assert "bootstrap.bundle.min.js" in response.text


def test_creative_page_returns_200(client):
    """GET /creative/ui should load without error."""
    response = client.get("/creative/ui")
    assert response.status_code == 200
    # Verify tab structure exists
    assert 'data-bs-toggle="tab"' in response.text


# ---------------------------------------------------------------------------
# Fix 4: Swarm Live WebSocket sends initial state
# ---------------------------------------------------------------------------

def test_swarm_live_page_returns_200(client):
    """GET /swarm/live renders the live dashboard page."""
    response = client.get("/swarm/live")
    assert response.status_code == 200


def test_swarm_live_websocket_sends_initial_state(client):
    """WebSocket at /swarm/live sends initial_state on connect."""
    import json
    with client.websocket_connect("/swarm/live") as ws:
        data = ws.receive_json()
        assert data["type"] == "initial_state"
        assert "agents" in data["data"]
        assert "tasks" in data["data"]
        assert "auctions" in data["data"]
        assert data["data"]["agents"]["total"] >= 0


# ---------------------------------------------------------------------------
# Fix 5: Agent tools populated on /tools page
# ---------------------------------------------------------------------------

def test_tools_page_returns_200(client):
    """GET /tools loads successfully."""
    response = client.get("/tools")
    assert response.status_code == 200


def test_tools_page_shows_agent_capabilities(client):
    """GET /tools should show agent capabilities, not 'No agents registered'."""
    response = client.get("/tools")
    # The tools registry always has at least the built-in tools
    # If tools are registered, we should NOT see the empty message
    from timmy.tools import get_all_available_tools
    if get_all_available_tools():
        assert "No agents registered yet" not in response.text
        assert "Timmy" in response.text


def test_tools_api_stats_returns_json(client):
    """GET /tools/api/stats returns valid JSON."""
    response = client.get("/tools/api/stats")
    assert response.status_code == 200
    data = response.json()
    assert "available_tools" in data


# ---------------------------------------------------------------------------
# Fix 6: Notification bell dropdown + /api/notifications
# ---------------------------------------------------------------------------

def test_notifications_api_returns_json(client):
    """GET /api/notifications returns a JSON array."""
    response = client.get("/api/notifications")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


def test_notifications_bell_dropdown_in_html(client):
    """The notification bell should have a dropdown container."""
    response = client.get("/")
    assert "notif-dropdown" in response.text
    assert "notif-list" in response.text


# ---------------------------------------------------------------------------
# Fix 0b: Ollama timeout parameter
# ---------------------------------------------------------------------------

def test_create_timmy_uses_timeout_not_request_timeout():
    """create_timmy() should pass timeout=300, not request_timeout."""
    with patch("timmy.agent.Ollama") as mock_ollama, \
         patch("timmy.agent.SqliteDb"), \
         patch("timmy.agent.Agent"):
        mock_ollama.return_value = MagicMock()

        from timmy.agent import create_timmy
        try:
            create_timmy()
        except Exception:
            pass

        if mock_ollama.called:
            _, kwargs = mock_ollama.call_args
            assert "request_timeout" not in kwargs, \
                "Should use 'timeout', not 'request_timeout'"
            assert kwargs.get("timeout") == 300


# ---------------------------------------------------------------------------
# Task lifecycle e2e: create → approve → run → complete
# ---------------------------------------------------------------------------

def test_task_full_lifecycle(client):
    """Test full task lifecycle: create → approve → running → completed."""
    # Create
    create = client.post("/api/tasks", json={
        "title": "Lifecycle test",
        "priority": "high",
        "assigned_to": "default",
    })
    assert create.status_code == 201
    task_id = create.json()["id"]

    # Should appear in pending
    pending = client.get("/tasks/pending")
    assert "Lifecycle test" in pending.text

    # Approve
    approve = client.patch(
        f"/api/tasks/{task_id}/status",
        json={"status": "approved"},
    )
    assert approve.status_code == 200
    assert approve.json()["status"] == "approved"

    # Should now appear in active
    active = client.get("/tasks/active")
    assert "Lifecycle test" in active.text

    # Set running
    client.patch(f"/api/tasks/{task_id}/status", json={"status": "running"})

    # Complete
    complete = client.patch(
        f"/api/tasks/{task_id}/status",
        json={"status": "completed"},
    )
    assert complete.status_code == 200
    assert complete.json()["status"] == "completed"
    assert complete.json()["completed_at"] is not None

    # Should now appear in completed
    completed = client.get("/tasks/completed")
    assert "Lifecycle test" in completed.text

    # Should no longer appear in pending or active
    pending2 = client.get("/tasks/pending")
    assert "Lifecycle test" not in pending2.text
    active2 = client.get("/tasks/active")
    assert "Lifecycle test" not in active2.text


# ---------------------------------------------------------------------------
# Pages that were broken — verify they return 200
# ---------------------------------------------------------------------------

def test_all_dashboard_pages_return_200(client):
    """Smoke test: all main dashboard routes return 200."""
    pages = [
        "/",
        "/tasks",
        "/briefing",
        "/thinking",
        "/swarm/mission-control",
        "/swarm/live",
        "/swarm/events",
        "/bugs",
        "/tools",
        "/lightning/ledger",
        "/self-modify/queue",
        "/self-coding",
        "/hands",
        "/creative/ui",
        "/calm",
    ]
    for page in pages:
        response = client.get(page)
        assert response.status_code == 200, f"{page} returned {response.status_code}"
