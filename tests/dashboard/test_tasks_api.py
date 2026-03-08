"""Tests for the Task Queue API endpoints.

Verifies task CRUD operations and the dashboard page rendering.
"""


def test_tasks_page_returns_200(client):
    response = client.get("/tasks")
    assert response.status_code == 200
    assert "TASK QUEUE" in response.text


def test_create_task(client):
    """POST /api/tasks returns 201 with task JSON."""
    response = client.post("/api/tasks", json={
        "title": "Fix the memory bug",
        "priority": "high",
    })
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "Fix the memory bug"
    assert data["priority"] == "high"
    assert data["status"] == "pending_approval"
    assert "id" in data


def test_list_tasks(client):
    """GET /api/tasks returns JSON array."""
    response = client.get("/api/tasks")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_create_and_list_roundtrip(client):
    """Creating a task makes it appear in the list."""
    client.post("/api/tasks", json={"title": "Roundtrip test"})
    response = client.get("/api/tasks")
    tasks = response.json()
    assert any(t["title"] == "Roundtrip test" for t in tasks)


def test_update_task_status(client):
    """PATCH /api/tasks/{id}/status updates the task."""
    create = client.post("/api/tasks", json={"title": "To approve"})
    task_id = create.json()["id"]

    response = client.patch(
        f"/api/tasks/{task_id}/status",
        json={"status": "approved"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "approved"


def test_delete_task(client):
    """DELETE /api/tasks/{id} removes the task."""
    create = client.post("/api/tasks", json={"title": "To delete"})
    task_id = create.json()["id"]

    response = client.delete(f"/api/tasks/{task_id}")
    assert response.status_code == 200

    # Verify it's gone
    tasks = client.get("/api/tasks").json()
    assert not any(t["id"] == task_id for t in tasks)


def test_create_task_missing_title_422(client):
    """POST /api/tasks without title returns 422."""
    response = client.post("/api/tasks", json={"priority": "high"})
    assert response.status_code == 422


def test_create_task_via_form(client):
    """POST /tasks/create via form creates and returns task card HTML."""
    response = client.post("/tasks/create", data={
        "title": "Form task",
        "description": "Created via form",
        "priority": "normal",
        "assigned_to": "",
    })
    assert response.status_code == 200
    assert "Form task" in response.text


def test_pending_partial(client):
    """GET /tasks/pending returns HTML partial."""
    client.post("/api/tasks", json={"title": "Pending task"})
    response = client.get("/tasks/pending")
    assert response.status_code == 200
    assert "Pending task" in response.text
