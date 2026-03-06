"""Tests for the Paperclip bridge (CEO orchestration logic)."""

from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from integrations.paperclip.bridge import PaperclipBridge
from integrations.paperclip.client import PaperclipClient
from integrations.paperclip.models import PaperclipAgent, PaperclipGoal, PaperclipIssue


@pytest.fixture
def mock_client():
    client = MagicMock(spec=PaperclipClient)
    # Make all methods async
    client.healthy = AsyncMock(return_value=True)
    client.list_agents = AsyncMock(return_value=[])
    client.list_issues = AsyncMock(return_value=[])
    client.list_goals = AsyncMock(return_value=[])
    client.list_approvals = AsyncMock(return_value=[])
    client.list_heartbeat_runs = AsyncMock(return_value=[])
    client.get_issue = AsyncMock(return_value=None)
    client.get_org = AsyncMock(return_value=None)
    client.create_issue = AsyncMock(return_value=None)
    client.update_issue = AsyncMock(return_value=None)
    client.add_comment = AsyncMock(return_value=None)
    client.wake_agent = AsyncMock(return_value=None)
    client.create_goal = AsyncMock(return_value=None)
    client.approve = AsyncMock(return_value=None)
    client.reject = AsyncMock(return_value=None)
    client.cancel_run = AsyncMock(return_value=None)
    client.list_comments = AsyncMock(return_value=[])
    return client


@pytest.fixture
def bridge(mock_client):
    return PaperclipBridge(client=mock_client)


# ── status ───────────────────────────────────────────────────────────────────


async def test_status_when_disabled(bridge):
    with patch("integrations.paperclip.bridge.settings") as mock_settings:
        mock_settings.paperclip_enabled = False
        mock_settings.paperclip_url = "http://localhost:3100"
        status = await bridge.get_status()
    assert status.enabled is False


async def test_status_when_connected(bridge, mock_client):
    mock_client.healthy.return_value = True
    mock_client.list_agents.return_value = [
        PaperclipAgent(id="a1", name="Codex"),
    ]
    mock_client.list_issues.return_value = [
        PaperclipIssue(id="i1", title="Bug"),
        PaperclipIssue(id="i2", title="Feature"),
    ]

    with patch("integrations.paperclip.bridge.settings") as mock_settings:
        mock_settings.paperclip_enabled = True
        mock_settings.paperclip_url = "http://vps:3100"
        mock_settings.paperclip_company_id = "comp-1"
        status = await bridge.get_status()

    assert status.enabled is True
    assert status.connected is True
    assert status.agent_count == 1
    assert status.issue_count == 2


async def test_status_when_disconnected(bridge, mock_client):
    mock_client.healthy.return_value = False

    with patch("integrations.paperclip.bridge.settings") as mock_settings:
        mock_settings.paperclip_enabled = True
        mock_settings.paperclip_url = "http://vps:3100"
        mock_settings.paperclip_company_id = "comp-1"
        status = await bridge.get_status()

    assert status.enabled is True
    assert status.connected is False
    assert "Cannot reach" in status.error


# ── create and assign ────────────────────────────────────────────────────────


async def test_create_and_assign_with_wake(bridge, mock_client):
    issue = PaperclipIssue(id="i1", title="Deploy v2")
    mock_client.create_issue.return_value = issue
    mock_client.wake_agent.return_value = {"status": "queued"}

    result = await bridge.create_and_assign(
        title="Deploy v2",
        assignee_id="agent-codex",
        wake=True,
    )

    assert result is not None
    assert result.id == "i1"
    mock_client.wake_agent.assert_awaited_once_with("agent-codex", issue_id="i1")


async def test_create_and_assign_no_wake(bridge, mock_client):
    issue = PaperclipIssue(id="i2", title="Research task")
    mock_client.create_issue.return_value = issue

    result = await bridge.create_and_assign(
        title="Research task",
        assignee_id="agent-research",
        wake=False,
    )

    assert result is not None
    mock_client.wake_agent.assert_not_awaited()


async def test_create_and_assign_failure(bridge, mock_client):
    mock_client.create_issue.return_value = None

    result = await bridge.create_and_assign(title="Will fail")
    assert result is None


# ── delegate ─────────────────────────────────────────────────────────────────


async def test_delegate_issue(bridge, mock_client):
    mock_client.update_issue.return_value = PaperclipIssue(id="i1", title="Task")
    mock_client.wake_agent.return_value = {"status": "queued"}

    ok = await bridge.delegate_issue("i1", "agent-codex", message="Handle this")
    assert ok is True
    mock_client.add_comment.assert_awaited_once()
    mock_client.wake_agent.assert_awaited_once()


async def test_delegate_issue_update_fails(bridge, mock_client):
    mock_client.update_issue.return_value = None

    ok = await bridge.delegate_issue("i1", "agent-codex")
    assert ok is False


# ── close issue ──────────────────────────────────────────────────────────────


async def test_close_issue(bridge, mock_client):
    mock_client.update_issue.return_value = PaperclipIssue(id="i1", title="Done")

    ok = await bridge.close_issue("i1", comment="Shipped!")
    assert ok is True
    mock_client.add_comment.assert_awaited_once()


# ── goals ────────────────────────────────────────────────────────────────────


async def test_set_goal(bridge, mock_client):
    mock_client.create_goal.return_value = PaperclipGoal(id="g1", title="Ship MVP")

    goal = await bridge.set_goal("Ship MVP")
    assert goal is not None
    assert goal.title == "Ship MVP"


# ── approvals ────────────────────────────────────────────────────────────────


async def test_approve(bridge, mock_client):
    mock_client.approve.return_value = {"status": "approved"}
    ok = await bridge.approve("ap1")
    assert ok is True


async def test_reject(bridge, mock_client):
    mock_client.reject.return_value = {"status": "rejected"}
    ok = await bridge.reject("ap1", comment="Needs work")
    assert ok is True


async def test_approve_failure(bridge, mock_client):
    mock_client.approve.return_value = None
    ok = await bridge.approve("ap1")
    assert ok is False


# ── runs ─────────────────────────────────────────────────────────────────────


async def test_active_runs(bridge, mock_client):
    mock_client.list_heartbeat_runs.return_value = [
        {"id": "r1", "status": "running"},
    ]
    runs = await bridge.active_runs()
    assert len(runs) == 1


async def test_cancel_run(bridge, mock_client):
    mock_client.cancel_run.return_value = {"status": "cancelled"}
    ok = await bridge.cancel_run("r1")
    assert ok is True
