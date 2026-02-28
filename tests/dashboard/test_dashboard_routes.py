"""Tests for new dashboard routes: swarm, marketplace, voice, mobile, shortcuts."""

import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from dashboard.app import app
    with TestClient(app) as c:
        yield c


# ── Swarm routes ─────────────────────────────────────────────────────────────

def test_swarm_status(client):
    response = client.get("/swarm")
    assert response.status_code == 200
    data = response.json()
    assert "agents" in data
    assert "tasks_total" in data


def test_swarm_list_agents(client):
    response = client.get("/swarm/agents")
    assert response.status_code == 200
    assert "agents" in response.json()


def test_swarm_spawn_agent(client):
    response = client.post("/swarm/spawn", data={"name": "TestBot"})
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "TestBot"
    assert "agent_id" in data


def test_swarm_list_tasks(client):
    response = client.get("/swarm/tasks")
    assert response.status_code == 200
    assert "tasks" in response.json()


def test_swarm_post_task(client):
    response = client.post("/swarm/tasks", data={"description": "Research Bitcoin"})
    assert response.status_code == 200
    data = response.json()
    assert data["description"] == "Research Bitcoin"
    assert data["status"] == "bidding"


def test_swarm_get_task(client):
    # Create a task first
    create_resp = client.post("/swarm/tasks", data={"description": "Find me"})
    task_id = create_resp.json()["task_id"]
    # Retrieve it
    response = client.get(f"/swarm/tasks/{task_id}")
    assert response.status_code == 200
    assert response.json()["description"] == "Find me"


def test_swarm_get_task_not_found(client):
    response = client.get("/swarm/tasks/nonexistent")
    assert response.status_code == 200
    assert "error" in response.json()


# ── Marketplace routes ───────────────────────────────────────────────────────

def test_marketplace_list(client):
    response = client.get("/marketplace")
    assert response.status_code == 200
    data = response.json()
    assert "agents" in data
    assert data["total"] >= 7  # Timmy + 6 planned personas


def test_marketplace_has_timmy(client):
    response = client.get("/marketplace")
    agents = response.json()["agents"]
    timmy = next((a for a in agents if a["id"] == "timmy"), None)
    assert timmy is not None
    assert timmy["status"] == "active"
    assert timmy["rate_sats"] == 0


def test_marketplace_has_planned_agents(client):
    response = client.get("/marketplace")
    data = response.json()
    # Total should be 10 (1 Timmy + 9 personas)
    assert data["total"] == 10
    # planned_count + active_count should equal total
    assert data["planned_count"] + data["active_count"] == data["total"]
    # Timmy should always be in the active list
    timmy = next((a for a in data["agents"] if a["id"] == "timmy"), None)
    assert timmy is not None
    assert timmy["status"] == "active"


def test_marketplace_agent_detail(client):
    response = client.get("/marketplace/echo")
    assert response.status_code == 200
    assert response.json()["name"] == "Echo"


def test_marketplace_agent_not_found(client):
    response = client.get("/marketplace/nonexistent")
    assert response.status_code == 200
    assert "error" in response.json()


# ── Voice routes ─────────────────────────────────────────────────────────────

def test_voice_nlu(client):
    response = client.post("/voice/nlu", data={"text": "What is your status?"})
    assert response.status_code == 200
    data = response.json()
    assert data["intent"] == "status"
    assert data["confidence"] >= 0.8


def test_voice_nlu_chat_fallback(client):
    response = client.post("/voice/nlu", data={"text": "Tell me about Bitcoin"})
    assert response.status_code == 200
    assert response.json()["intent"] == "chat"


def test_voice_tts_status(client):
    response = client.get("/voice/tts/status")
    assert response.status_code == 200
    assert "available" in response.json()


# ── Mobile routes ────────────────────────────────────────────────────────────

def test_mobile_dashboard(client):
    response = client.get("/mobile")
    assert response.status_code == 200
    assert "TIMMY TIME" in response.text


def test_mobile_status(client):
    with patch("dashboard.routes.health.check_ollama", new_callable=AsyncMock, return_value=True):
        response = client.get("/mobile/status")
    assert response.status_code == 200
    data = response.json()
    assert data["agent"] == "timmy"
    assert data["ready"] is True


# ── Shortcuts route ──────────────────────────────────────────────────────────

def test_shortcuts_setup(client):
    response = client.get("/shortcuts/setup")
    assert response.status_code == 200
    data = response.json()
    assert "title" in data
    assert "actions" in data
    assert len(data["actions"]) >= 4


# ── Marketplace UI route ──────────────────────────────────────────────────────

def test_marketplace_ui_renders_html(client):
    response = client.get("/marketplace/ui")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Agent Marketplace" in response.text


def test_marketplace_ui_shows_all_agents(client):
    response = client.get("/marketplace/ui")
    assert response.status_code == 200
    # All seven catalog entries should appear
    for name in ["Timmy", "Echo", "Mace", "Helm", "Seer", "Forge", "Quill"]:
        assert name in response.text, f"{name} not found in marketplace UI"


def test_marketplace_ui_shows_timmy_free(client):
    response = client.get("/marketplace/ui")
    assert "FREE" in response.text


def test_marketplace_ui_shows_planned_status(client):
    response = client.get("/marketplace/ui")
    # Personas not yet in registry show as "planned"
    assert "planned" in response.text


def test_marketplace_ui_shows_active_timmy(client):
    response = client.get("/marketplace/ui")
    # Timmy is always active even without registry entry
    assert "active" in response.text


# ── Marketplace enriched data ─────────────────────────────────────────────────

def test_marketplace_enriched_includes_stats_fields(client):
    response = client.get("/marketplace")
    agents = response.json()["agents"]
    for a in agents:
        assert "tasks_completed" in a, f"Missing tasks_completed in {a['id']}"
        assert "total_earned" in a, f"Missing total_earned in {a['id']}"


def test_marketplace_persona_spawned_changes_status(client):
    """Spawning a persona into the registry changes its marketplace status."""
    # Spawn Echo via swarm route (or ensure it's already spawned)
    spawn_resp = client.post("/swarm/spawn", data={"name": "Echo"})
    assert spawn_resp.status_code == 200

    # Echo should now show as idle (or busy) in the marketplace
    resp = client.get("/marketplace")
    agents = {a["id"]: a for a in resp.json()["agents"]}
    assert agents["echo"]["status"] in ("idle", "busy")
