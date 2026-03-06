"""Tests for the Paperclip API routes."""

from unittest.mock import AsyncMock, patch, MagicMock

from integrations.paperclip.models import PaperclipIssue, PaperclipAgent, PaperclipGoal


# ── GET /api/paperclip/status ────────────────────────────────────────────────


def test_status_disabled(client):
    """When paperclip_enabled is False, status returns disabled."""
    response = client.get("/api/paperclip/status")
    assert response.status_code == 200
    data = response.json()
    assert data["enabled"] is False


def test_status_enabled(client):
    mock_status = MagicMock()
    mock_status.model_dump.return_value = {
        "enabled": True,
        "connected": True,
        "paperclip_url": "http://vps:3100",
        "company_id": "comp-1",
        "agent_count": 3,
        "issue_count": 5,
        "error": None,
    }
    mock_bridge = MagicMock()
    mock_bridge.get_status = AsyncMock(return_value=mock_status)
    with patch("dashboard.routes.paperclip.settings") as mock_settings:
        mock_settings.paperclip_enabled = True
        with patch.dict("sys.modules", {}):
            with patch("integrations.paperclip.bridge.bridge", mock_bridge):
                response = client.get("/api/paperclip/status")
    assert response.status_code == 200
    assert response.json()["connected"] is True


# ── GET /api/paperclip/issues ────────────────────────────────────────────────


def test_list_issues_disabled(client):
    response = client.get("/api/paperclip/issues")
    assert response.status_code == 200
    assert response.json()["enabled"] is False


# ── POST /api/paperclip/issues ───────────────────────────────────────────────


def test_create_issue_disabled(client):
    response = client.post(
        "/api/paperclip/issues",
        json={"title": "Test"},
    )
    assert response.status_code == 200
    assert response.json()["enabled"] is False


def test_create_issue_missing_title(client):
    with patch("dashboard.routes.paperclip.settings") as mock_settings:
        mock_settings.paperclip_enabled = True
        response = client.post(
            "/api/paperclip/issues",
            json={"description": "No title"},
        )
    assert response.status_code == 400
    assert "title" in response.json()["error"]


# ── POST /api/paperclip/issues/{id}/delegate ─────────────────────────────────


def test_delegate_issue_missing_agent_id(client):
    with patch("dashboard.routes.paperclip.settings") as mock_settings:
        mock_settings.paperclip_enabled = True
        response = client.post(
            "/api/paperclip/issues/i1/delegate",
            json={"message": "Do this"},
        )
    assert response.status_code == 400
    assert "agent_id" in response.json()["error"]


# ── POST /api/paperclip/issues/{id}/comment ──────────────────────────────────


def test_add_comment_missing_content(client):
    with patch("dashboard.routes.paperclip.settings") as mock_settings:
        mock_settings.paperclip_enabled = True
        response = client.post(
            "/api/paperclip/issues/i1/comment",
            json={},
        )
    assert response.status_code == 400
    assert "content" in response.json()["error"]


# ── GET /api/paperclip/agents ────────────────────────────────────────────────


def test_list_agents_disabled(client):
    response = client.get("/api/paperclip/agents")
    assert response.status_code == 200
    assert response.json()["enabled"] is False


# ── GET /api/paperclip/goals ─────────────────────────────────────────────────


def test_list_goals_disabled(client):
    response = client.get("/api/paperclip/goals")
    assert response.status_code == 200
    assert response.json()["enabled"] is False


# ── POST /api/paperclip/goals ────────────────────────────────────────────────


def test_create_goal_missing_title(client):
    with patch("dashboard.routes.paperclip.settings") as mock_settings:
        mock_settings.paperclip_enabled = True
        response = client.post(
            "/api/paperclip/goals",
            json={"description": "No title"},
        )
    assert response.status_code == 400
    assert "title" in response.json()["error"]


# ── GET /api/paperclip/approvals ─────────────────────────────────────────────


def test_list_approvals_disabled(client):
    response = client.get("/api/paperclip/approvals")
    assert response.status_code == 200
    assert response.json()["enabled"] is False


# ── GET /api/paperclip/runs ──────────────────────────────────────────────────


def test_list_runs_disabled(client):
    response = client.get("/api/paperclip/runs")
    assert response.status_code == 200
    assert response.json()["enabled"] is False
