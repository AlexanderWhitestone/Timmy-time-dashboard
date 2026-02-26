"""Task Queue routes — Human-in-the-loop approval dashboard.

GET  /tasks               — Task queue dashboard page
GET  /api/tasks           — List tasks (JSON)
POST /api/tasks           — Create a new task (JSON)
GET  /api/tasks/counts    — Badge counts
GET  /api/tasks/{id}      — Get single task
PATCH /api/tasks/{id}/approve — Approve a task
PATCH /api/tasks/{id}/veto    — Veto a task
PATCH /api/tasks/{id}/modify  — Modify a task
PATCH /api/tasks/{id}/pause   — Pause a running task
PATCH /api/tasks/{id}/cancel  — Cancel / fail a task
PATCH /api/tasks/{id}/retry   — Retry a failed task
GET  /tasks/pending       — HTMX partial: pending tasks
GET  /tasks/active        — HTMX partial: active tasks
GET  /tasks/completed     — HTMX partial: completed tasks
"""

import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from task_queue.models import (
    QueueTask,
    TaskPriority,
    TaskStatus,
    create_task,
    get_counts_by_status,
    get_pending_count,
    get_task,
    list_tasks,
    update_task,
    update_task_status,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["tasks"])
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


# ── Helper to broadcast task events via WebSocket ────────────────────────

def _broadcast_task_event(event_type: str, task: QueueTask):
    """Best-effort broadcast a task event to connected WebSocket clients."""
    try:
        import asyncio
        from ws_manager.handler import ws_manager

        payload = {
            "type": "task_event",
            "event": event_type,
            "task": {
                "id": task.id,
                "title": task.title,
                "status": task.status.value,
                "priority": task.priority.value,
                "assigned_to": task.assigned_to,
                "created_by": task.created_by,
            },
        }
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(ws_manager.broadcast_json(payload))
        except RuntimeError:
            pass  # No event loop running (e.g. in tests)
    except Exception:
        pass  # WebSocket is optional


# ── Dashboard page ───────────────────────────────────────────────────────

@router.get("/tasks", response_class=HTMLResponse)
async def task_queue_page(request: Request, assign: Optional[str] = None):
    """Task queue dashboard with three columns."""
    pending = list_tasks(status=TaskStatus.PENDING_APPROVAL) + \
              list_tasks(status=TaskStatus.APPROVED)
    active = list_tasks(status=TaskStatus.RUNNING) + \
             list_tasks(status=TaskStatus.PAUSED)
    completed = list_tasks(status=TaskStatus.COMPLETED, limit=20) + \
                list_tasks(status=TaskStatus.VETOED, limit=10) + \
                list_tasks(status=TaskStatus.FAILED, limit=10)

    # Get agents for the create modal
    agents = []
    try:
        from swarm.coordinator import coordinator
        agents = [
            {"id": a.id, "name": a.name}
            for a in coordinator.list_swarm_agents()
        ]
    except Exception:
        pass
    # Always include core agents
    core_agents = ["timmy", "forge", "seer", "echo"]
    agent_names = {a["name"] for a in agents}
    for name in core_agents:
        if name not in agent_names:
            agents.append({"id": name, "name": name})

    return templates.TemplateResponse(
        request,
        "tasks.html",
        {
            "page_title": "Task Queue",
            "pending": pending,
            "active": active,
            "completed": completed,
            "pending_count": len(pending),
            "agents": agents,
            "priorities": [p.value for p in TaskPriority],
            "pre_assign": assign or "",
        },
    )


# ── HTMX partials ───────────────────────────────────────────────────────

@router.get("/tasks/pending", response_class=HTMLResponse)
async def tasks_pending_partial(request: Request):
    """HTMX partial: pending approval tasks."""
    pending = list_tasks(status=TaskStatus.PENDING_APPROVAL) + \
              list_tasks(status=TaskStatus.APPROVED)
    return templates.TemplateResponse(
        request,
        "partials/task_cards.html",
        {"tasks": pending, "section": "pending"},
    )


@router.get("/tasks/active", response_class=HTMLResponse)
async def tasks_active_partial(request: Request):
    """HTMX partial: active tasks."""
    active = list_tasks(status=TaskStatus.RUNNING) + \
             list_tasks(status=TaskStatus.PAUSED)
    return templates.TemplateResponse(
        request,
        "partials/task_cards.html",
        {"tasks": active, "section": "active"},
    )


@router.get("/tasks/completed", response_class=HTMLResponse)
async def tasks_completed_partial(request: Request):
    """HTMX partial: completed tasks."""
    completed = list_tasks(status=TaskStatus.COMPLETED, limit=20) + \
                list_tasks(status=TaskStatus.VETOED, limit=10) + \
                list_tasks(status=TaskStatus.FAILED, limit=10)
    return templates.TemplateResponse(
        request,
        "partials/task_cards.html",
        {"tasks": completed, "section": "completed"},
    )


# ── JSON API ─────────────────────────────────────────────────────────────

@router.get("/api/tasks", response_class=JSONResponse)
async def api_list_tasks(
    status: Optional[str] = None,
    priority: Optional[str] = None,
    assigned_to: Optional[str] = None,
    limit: int = 100,
):
    """List tasks with optional filters."""
    s = TaskStatus(status) if status else None
    p = TaskPriority(priority) if priority else None

    tasks = list_tasks(status=s, priority=p, assigned_to=assigned_to, limit=limit)
    return {
        "tasks": [_task_to_dict(t) for t in tasks],
        "count": len(tasks),
    }


@router.post("/api/tasks", response_class=JSONResponse)
async def api_create_task(request: Request):
    """Create a new task (JSON body)."""
    body = await request.json()
    task = create_task(
        title=body.get("title", ""),
        description=body.get("description", ""),
        assigned_to=body.get("assigned_to", "timmy"),
        created_by=body.get("created_by", "user"),
        priority=body.get("priority", "normal"),
        requires_approval=body.get("requires_approval", True),
        auto_approve=body.get("auto_approve", False),
        parent_task_id=body.get("parent_task_id"),
        steps=body.get("steps"),
    )

    # Notify
    _notify_task_created(task)
    _broadcast_task_event("task_created", task)

    logger.info("Task created: %s (status=%s)", task.title, task.status.value)
    return {"success": True, "task": _task_to_dict(task)}


@router.post("/tasks/create", response_class=HTMLResponse)
async def form_create_task(
    request: Request,
    title: str = Form(...),
    description: str = Form(""),
    assigned_to: str = Form("timmy"),
    priority: str = Form("normal"),
    requires_approval: bool = Form(True),
):
    """Create a task from the dashboard form (Form-encoded)."""
    task = create_task(
        title=title,
        description=description,
        assigned_to=assigned_to,
        created_by="user",
        priority=priority,
        requires_approval=requires_approval,
    )
    _notify_task_created(task)
    _broadcast_task_event("task_created", task)
    logger.info("Task created (form): %s", task.title)

    # Return the new card for HTMX swap
    return templates.TemplateResponse(
        request,
        "partials/task_card.html",
        {"task": task},
    )


@router.get("/api/tasks/counts", response_class=JSONResponse)
async def api_task_counts():
    """Get task counts by status (for nav badges)."""
    counts = get_counts_by_status()
    return {
        "pending": counts.get("pending_approval", 0),
        "approved": counts.get("approved", 0),
        "running": counts.get("running", 0),
        "completed": counts.get("completed", 0),
        "failed": counts.get("failed", 0),
        "vetoed": counts.get("vetoed", 0),
        "total": sum(counts.values()),
    }


@router.get("/api/tasks/{task_id}", response_class=JSONResponse)
async def api_get_task(task_id: str):
    """Get a single task by ID."""
    task = get_task(task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    return _task_to_dict(task)


# ── Workflow actions ─────────────────────────────────────────────────────

@router.patch("/api/tasks/{task_id}/approve", response_class=JSONResponse)
async def api_approve_task(task_id: str):
    """Approve a pending task."""
    task = get_task(task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    if task.status not in (TaskStatus.PENDING_APPROVAL,):
        raise HTTPException(400, f"Cannot approve task in {task.status.value} state")

    updated = update_task_status(task_id, TaskStatus.APPROVED)
    _broadcast_task_event("task_approved", updated)
    return {"success": True, "task": _task_to_dict(updated)}


@router.post("/tasks/{task_id}/approve", response_class=HTMLResponse)
async def htmx_approve_task(request: Request, task_id: str):
    """Approve a pending task (HTMX)."""
    task = get_task(task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    updated = update_task_status(task_id, TaskStatus.APPROVED)
    _broadcast_task_event("task_approved", updated)
    return templates.TemplateResponse(
        request, "partials/task_card.html", {"task": updated}
    )


@router.patch("/api/tasks/{task_id}/veto", response_class=JSONResponse)
async def api_veto_task(task_id: str):
    """Veto (reject) a task."""
    task = get_task(task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    if task.status in (TaskStatus.COMPLETED, TaskStatus.VETOED):
        raise HTTPException(400, f"Cannot veto task in {task.status.value} state")

    updated = update_task_status(task_id, TaskStatus.VETOED)
    _broadcast_task_event("task_vetoed", updated)
    return {"success": True, "task": _task_to_dict(updated)}


@router.post("/tasks/{task_id}/veto", response_class=HTMLResponse)
async def htmx_veto_task(request: Request, task_id: str):
    """Veto a task (HTMX)."""
    task = get_task(task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    updated = update_task_status(task_id, TaskStatus.VETOED)
    _broadcast_task_event("task_vetoed", updated)
    return templates.TemplateResponse(
        request, "partials/task_card.html", {"task": updated}
    )


@router.patch("/api/tasks/{task_id}/modify", response_class=JSONResponse)
async def api_modify_task(task_id: str, request: Request):
    """Modify a task's title, description, assignment, or priority."""
    task = get_task(task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    if task.status in (TaskStatus.COMPLETED, TaskStatus.VETOED):
        raise HTTPException(400, f"Cannot modify task in {task.status.value} state")

    body = await request.json()
    updated = update_task(
        task_id,
        title=body.get("title"),
        description=body.get("description"),
        assigned_to=body.get("assigned_to"),
        priority=body.get("priority"),
    )
    _broadcast_task_event("task_modified", updated)
    return {"success": True, "task": _task_to_dict(updated)}


@router.post("/tasks/{task_id}/modify", response_class=HTMLResponse)
async def htmx_modify_task(
    request: Request,
    task_id: str,
    title: str = Form(None),
    description: str = Form(None),
    assigned_to: str = Form(None),
    priority: str = Form(None),
):
    """Modify a task (HTMX form)."""
    task = get_task(task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    updated = update_task(
        task_id,
        title=title,
        description=description,
        assigned_to=assigned_to,
        priority=priority,
    )
    _broadcast_task_event("task_modified", updated)
    return templates.TemplateResponse(
        request, "partials/task_card.html", {"task": updated}
    )


@router.patch("/api/tasks/{task_id}/pause", response_class=JSONResponse)
async def api_pause_task(task_id: str):
    """Pause a running task."""
    task = get_task(task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    if task.status != TaskStatus.RUNNING:
        raise HTTPException(400, "Can only pause running tasks")
    updated = update_task_status(task_id, TaskStatus.PAUSED)
    _broadcast_task_event("task_paused", updated)
    return {"success": True, "task": _task_to_dict(updated)}


@router.post("/tasks/{task_id}/pause", response_class=HTMLResponse)
async def htmx_pause_task(request: Request, task_id: str):
    """Pause a running task (HTMX)."""
    task = get_task(task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    updated = update_task_status(task_id, TaskStatus.PAUSED)
    _broadcast_task_event("task_paused", updated)
    return templates.TemplateResponse(
        request, "partials/task_card.html", {"task": updated}
    )


@router.patch("/api/tasks/{task_id}/cancel", response_class=JSONResponse)
async def api_cancel_task(task_id: str):
    """Cancel a task (sets to failed)."""
    task = get_task(task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    if task.status in (TaskStatus.COMPLETED, TaskStatus.VETOED):
        raise HTTPException(400, f"Cannot cancel task in {task.status.value} state")
    updated = update_task_status(task_id, TaskStatus.FAILED, result="Cancelled by user")
    _broadcast_task_event("task_cancelled", updated)
    return {"success": True, "task": _task_to_dict(updated)}


@router.post("/tasks/{task_id}/cancel", response_class=HTMLResponse)
async def htmx_cancel_task(request: Request, task_id: str):
    """Cancel a task (HTMX)."""
    task = get_task(task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    updated = update_task_status(task_id, TaskStatus.FAILED, result="Cancelled by user")
    _broadcast_task_event("task_cancelled", updated)
    return templates.TemplateResponse(
        request, "partials/task_card.html", {"task": updated}
    )


@router.patch("/api/tasks/{task_id}/retry", response_class=JSONResponse)
async def api_retry_task(task_id: str):
    """Retry a failed task (resets to approved)."""
    task = get_task(task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    if task.status != TaskStatus.FAILED:
        raise HTTPException(400, "Can only retry failed tasks")
    updated = update_task_status(task_id, TaskStatus.APPROVED, result=None)
    _broadcast_task_event("task_retried", updated)
    return {"success": True, "task": _task_to_dict(updated)}


@router.post("/tasks/{task_id}/retry", response_class=HTMLResponse)
async def htmx_retry_task(request: Request, task_id: str):
    """Retry a failed task (HTMX)."""
    task = get_task(task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    updated = update_task_status(task_id, TaskStatus.APPROVED, result=None)
    _broadcast_task_event("task_retried", updated)
    return templates.TemplateResponse(
        request, "partials/task_card.html", {"task": updated}
    )


# ── Helpers ──────────────────────────────────────────────────────────────

def _task_to_dict(task: QueueTask) -> dict:
    return {
        "id": task.id,
        "title": task.title,
        "description": task.description,
        "assigned_to": task.assigned_to,
        "created_by": task.created_by,
        "status": task.status.value,
        "priority": task.priority.value,
        "requires_approval": task.requires_approval,
        "auto_approve": task.auto_approve,
        "parent_task_id": task.parent_task_id,
        "result": task.result,
        "steps": task.steps,
        "created_at": task.created_at,
        "started_at": task.started_at,
        "completed_at": task.completed_at,
        "updated_at": task.updated_at,
    }


def _notify_task_created(task: QueueTask):
    try:
        from notifications.push import notifier
        notifier.notify(
            title="New Task",
            message=f"{task.created_by} created: {task.title}",
            category="task",
            native=task.priority in (TaskPriority.HIGH, TaskPriority.URGENT),
        )
    except Exception:
        pass
