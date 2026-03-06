"""Tests for the Paperclip API client."""

from unittest.mock import AsyncMock, patch

import pytest

from integrations.paperclip.client import PaperclipClient
from integrations.paperclip.models import CreateIssueRequest


@pytest.fixture
def client():
    return PaperclipClient(base_url="http://fake:3100", api_key="test-key")


# ── health ───────────────────────────────────────────────────────────────────


async def test_healthy_returns_true_on_success(client):
    with patch.object(client, "_get", new_callable=AsyncMock, return_value={"status": "ok"}):
        assert await client.healthy() is True


async def test_healthy_returns_false_on_failure(client):
    with patch.object(client, "_get", new_callable=AsyncMock, return_value=None):
        assert await client.healthy() is False


# ── agents ───────────────────────────────────────────────────────────────────


async def test_list_agents_returns_list(client):
    raw = [{"id": "a1", "name": "Codex", "role": "engineer", "status": "active"}]
    with patch.object(client, "_get", new_callable=AsyncMock, return_value=raw):
        with patch("integrations.paperclip.client.settings") as mock_settings:
            mock_settings.paperclip_company_id = "comp-1"
            agents = await client.list_agents(company_id="comp-1")
    assert len(agents) == 1
    assert agents[0].name == "Codex"


async def test_list_agents_graceful_on_none(client):
    with patch.object(client, "_get", new_callable=AsyncMock, return_value=None):
        agents = await client.list_agents(company_id="comp-1")
    assert agents == []


# ── issues ───────────────────────────────────────────────────────────────────


async def test_list_issues(client):
    raw = [{"id": "i1", "title": "Fix bug"}]
    with patch.object(client, "_get", new_callable=AsyncMock, return_value=raw):
        issues = await client.list_issues(company_id="comp-1")
    assert len(issues) == 1
    assert issues[0].title == "Fix bug"


async def test_get_issue(client):
    raw = {"id": "i1", "title": "Fix bug", "description": "It's broken"}
    with patch.object(client, "_get", new_callable=AsyncMock, return_value=raw):
        issue = await client.get_issue("i1")
    assert issue is not None
    assert issue.id == "i1"


async def test_get_issue_not_found(client):
    with patch.object(client, "_get", new_callable=AsyncMock, return_value=None):
        issue = await client.get_issue("nonexistent")
    assert issue is None


async def test_create_issue(client):
    raw = {"id": "i2", "title": "New feature"}
    with patch.object(client, "_post", new_callable=AsyncMock, return_value=raw):
        req = CreateIssueRequest(title="New feature")
        issue = await client.create_issue(req, company_id="comp-1")
    assert issue is not None
    assert issue.id == "i2"


async def test_create_issue_no_company_id(client):
    with patch("integrations.paperclip.client.settings") as mock_settings:
        mock_settings.paperclip_company_id = ""
        issue = await client.create_issue(
            CreateIssueRequest(title="Test"),
        )
    assert issue is None


async def test_delete_issue(client):
    with patch.object(client, "_delete", new_callable=AsyncMock, return_value=True):
        result = await client.delete_issue("i1")
    assert result is True


# ── comments ─────────────────────────────────────────────────────────────────


async def test_add_comment(client):
    raw = {"id": "c1", "issue_id": "i1", "content": "Done"}
    with patch.object(client, "_post", new_callable=AsyncMock, return_value=raw):
        comment = await client.add_comment("i1", "Done")
    assert comment is not None
    assert comment.content == "Done"


async def test_list_comments(client):
    raw = [{"id": "c1", "issue_id": "i1", "content": "LGTM"}]
    with patch.object(client, "_get", new_callable=AsyncMock, return_value=raw):
        comments = await client.list_comments("i1")
    assert len(comments) == 1


# ── goals ────────────────────────────────────────────────────────────────────


async def test_list_goals(client):
    raw = [{"id": "g1", "title": "Ship MVP"}]
    with patch.object(client, "_get", new_callable=AsyncMock, return_value=raw):
        goals = await client.list_goals(company_id="comp-1")
    assert len(goals) == 1
    assert goals[0].title == "Ship MVP"


async def test_create_goal(client):
    raw = {"id": "g2", "title": "Scale to 1000 users"}
    with patch.object(client, "_post", new_callable=AsyncMock, return_value=raw):
        goal = await client.create_goal("Scale to 1000 users", company_id="comp-1")
    assert goal is not None


# ── wake agent ───────────────────────────────────────────────────────────────


async def test_wake_agent(client):
    raw = {"status": "queued"}
    with patch.object(client, "_post", new_callable=AsyncMock, return_value=raw):
        result = await client.wake_agent("a1", issue_id="i1")
    assert result == {"status": "queued"}


async def test_wake_agent_failure(client):
    with patch.object(client, "_post", new_callable=AsyncMock, return_value=None):
        result = await client.wake_agent("a1")
    assert result is None


# ── approvals ────────────────────────────────────────────────────────────────


async def test_approve(client):
    raw = {"status": "approved"}
    with patch.object(client, "_post", new_callable=AsyncMock, return_value=raw):
        result = await client.approve("ap1", comment="LGTM")
    assert result is not None


async def test_reject(client):
    raw = {"status": "rejected"}
    with patch.object(client, "_post", new_callable=AsyncMock, return_value=raw):
        result = await client.reject("ap1", comment="Needs work")
    assert result is not None


# ── heartbeat runs ───────────────────────────────────────────────────────────


async def test_list_heartbeat_runs(client):
    raw = [{"id": "r1", "agent_id": "a1", "status": "running"}]
    with patch.object(client, "_get", new_callable=AsyncMock, return_value=raw):
        runs = await client.list_heartbeat_runs(company_id="comp-1")
    assert len(runs) == 1


async def test_cancel_run(client):
    raw = {"status": "cancelled"}
    with patch.object(client, "_post", new_callable=AsyncMock, return_value=raw):
        result = await client.cancel_run("r1")
    assert result is not None
