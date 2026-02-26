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
