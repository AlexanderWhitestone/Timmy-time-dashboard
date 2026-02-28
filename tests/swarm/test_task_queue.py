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
    from swarm.task_queue.models import create_task, TaskStatus, TaskPriority

    task = create_task(
        title="Test task",
        description="A test description",
        assigned_to="timmy",
        created_by="user",
        priority="normal",
    )
    assert task.id
    assert task.title == "Test task"
    assert task.status == TaskStatus.APPROVED
    assert task.priority == TaskPriority.NORMAL
    assert task.assigned_to == "timmy"
    assert task.created_by == "user"


def test_get_task():
    from swarm.task_queue.models import create_task, get_task

    task = create_task(title="Get me", created_by="test")
    retrieved = get_task(task.id)
    assert retrieved is not None
    assert retrieved.title == "Get me"


def test_get_task_not_found():
    from swarm.task_queue.models import get_task

    assert get_task("nonexistent-id") is None


def test_list_tasks():
    from swarm.task_queue.models import create_task, list_tasks, TaskStatus

    create_task(title="List test 1", created_by="test")
    create_task(title="List test 2", created_by="test")
    tasks = list_tasks()
    assert len(tasks) >= 2


def test_list_tasks_with_status_filter():
    from swarm.task_queue.models import (
        create_task,
        list_tasks,
        update_task_status,
        TaskStatus,
    )

    task = create_task(title="Filter test", created_by="test")
    update_task_status(task.id, TaskStatus.APPROVED)
    approved = list_tasks(status=TaskStatus.APPROVED)
    assert any(t.id == task.id for t in approved)


def test_update_task_status():
    from swarm.task_queue.models import (
        create_task,
        update_task_status,
        TaskStatus,
    )

    task = create_task(title="Status test", created_by="test")
    updated = update_task_status(task.id, TaskStatus.APPROVED)
    assert updated.status == TaskStatus.APPROVED


def test_update_task_running_sets_started_at():
    from swarm.task_queue.models import (
        create_task,
        update_task_status,
        TaskStatus,
    )

    task = create_task(title="Running test", created_by="test")
    updated = update_task_status(task.id, TaskStatus.RUNNING)
    assert updated.started_at is not None


def test_update_task_completed_sets_completed_at():
    from swarm.task_queue.models import (
        create_task,
        update_task_status,
        TaskStatus,
    )

    task = create_task(title="Complete test", created_by="test")
    updated = update_task_status(task.id, TaskStatus.COMPLETED, result="Done!")
    assert updated.completed_at is not None
    assert updated.result == "Done!"


def test_update_task_fields():
    from swarm.task_queue.models import create_task, update_task

    task = create_task(title="Modify test", created_by="test")
    updated = update_task(task.id, title="Modified title", priority="high")
    assert updated.title == "Modified title"
    assert updated.priority.value == "high"


def test_get_counts_by_status():
    from swarm.task_queue.models import create_task, get_counts_by_status

    create_task(title="Count test", created_by="test")
    counts = get_counts_by_status()
    assert "approved" in counts


def test_get_pending_count():
    from swarm.task_queue.models import create_task, get_pending_count

    # Only escalations go to pending_approval
    create_task(title="Pending count test", created_by="test", task_type="escalation")
    count = get_pending_count()
    assert count >= 1


def test_update_task_steps():
    from swarm.task_queue.models import create_task, update_task_steps, get_task

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


def test_escalation_stays_pending():
    """Only escalation tasks stay in pending_approval — everything else auto-approves."""
    from swarm.task_queue.models import create_task, TaskStatus

    task = create_task(title="Escalation test", created_by="timmy", task_type="escalation")
    assert task.status == TaskStatus.PENDING_APPROVAL

    normal = create_task(title="Normal task", created_by="user")
    assert normal.status == TaskStatus.APPROVED


def test_get_task_summary_for_briefing():
    from swarm.task_queue.models import create_task, get_task_summary_for_briefing

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
    assert data["task"]["status"] == "approved"


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
    # Create an escalation (the only type that stays pending_approval)
    create_resp = client.post(
        "/api/tasks",
        json={"title": "To approve", "assigned_to": "timmy", "task_type": "escalation"},
    )
    task_id = create_resp.json()["task"]["id"]
    assert create_resp.json()["task"]["status"] == "pending_approval"

    resp = client.post(f"/tasks/{task_id}/approve")
    assert resp.status_code == 200
    assert "APPROVED" in resp.text.upper() or "approved" in resp.text


def test_veto_task_htmx(client):
    create_resp = client.post(
        "/api/tasks",
        json={"title": "To veto", "assigned_to": "timmy", "task_type": "escalation"},
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
    from swarm.task_queue.models import create_task, update_task_status, TaskStatus

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

        assert (
            _extract_task_from_message("Can you explain how to create a task?") is None
        )

    def test_what_would_question_returns_none(self):
        from dashboard.routes.agents import _extract_task_from_message

        assert _extract_task_from_message("What would a task flow look like?") is None


class TestExtractAgentFromMessage:
    """Tests for _extract_agent_from_message."""

    def test_extracts_forge(self):
        from dashboard.routes.agents import _extract_agent_from_message

        assert (
            _extract_agent_from_message("Create a task for Forge to refactor")
            == "forge"
        )

    def test_extracts_echo(self):
        from dashboard.routes.agents import _extract_agent_from_message

        assert (
            _extract_agent_from_message("Add research for Echo to the queue") == "echo"
        )

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

        result = _extract_task_from_message(
            "Create a task for Forge to refactor the login"
        )
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

        result = _extract_task_from_message(
            "Create a high priority task for Forge to refactor auth"
        )
        assert result is not None
        assert result["agent"] == "forge"
        assert result["priority"] == "high"
        assert result["description"]  # original message preserved

    def test_create_with_all_fields(self):
        from dashboard.routes.agents import _extract_task_from_message

        result = _extract_task_from_message(
            "Add an urgent task for Mace to audit security to the queue"
        )
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

    def test_chat_queues_message_for_async_processing(self, client):
        """Normal chat messages are now queued for async processing."""
        resp = client.post(
            "/agents/timmy/chat",
            data={"message": "Hello Timmy, how are you?"},
        )
        assert resp.status_code == 200
        # Should queue the message, not respond immediately
        assert "queued" in resp.text.lower() or "queue" in resp.text.lower()
        # Should show position info
        assert "position" in resp.text.lower() or "1/" in resp.text

    def test_chat_creates_chat_response_task(self, client):
        """Chat messages create a chat_response task type."""
        from swarm.task_queue.models import list_tasks, TaskStatus

        resp = client.post(
            "/agents/timmy/chat",
            data={"message": "Test message"},
        )
        assert resp.status_code == 200

        # Check that a chat_response task was created
        tasks = list_tasks(assigned_to="timmy")
        chat_tasks = [t for t in tasks if t.task_type == "chat_response"]
        assert len(chat_tasks) >= 1

    @patch("dashboard.routes.agents.timmy_chat")
    def test_chat_no_queue_context_for_normal_message(self, mock_chat, client):
        """Queue context is not built for normal queued messages."""
        mock_chat.return_value = "Hi!"
        client.post(
            "/agents/timmy/chat",
            data={"message": "Tell me a joke"},
        )
        # timmy_chat is not called directly - message is queued
        mock_chat.assert_not_called()


class TestBuildQueueContext:
    """Tests for _build_queue_context helper."""

    def test_returns_string_with_counts(self):
        from dashboard.routes.agents import _build_queue_context
        from swarm.task_queue.models import create_task

        create_task(title="Context test task", created_by="test")
        ctx = _build_queue_context()
        assert "[System: Task queue" in ctx
        assert "queued" in ctx.lower()

    def test_returns_empty_on_error(self):
        from dashboard.routes.agents import _build_queue_context

        with patch(
            "swarm.task_queue.models.get_counts_by_status",
            side_effect=Exception("DB error"),
        ):
            ctx = _build_queue_context()
            assert isinstance(ctx, str)
            assert ctx == ""


# ── Briefing Integration ──────────────────────────────────────────────────


def test_briefing_task_queue_summary():
    """Briefing engine should include task queue data."""
    from swarm.task_queue.models import create_task
    from timmy.briefing import _gather_task_queue_summary

    create_task(title="Briefing integration test", created_by="test")
    summary = _gather_task_queue_summary()
    assert "pending" in summary.lower() or "task" in summary.lower()


# ── Backlog Tests ──────────────────────────────────────────────────────────


def test_backlogged_status_exists():
    """BACKLOGGED is a valid task status."""
    from swarm.task_queue.models import TaskStatus

    assert TaskStatus.BACKLOGGED.value == "backlogged"


def test_backlog_task():
    """Tasks can be moved to backlogged status with a reason."""
    from swarm.task_queue.models import create_task, update_task_status, TaskStatus, get_task

    task = create_task(title="To backlog", created_by="test")
    updated = update_task_status(
        task.id, TaskStatus.BACKLOGGED,
        result="Backlogged: no handler",
        backlog_reason="No handler for task type: external",
    )
    assert updated.status == TaskStatus.BACKLOGGED
    refreshed = get_task(task.id)
    assert refreshed.backlog_reason == "No handler for task type: external"


def test_list_backlogged_tasks():
    """list_backlogged_tasks returns only backlogged tasks."""
    from swarm.task_queue.models import (
        create_task, update_task_status, TaskStatus, list_backlogged_tasks,
    )

    task = create_task(title="Backlog list test", created_by="test", assigned_to="timmy")
    update_task_status(
        task.id, TaskStatus.BACKLOGGED, backlog_reason="test reason",
    )
    backlogged = list_backlogged_tasks(assigned_to="timmy")
    assert any(t.id == task.id for t in backlogged)


def test_list_backlogged_tasks_filters_by_agent():
    """list_backlogged_tasks filters by assigned_to."""
    from swarm.task_queue.models import (
        create_task, update_task_status, TaskStatus, list_backlogged_tasks,
    )

    task = create_task(title="Agent filter test", created_by="test", assigned_to="forge")
    update_task_status(task.id, TaskStatus.BACKLOGGED, backlog_reason="test")
    backlogged = list_backlogged_tasks(assigned_to="echo")
    assert not any(t.id == task.id for t in backlogged)


def test_get_all_actionable_tasks():
    """get_all_actionable_tasks returns approved and pending tasks in priority order."""
    from swarm.task_queue.models import (
        create_task, update_task_status, TaskStatus, get_all_actionable_tasks,
    )

    t1 = create_task(title="Low prio", created_by="test", assigned_to="drain-test", priority="low")
    t2 = create_task(title="Urgent", created_by="test", assigned_to="drain-test", priority="urgent")
    update_task_status(t2.id, TaskStatus.APPROVED)  # Approve the urgent one

    tasks = get_all_actionable_tasks("drain-test")
    assert len(tasks) >= 2
    # Urgent should come before low
    ids = [t.id for t in tasks]
    assert ids.index(t2.id) < ids.index(t1.id)


def test_briefing_includes_backlogged():
    """Briefing summary includes backlogged count."""
    from swarm.task_queue.models import (
        create_task, update_task_status, TaskStatus, get_task_summary_for_briefing,
    )

    task = create_task(title="Briefing backlog test", created_by="test")
    update_task_status(task.id, TaskStatus.BACKLOGGED, backlog_reason="No handler")
    summary = get_task_summary_for_briefing()
    assert "backlogged" in summary
    assert "recent_backlogged" in summary


# ── Task Processor Tests ────────────────────────────────────────────────


class TestTaskProcessor:
    """Tests for the TaskProcessor drain and backlog logic."""

    @pytest.mark.asyncio
    async def test_drain_empty_queue(self):
        """drain_queue with no tasks returns zero counts."""
        from swarm.task_processor import TaskProcessor

        tp = TaskProcessor("drain-empty-test")
        summary = await tp.drain_queue()
        assert summary["processed"] == 0
        assert summary["backlogged"] == 0
        assert summary["skipped"] == 0

    @pytest.mark.asyncio
    async def test_drain_backlogs_unhandled_tasks(self):
        """Tasks with no registered handler get backlogged during drain."""
        from swarm.task_processor import TaskProcessor
        from swarm.task_queue.models import create_task, get_task, TaskStatus

        tp = TaskProcessor("drain-backlog-test")
        # No handlers registered — should backlog
        task = create_task(
            title="Unhandleable task",
            task_type="unknown_type",
            assigned_to="drain-backlog-test",
            created_by="test",
            requires_approval=False,
            auto_approve=True,
        )

        summary = await tp.drain_queue()
        assert summary["backlogged"] >= 1

        refreshed = get_task(task.id)
        assert refreshed.status == TaskStatus.BACKLOGGED
        assert refreshed.backlog_reason is not None

    @pytest.mark.asyncio
    async def test_drain_processes_handled_tasks(self):
        """Tasks with a registered handler get processed during drain."""
        from swarm.task_processor import TaskProcessor
        from swarm.task_queue.models import create_task, get_task, TaskStatus

        tp = TaskProcessor("drain-process-test")
        tp.register_handler("test_type", lambda task: "done")

        task = create_task(
            title="Handleable task",
            task_type="test_type",
            assigned_to="drain-process-test",
            created_by="test",
            requires_approval=False,
            auto_approve=True,
        )

        summary = await tp.drain_queue()
        assert summary["processed"] >= 1

        refreshed = get_task(task.id)
        assert refreshed.status == TaskStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_drain_skips_escalations(self):
        """Escalation tasks stay in pending_approval and are skipped during drain."""
        from swarm.task_processor import TaskProcessor
        from swarm.task_queue.models import create_task, get_task, TaskStatus

        tp = TaskProcessor("drain-skip-test")
        tp.register_handler("escalation", lambda task: "ok")

        task = create_task(
            title="Needs human review",
            task_type="escalation",
            assigned_to="drain-skip-test",
            created_by="timmy",
        )
        assert task.status == TaskStatus.PENDING_APPROVAL

        summary = await tp.drain_queue()
        assert summary["skipped"] >= 1

        refreshed = get_task(task.id)
        assert refreshed.status == TaskStatus.PENDING_APPROVAL

    @pytest.mark.asyncio
    async def test_process_single_task_backlogs_on_no_handler(self):
        """process_single_task backlogs when no handler is registered."""
        from swarm.task_processor import TaskProcessor
        from swarm.task_queue.models import create_task, get_task, TaskStatus

        tp = TaskProcessor("single-backlog-test")
        task = create_task(
            title="No handler",
            task_type="exotic_type",
            assigned_to="single-backlog-test",
            created_by="test",
            requires_approval=False,
        )

        result = await tp.process_single_task(task)
        assert result is None

        refreshed = get_task(task.id)
        assert refreshed.status == TaskStatus.BACKLOGGED

    @pytest.mark.asyncio
    async def test_process_single_task_backlogs_permanent_error(self):
        """process_single_task backlogs tasks with permanent errors."""
        from swarm.task_processor import TaskProcessor
        from swarm.task_queue.models import create_task, get_task, TaskStatus

        tp = TaskProcessor("perm-error-test")

        def bad_handler(task):
            raise RuntimeError("not supported operation")

        tp.register_handler("broken_type", bad_handler)
        task = create_task(
            title="Perm error",
            task_type="broken_type",
            assigned_to="perm-error-test",
            created_by="test",
            requires_approval=False,
        )

        result = await tp.process_single_task(task)
        assert result is None

        refreshed = get_task(task.id)
        assert refreshed.status == TaskStatus.BACKLOGGED

    @pytest.mark.asyncio
    async def test_process_single_task_fails_transient_error(self):
        """process_single_task marks transient errors as FAILED (retryable)."""
        from swarm.task_processor import TaskProcessor
        from swarm.task_queue.models import create_task, get_task, TaskStatus

        tp = TaskProcessor("transient-error-test")

        def flaky_handler(task):
            raise ConnectionError("Ollama connection refused")

        tp.register_handler("flaky_type", flaky_handler)
        task = create_task(
            title="Transient error",
            task_type="flaky_type",
            assigned_to="transient-error-test",
            created_by="test",
            requires_approval=False,
        )

        result = await tp.process_single_task(task)
        assert result is None

        refreshed = get_task(task.id)
        assert refreshed.status == TaskStatus.FAILED

    @pytest.mark.asyncio
    async def test_reconcile_zombie_tasks(self):
        """Zombie RUNNING tasks are reset to APPROVED on startup."""
        from swarm.task_processor import TaskProcessor
        from swarm.task_queue.models import create_task, get_task, update_task_status, TaskStatus

        tp = TaskProcessor("zombie-test")

        task = create_task(
            title="Zombie task",
            task_type="chat_response",
            assigned_to="zombie-test",
            created_by="test",
        )
        # Simulate a crash: task stuck in RUNNING
        update_task_status(task.id, TaskStatus.RUNNING)

        count = tp.reconcile_zombie_tasks()
        assert count == 1

        refreshed = get_task(task.id)
        assert refreshed.status == TaskStatus.APPROVED

    @pytest.mark.asyncio
    async def test_task_request_type_has_handler(self):
        """task_request tasks are processed (not backlogged) when a handler is registered.

        Regression test: previously task_request had no handler, causing all
        user-queued tasks from chat to be immediately backlogged.
        """
        from swarm.task_processor import TaskProcessor
        from swarm.task_queue.models import create_task, get_task, TaskStatus

        tp = TaskProcessor("task-request-test")
        tp.register_handler("task_request", lambda task: f"Completed: {task.title}")

        task = create_task(
            title="Refactor the login module",
            description="Create a task to refactor the login module",
            task_type="task_request",
            assigned_to="task-request-test",
            created_by="user",
        )

        result = await tp.process_single_task(task)
        assert result is not None

        refreshed = get_task(task.id)
        assert refreshed.status == TaskStatus.COMPLETED
        assert "Refactor" in refreshed.result

    def test_chat_queue_request_creates_task_request_type(self, client):
        """Chat messages that match queue patterns create task_request tasks."""
        from swarm.task_queue.models import list_tasks

        client.post(
            "/agents/timmy/chat",
            data={"message": "Add refactor the login module to the task queue"},
        )

        tasks = list_tasks(assigned_to="timmy")
        task_request_tasks = [t for t in tasks if t.task_type == "task_request"]
        assert len(task_request_tasks) >= 1
        assert any("login" in t.title.lower() or "refactor" in t.title.lower()
                    for t in task_request_tasks)


# ── Backlog Route Tests ─────────────────────────────────────────────────


def test_api_list_backlogged(client):
    resp = client.get("/api/tasks/backlog")
    assert resp.status_code == 200
    data = resp.json()
    assert "tasks" in data
    assert "count" in data


def test_api_unbacklog_task(client):
    from swarm.task_queue.models import create_task, update_task_status, TaskStatus

    task = create_task(title="To unbacklog", created_by="test")
    update_task_status(task.id, TaskStatus.BACKLOGGED, backlog_reason="test")

    resp = client.patch(f"/api/tasks/{task.id}/unbacklog")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["task"]["status"] == "approved"


def test_api_unbacklog_wrong_status(client):
    from swarm.task_queue.models import create_task

    task = create_task(title="Not backlogged", created_by="test")
    resp = client.patch(f"/api/tasks/{task.id}/unbacklog")
    assert resp.status_code == 400


def test_htmx_unbacklog(client):
    from swarm.task_queue.models import create_task, update_task_status, TaskStatus

    task = create_task(title="HTMX unbacklog", created_by="test")
    update_task_status(task.id, TaskStatus.BACKLOGGED, backlog_reason="test")

    resp = client.post(f"/tasks/{task.id}/unbacklog")
    assert resp.status_code == 200


def test_task_counts_include_backlogged(client):
    resp = client.get("/api/tasks/counts")
    assert resp.status_code == 200
    data = resp.json()
    assert "backlogged" in data
