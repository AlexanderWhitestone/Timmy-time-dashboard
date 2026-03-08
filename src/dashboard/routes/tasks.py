"""Task Queue routes — SQLite-backed CRUD for the task management dashboard."""

import logging
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse

from dashboard.templating import templates

logger = logging.getLogger(__name__)

router = APIRouter(tags=["tasks"])

# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

DB_PATH = Path("data/tasks.db")

VALID_STATUSES = {
    "pending_approval", "approved", "running", "paused",
    "completed", "vetoed", "failed", "backlogged",
}
VALID_PRIORITIES = {"low", "normal", "high", "urgent"}


def _get_db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            description TEXT DEFAULT '',
            status TEXT DEFAULT 'pending_approval',
            priority TEXT DEFAULT 'normal',
            assigned_to TEXT DEFAULT '',
            created_by TEXT DEFAULT 'operator',
            result TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now')),
            completed_at TEXT
        )
    """)
    conn.commit()
    return conn


def _row_to_dict(row: sqlite3.Row) -> dict:
    return dict(row)


class _EnumLike:
    """Thin wrapper so Jinja templates can use task.status.value."""

    def __init__(self, v: str):
        self.value = v

    def __str__(self):
        return self.value

    def __eq__(self, other):
        if isinstance(other, str):
            return self.value == other
        return NotImplemented


class _TaskView:
    """Lightweight view object for Jinja template rendering."""

    def __init__(self, row: dict):
        self.id = row["id"]
        self.title = row.get("title", "")
        self.description = row.get("description", "")
        self.status = _EnumLike(row.get("status", "pending_approval"))
        self.priority = _EnumLike(row.get("priority", "normal"))
        self.assigned_to = row.get("assigned_to", "")
        self.created_by = row.get("created_by", "operator")
        self.result = row.get("result", "")
        self.created_at = row.get("created_at", "")
        self.completed_at = row.get("completed_at")
        self.steps = []  # reserved for future use


# ---------------------------------------------------------------------------
# Page routes
# ---------------------------------------------------------------------------

@router.get("/tasks", response_class=HTMLResponse)
async def tasks_page(request: Request):
    """Render the main task queue page with 3-column layout."""
    db = _get_db()
    try:
        pending = [_TaskView(_row_to_dict(r)) for r in db.execute(
            "SELECT * FROM tasks WHERE status IN ('pending_approval') ORDER BY created_at DESC"
        ).fetchall()]
        active = [_TaskView(_row_to_dict(r)) for r in db.execute(
            "SELECT * FROM tasks WHERE status IN ('approved','running','paused') ORDER BY created_at DESC"
        ).fetchall()]
        completed = [_TaskView(_row_to_dict(r)) for r in db.execute(
            "SELECT * FROM tasks WHERE status IN ('completed','vetoed','failed') ORDER BY completed_at DESC LIMIT 50"
        ).fetchall()]
    finally:
        db.close()

    return templates.TemplateResponse(request, "tasks.html", {
        "pending_count": len(pending),
        "pending": pending,
        "active": active,
        "completed": completed,
        "agents": [],  # no agent roster wired yet
        "pre_assign": "",
    })


# ---------------------------------------------------------------------------
# HTMX partials (polled by the template)
# ---------------------------------------------------------------------------

@router.get("/tasks/pending", response_class=HTMLResponse)
async def tasks_pending(request: Request):
    db = _get_db()
    try:
        rows = db.execute(
            "SELECT * FROM tasks WHERE status='pending_approval' ORDER BY created_at DESC"
        ).fetchall()
    finally:
        db.close()
    tasks = [_TaskView(_row_to_dict(r)) for r in rows]
    parts = []
    for task in tasks:
        parts.append(templates.TemplateResponse(
            request, "partials/task_card.html", {"task": task}
        ).body.decode())
    if not parts:
        return HTMLResponse('<div class="empty-column">No pending tasks</div>')
    return HTMLResponse("".join(parts))


@router.get("/tasks/active", response_class=HTMLResponse)
async def tasks_active(request: Request):
    db = _get_db()
    try:
        rows = db.execute(
            "SELECT * FROM tasks WHERE status IN ('approved','running','paused') ORDER BY created_at DESC"
        ).fetchall()
    finally:
        db.close()
    tasks = [_TaskView(_row_to_dict(r)) for r in rows]
    parts = []
    for task in tasks:
        parts.append(templates.TemplateResponse(
            request, "partials/task_card.html", {"task": task}
        ).body.decode())
    if not parts:
        return HTMLResponse('<div class="empty-column">No active tasks</div>')
    return HTMLResponse("".join(parts))


@router.get("/tasks/completed", response_class=HTMLResponse)
async def tasks_completed(request: Request):
    db = _get_db()
    try:
        rows = db.execute(
            "SELECT * FROM tasks WHERE status IN ('completed','vetoed','failed') ORDER BY completed_at DESC LIMIT 50"
        ).fetchall()
    finally:
        db.close()
    tasks = [_TaskView(_row_to_dict(r)) for r in rows]
    parts = []
    for task in tasks:
        parts.append(templates.TemplateResponse(
            request, "partials/task_card.html", {"task": task}
        ).body.decode())
    if not parts:
        return HTMLResponse('<div class="empty-column">No completed tasks yet</div>')
    return HTMLResponse("".join(parts))


# ---------------------------------------------------------------------------
# Form-based create (used by the modal in tasks.html)
# ---------------------------------------------------------------------------

@router.post("/tasks/create", response_class=HTMLResponse)
async def create_task_form(
    request: Request,
    title: str = Form(...),
    description: str = Form(""),
    priority: str = Form("normal"),
    assigned_to: str = Form(""),
):
    """Create a task from the modal form and return a task card partial."""
    task_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    priority = priority if priority in VALID_PRIORITIES else "normal"

    db = _get_db()
    try:
        db.execute(
            "INSERT INTO tasks (id, title, description, priority, assigned_to, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (task_id, title, description, priority, assigned_to, now),
        )
        db.commit()
        row = db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    finally:
        db.close()

    task = _TaskView(_row_to_dict(row))
    return templates.TemplateResponse(request, "partials/task_card.html", {"task": task})


# ---------------------------------------------------------------------------
# Task action endpoints (approve, veto, modify, pause, cancel, retry)
# ---------------------------------------------------------------------------

@router.post("/tasks/{task_id}/approve", response_class=HTMLResponse)
async def approve_task(request: Request, task_id: str):
    return await _set_status(request, task_id, "approved")


@router.post("/tasks/{task_id}/veto", response_class=HTMLResponse)
async def veto_task(request: Request, task_id: str):
    return await _set_status(request, task_id, "vetoed")


@router.post("/tasks/{task_id}/pause", response_class=HTMLResponse)
async def pause_task(request: Request, task_id: str):
    return await _set_status(request, task_id, "paused")


@router.post("/tasks/{task_id}/cancel", response_class=HTMLResponse)
async def cancel_task(request: Request, task_id: str):
    return await _set_status(request, task_id, "vetoed")


@router.post("/tasks/{task_id}/retry", response_class=HTMLResponse)
async def retry_task(request: Request, task_id: str):
    return await _set_status(request, task_id, "approved")


@router.post("/tasks/{task_id}/modify", response_class=HTMLResponse)
async def modify_task(
    request: Request,
    task_id: str,
    title: str = Form(...),
    description: str = Form(""),
):
    db = _get_db()
    try:
        db.execute(
            "UPDATE tasks SET title=?, description=? WHERE id=?",
            (title, description, task_id),
        )
        db.commit()
        row = db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    finally:
        db.close()
    if not row:
        raise HTTPException(404, "Task not found")
    task = _TaskView(_row_to_dict(row))
    return templates.TemplateResponse(request, "partials/task_card.html", {"task": task})


async def _set_status(request: Request, task_id: str, new_status: str):
    """Helper to update status and return refreshed task card."""
    completed_at = datetime.utcnow().isoformat() if new_status in ("completed", "vetoed", "failed") else None
    db = _get_db()
    try:
        db.execute(
            "UPDATE tasks SET status=?, completed_at=COALESCE(?, completed_at) WHERE id=?",
            (new_status, completed_at, task_id),
        )
        db.commit()
        row = db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    finally:
        db.close()
    if not row:
        raise HTTPException(404, "Task not found")
    task = _TaskView(_row_to_dict(row))
    return templates.TemplateResponse(request, "partials/task_card.html", {"task": task})


# ---------------------------------------------------------------------------
# JSON API (for programmatic access / Timmy's tool calls)
# ---------------------------------------------------------------------------

@router.post("/api/tasks", response_class=JSONResponse, status_code=201)
async def api_create_task(request: Request):
    """Create a task via JSON API."""
    body = await request.json()
    title = body.get("title")
    if not title:
        raise HTTPException(422, "title is required")

    task_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    priority = body.get("priority", "normal")
    if priority not in VALID_PRIORITIES:
        priority = "normal"

    db = _get_db()
    try:
        db.execute(
            "INSERT INTO tasks (id, title, description, priority, assigned_to, created_by, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                task_id,
                title,
                body.get("description", ""),
                priority,
                body.get("assigned_to", ""),
                body.get("created_by", "operator"),
                now,
            ),
        )
        db.commit()
        row = db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    finally:
        db.close()

    return JSONResponse(_row_to_dict(row), status_code=201)


@router.get("/api/tasks", response_class=JSONResponse)
async def api_list_tasks():
    """List all tasks as JSON."""
    db = _get_db()
    try:
        rows = db.execute("SELECT * FROM tasks ORDER BY created_at DESC").fetchall()
    finally:
        db.close()
    return JSONResponse([_row_to_dict(r) for r in rows])


@router.patch("/api/tasks/{task_id}/status", response_class=JSONResponse)
async def api_update_status(task_id: str, request: Request):
    """Update task status via JSON API."""
    body = await request.json()
    new_status = body.get("status")
    if not new_status or new_status not in VALID_STATUSES:
        raise HTTPException(422, f"Invalid status. Must be one of: {VALID_STATUSES}")

    completed_at = datetime.utcnow().isoformat() if new_status in ("completed", "vetoed", "failed") else None
    db = _get_db()
    try:
        db.execute(
            "UPDATE tasks SET status=?, completed_at=COALESCE(?, completed_at) WHERE id=?",
            (new_status, completed_at, task_id),
        )
        db.commit()
        row = db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    finally:
        db.close()
    if not row:
        raise HTTPException(404, "Task not found")
    return JSONResponse(_row_to_dict(row))


@router.delete("/api/tasks/{task_id}", response_class=JSONResponse)
async def api_delete_task(task_id: str):
    """Delete a task."""
    db = _get_db()
    try:
        cursor = db.execute("DELETE FROM tasks WHERE id=?", (task_id,))
        db.commit()
    finally:
        db.close()
    if cursor.rowcount == 0:
        raise HTTPException(404, "Task not found")
    return JSONResponse({"success": True, "id": task_id})
