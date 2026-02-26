"""Tests for the Task Queue system."""

import json
import os
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Set test mode before importing app modules
os.environ["TIMMY_TEST_MODE"] = "1"


# ── Model Tests ──────────────────────────────────────────────────────────


def test_create_task():
    from task_queue.models import create_task, TaskStatus, TaskPriority

    task = create_task(
        title="Test task",
        description="A test description",
        assigned_to="timmy",
        created_by="user",
        priority="normal",
    )
    assert task.id
    assert task.title == "Test task"
    assert task.status == TaskStatus.PENDING_APPROVAL
    assert task.priority == TaskPriority.NORMAL
    assert task.assigned_to == "timmy"
    assert task.created_by == "user"


def test_get_task():
    from task_queue.models import create_task, get_task

    task = create_task(title="Get me", created_by="test")
    retrieved = get_task(task.id)
    assert retrieved is not None
    assert retrieved.title == "Get me"


def test_get_task_not_found():
    from task_queue.models import get_task

    assert get_task("nonexistent-id") is None


def test_list_tasks():
    from task_queue.models import create_task, list_tasks, TaskStatus

    create_task(title="List test 1", created_by="test")
    create_task(title="List test 2", created_by="test")
    tasks = list_tasks()
    assert len(tasks) >= 2


def test_list_tasks_with_status_filter():
    from task_queue.models import (
        create_task, list_tasks, update_task_status, TaskStatus,
    )

    task = create_task(title="Filter test", created_by="test")
    update_task_status(task.id, TaskStatus.APPROVED)
    approved = list_tasks(status=TaskStatus.APPROVED)
    assert any(t.id == task.id for t in approved)


def test_update_task_status():
    from task_queue.models import (
        create_task, update_task_status, TaskStatus,
    )

    task = create_task(title="Status test", created_by="test")
    updated = update_task_status(task.id, TaskStatus.APPROVED)
    assert updated.status == TaskStatus.APPROVED


def test_update_task_running_sets_started_at():
    from task_queue.models import (
        create_task, update_task_status, TaskStatus,
    )

    task = create_task(title="Running test", created_by="test")
    updated = update_task_status(task.id, TaskStatus.RUNNING)
    assert updated.started_at is not None


def test_update_task_completed_sets_completed_at():
    from task_queue.models import (
        create_task, update_task_status, TaskStatus,
    )

    task = create_task(title="Complete test", created_by="test")
    updated = update_task_status(task.id, TaskStatus.COMPLETED, result="Done!")
    assert updated.completed_at is not None
    assert updated.result == "Done!"


def test_update_task_fields():
    from task_queue.models import create_task, update_task

    task = create_task(title="Modify test", created_by="test")
    updated = update_task(task.id, title="Modified title", priority="high")
    assert updated.title == "Modified title"
    assert updated.priority.value == "high"


def test_get_counts_by_status():
    from task_queue.models import create_task, get_counts_by_status

    create_task(title="Count test", created_by="test")
    counts = get_counts_by_status()
    assert "pending_approval" in counts


def test_get_pending_count():
    from task_queue.models import create_task, get_pending_count

    create_task(title="Pending count test", created_by="test")
    count = get_pending_count()
    assert count >= 1


def test_update_task_steps():
    from task_queue.models import create_task, update_task_steps, get_task

    task = create_task(title="Steps test", created_by="test")
    steps = [
        {"description": "Step 1", "status": "completed"},
        {"description": "Step 2", "status": "running"},
    ]
    ok = update_task_steps(task.id, steps)
    assert ok
    retrieved = get_task(task.id)
    assert len(retrieved.steps) == 2
    assert retrieved.steps[0]["description"] == "Step 1"


def test_auto_approve_not_triggered_by_default():
    from task_queue.models import create_task, TaskStatus

    task = create_task(title="No auto", created_by="user", auto_approve=False)
    assert task.status == TaskStatus.PENDING_APPROVAL


def test_get_task_summary_for_briefing():
    from task_queue.models import create_task, get_task_summary_for_briefing

    create_task(title="Briefing test", created_by="test")
    summary = get_task_summary_for_briefing()
    assert "pending_approval" in summary
    assert "total" in summary


# ── Route Tests ──────────────────────────────────────────────────────────


@pytest.fixture
def client():
    """FastAPI test client."""
    from fastapi.testclient import TestClient
    from dashboard.app import app

    return TestClient(app)


def test_tasks_page(client):
    resp = client.get("/tasks")
    assert resp.status_code == 200
    assert "TASK QUEUE" in resp.text


def test_api_list_tasks(client):
    resp = client.get("/api/tasks")
    assert resp.status_code == 200
    data = resp.json()
    assert "tasks" in data
    assert "count" in data


def test_api_create_task(client):
    resp = client.post(
        "/api/tasks",
        json={
            "title": "API created task",
            "description": "Test via API",
            "assigned_to": "timmy",
            "priority": "high",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["task"]["title"] == "API created task"
    assert data["task"]["status"] == "pending_approval"


def test_api_task_counts(client):
    resp = client.get("/api/tasks/counts")
    assert resp.status_code == 200
    data = resp.json()
    assert "pending" in data
    assert "total" in data


def test_form_create_task(client):
    resp = client.post(
        "/tasks/create",
        data={
            "title": "Form created task",
            "description": "From form",
            "assigned_to": "forge",
            "priority": "normal",
        },
    )
    assert resp.status_code == 200
    assert "Form created task" in resp.text


def test_approve_task_htmx(client):
    # Create then approve
    create_resp = client.post(
        "/api/tasks",
        json={"title": "To approve", "assigned_to": "timmy"},
    )
    task_id = create_resp.json()["task"]["id"]

    resp = client.post(f"/tasks/{task_id}/approve")
    assert resp.status_code == 200
    assert "APPROVED" in resp.text.upper() or "approved" in resp.text


def test_veto_task_htmx(client):
    create_resp = client.post(
        "/api/tasks",
        json={"title": "To veto", "assigned_to": "timmy"},
    )
    task_id = create_resp.json()["task"]["id"]

    resp = client.post(f"/tasks/{task_id}/veto")
    assert resp.status_code == 200
    assert "VETOED" in resp.text.upper() or "vetoed" in resp.text


def test_modify_task_htmx(client):
    create_resp = client.post(
        "/api/tasks",
        json={"title": "To modify", "assigned_to": "timmy"},
    )
    task_id = create_resp.json()["task"]["id"]

    resp = client.post(
        f"/tasks/{task_id}/modify",
        data={"title": "Modified via HTMX"},
    )
    assert resp.status_code == 200
    assert "Modified via HTMX" in resp.text


def test_cancel_task_htmx(client):
    create_resp = client.post(
        "/api/tasks",
        json={"title": "To cancel", "assigned_to": "timmy"},
    )
    task_id = create_resp.json()["task"]["id"]

    resp = client.post(f"/tasks/{task_id}/cancel")
    assert resp.status_code == 200


def test_retry_failed_task(client):
    from task_queue.models import create_task, update_task_status, TaskStatus

    task = create_task(title="To retry", created_by="test")
    update_task_status(task.id, TaskStatus.FAILED, result="Something broke")

    resp = client.post(f"/tasks/{task.id}/retry")
    assert resp.status_code == 200


def test_pending_partial(client):
    resp = client.get("/tasks/pending")
    assert resp.status_code == 200


def test_active_partial(client):
    resp = client.get("/tasks/active")
    assert resp.status_code == 200


def test_completed_partial(client):
    resp = client.get("/tasks/completed")
    assert resp.status_code == 200


def test_api_approve_nonexistent(client):
    resp = client.patch("/api/tasks/nonexistent/approve")
    assert resp.status_code == 404


def test_api_veto_nonexistent(client):
    resp = client.patch("/api/tasks/nonexistent/veto")
    assert resp.status_code == 404


# ── Chat-to-Task Pipeline Tests ──────────────────────────────────────────


class TestExtractTaskFromMessage:
    """Tests for _extract_task_from_message — queue intent detection."""

    def test_add_to_queue(self):
        from dashboard.routes.agents import _extract_task_from_message
        result = _extract_task_from_message("Add refactor the login to the task queue")
        assert result is not None
        assert result["agent"] == "timmy"
        assert result["priority"] == "normal"

    def test_schedule_this(self):
        from dashboard.routes.agents import _extract_task_from_message
        result = _extract_task_from_message("Schedule this for later")
        assert result is not None

    def test_create_a_task(self):
        from dashboard.routes.agents import _extract_task_from_message
        result = _extract_task_from_message("Create a task to fix the login page")
        assert result is not None
        assert "title" in result

    def test_normal_message_returns_none(self):
        from dashboard.routes.agents import _extract_task_from_message
        assert _extract_task_from_message("Hello, how are you?") is None

    def test_meta_question_about_tasks_returns_none(self):
        from dashboard.routes.agents import _extract_task_from_message
        assert _extract_task_from_message("How do I create a task?") is None

    def test_what_is_question_returns_none(self):
        from dashboard.routes.agents import _extract_task_from_message
        assert _extract_task_from_message("What is a task queue?") is None

    def test_explain_question_returns_none(self):
        from dashboard.routes.agents import _extract_task_from_message
        assert _extract_task_from_message("Can you explain how to create a task?") is None

    def test_what_would_question_returns_none(self):
        from dashboard.routes.agents import _extract_task_from_message
        assert _extract_task_from_message("What would a task flow look like?") is None


class TestExtractAgentFromMessage:
    """Tests for _extract_agent_from_message."""

    def test_extracts_forge(self):
        from dashboard.routes.agents import _extract_agent_from_message
        assert _extract_agent_from_message("Create a task for Forge to refactor") == "forge"

    def test_extracts_echo(self):
        from dashboard.routes.agents import _extract_agent_from_message
        assert _extract_agent_from_message("Add research for Echo to the queue") == "echo"

    def test_case_insensitive(self):
        from dashboard.routes.agents import _extract_agent_from_message
        assert _extract_agent_from_message("Schedule this for SEER") == "seer"

    def test_defaults_to_timmy(self):
        from dashboard.routes.agents import _extract_agent_from_message
        assert _extract_agent_from_message("Create a task to fix the bug") == "timmy"

    def test_ignores_unknown_agent(self):
        from dashboard.routes.agents import _extract_agent_from_message
        assert _extract_agent_from_message("Create a task for BobAgent") == "timmy"


class TestExtractPriorityFromMessage:
    """Tests for _extract_priority_from_message."""

    def test_urgent(self):
        from dashboard.routes.agents import _extract_priority_from_message
        assert _extract_priority_from_message("urgent: fix the server") == "urgent"

    def test_critical(self):
        from dashboard.routes.agents import _extract_priority_from_message
        assert _extract_priority_from_message("This is critical, do it now") == "urgent"

    def test_asap(self):
        from dashboard.routes.agents import _extract_priority_from_message
        assert _extract_priority_from_message("Fix this ASAP") == "urgent"

    def test_high_priority(self):
        from dashboard.routes.agents import _extract_priority_from_message
        assert _extract_priority_from_message("This is important work") == "high"

    def test_low_priority(self):
        from dashboard.routes.agents import _extract_priority_from_message
        assert _extract_priority_from_message("minor cleanup task") == "low"

    def test_default_normal(self):
        from dashboard.routes.agents import _extract_priority_from_message
        assert _extract_priority_from_message("Fix the login page") == "normal"


class TestTitleCleaning:
    """Tests for task title extraction and cleaning."""

    def test_strips_agent_from_title(self):
        from dashboard.routes.agents import _extract_task_from_message
        result = _extract_task_from_message("Create a task for Forge to refactor the login")
        assert result is not None
        assert "forge" not in result["title"].lower()
        assert "for" not in result["title"].lower().split()[0:1]  # "for" stripped

    def test_strips_priority_from_title(self):
        from dashboard.routes.agents import _extract_task_from_message
        result = _extract_task_from_message("Create an urgent task to fix the server")
        assert result is not None
        assert "urgent" not in result["title"].lower()

    def test_title_is_capitalized(self):
        from dashboard.routes.agents import _extract_task_from_message
        result = _extract_task_from_message("Add refactor the login to the task queue")
        assert result is not None
        assert result["title"][0].isupper()

    def test_title_capped_at_120_chars(self):
        from dashboard.routes.agents import _extract_task_from_message
        long_msg = "Create a task to " + "x" * 200
        result = _extract_task_from_message(long_msg)
        assert result is not None
        assert len(result["title"]) <= 120


class TestFullExtraction:
    """Tests for combined agent + priority + title extraction."""

    def test_task_includes_agent_and_priority(self):
        from dashboard.routes.agents import _extract_task_from_message
        result = _extract_task_from_message("Create a high priority task for Forge to refactor auth")
        assert result is not None
        assert result["agent"] == "forge"
        assert result["priority"] == "high"
        assert result["description"]  # original message preserved

    def test_create_with_all_fields(self):
        from dashboard.routes.agents import _extract_task_from_message
        result = _extract_task_from_message("Add an urgent task for Mace to audit security to the queue")
        assert result is not None
        assert result["agent"] == "mace"
        assert result["priority"] == "urgent"


# ── Integration: chat_timmy Route ─────────────────────────────────────────


class TestChatTimmyIntegration:
    """Integration tests for the /agents/timmy/chat route."""

    def test_chat_creates_task_on_queue_request(self, client):
        resp = client.post(
            "/agents/timmy/chat",
            data={"message": "Create a task to refactor the login module"},
        )
        assert resp.status_code == 200
        assert "Task queued" in resp.text or "task" in resp.text.lower()

    def test_chat_creates_task_with_agent(self, client):
        resp = client.post(
            "/agents/timmy/chat",
            data={"message": "Add deploy monitoring for Helm to the task queue"},
        )
        assert resp.status_code == 200
        assert "helm" in resp.text.lower() or "Task queued" in resp.text

    def test_chat_creates_task_with_priority(self, client):
        resp = client.post(
            "/agents/timmy/chat",
            data={"message": "Create an urgent task to fix the production server"},
        )
        assert resp.status_code == 200
        assert "Task queued" in resp.text or "urgent" in resp.text.lower()

    @patch("dashboard.routes.agents.timmy_chat")
    def test_chat_injects_datetime_context(self, mock_chat, client):
        mock_chat.return_value = "Hello there!"
        client.post(
            "/agents/timmy/chat",
            data={"message": "Hello Timmy"},
        )
        mock_chat.assert_called_once()
        call_arg = mock_chat.call_args[0][0]
        assert "[System: Current date/time is" in call_arg

    @patch("dashboard.routes.agents.timmy_chat")
    @patch("dashboard.routes.agents._build_queue_context")
    def test_chat_injects_queue_context_on_queue_query(self, mock_ctx, mock_chat, client):
        mock_ctx.return_value = "[System: Task queue — 3 pending approval, 1 running, 5 completed.]"
        mock_chat.return_value = "There are 3 tasks pending."
        client.post(
            "/agents/timmy/chat",
            data={"message": "What tasks are in the queue?"},
        )
        mock_ctx.assert_called_once()
        mock_chat.assert_called_once()
        call_arg = mock_chat.call_args[0][0]
        assert "[System: Task queue" in call_arg

    @patch("dashboard.routes.agents.timmy_chat")
    @patch("dashboard.routes.agents._build_queue_context")
    def test_chat_no_queue_context_for_normal_message(self, mock_ctx, mock_chat, client):
        mock_chat.return_value = "Hi!"
        client.post(
            "/agents/timmy/chat",
            data={"message": "Tell me a joke"},
        )
        mock_ctx.assert_not_called()

    @patch("dashboard.routes.agents.timmy_chat")
    def test_chat_normal_message_uses_timmy(self, mock_chat, client):
        mock_chat.return_value = "I'm doing well, thank you."
        resp = client.post(
            "/agents/timmy/chat",
            data={"message": "How are you?"},
        )
        assert resp.status_code == 200
        mock_chat.assert_called_once()


class TestBuildQueueContext:
    """Tests for _build_queue_context helper."""

    def test_returns_string_with_counts(self):
        from dashboard.routes.agents import _build_queue_context
        from task_queue.models import create_task
        create_task(title="Context test task", created_by="test")
        ctx = _build_queue_context()
        assert "[System: Task queue" in ctx
        assert "pending" in ctx.lower()

    def test_returns_empty_on_error(self):
        from dashboard.routes.agents import _build_queue_context
        with patch("task_queue.models.get_counts_by_status", side_effect=Exception("DB error")):
            ctx = _build_queue_context()
            assert isinstance(ctx, str)
            assert ctx == ""


# ── Briefing Integration ──────────────────────────────────────────────────


def test_briefing_task_queue_summary():
    """Briefing engine should include task queue data."""
    from task_queue.models import create_task
    from timmy.briefing import _gather_task_queue_summary

    create_task(title="Briefing integration test", created_by="test")
    summary = _gather_task_queue_summary()
    assert "pending" in summary.lower() or "task" in summary.lower()
