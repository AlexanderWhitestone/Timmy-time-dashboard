"""Celery task queue routes — view and manage background tasks.

GET  /celery              — render the Celery task queue page
GET  /celery/api          — JSON list of tasks
POST /celery/api          — submit a new background task
GET  /celery/api/{id}     — get status of a specific task
POST /celery/api/{id}/revoke — cancel a running task
"""

import logging

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

from dashboard.templating import templates

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/celery", tags=["celery"])

# In-memory record of submitted task IDs for the dashboard display.
# In production this would use the Celery result backend directly,
# but this lightweight list keeps the UI functional without Redis.
_submitted_tasks: list[dict] = []
_MAX_TASK_HISTORY = 100


@router.get("", response_class=HTMLResponse)
async def tasks_page(request: Request):
    """Render the Celery task queue page."""
    from infrastructure.celery.app import celery_app

    celery_available = celery_app is not None
    tasks = _get_tasks_with_status()
    return templates.TemplateResponse(
        request,
        "celery_tasks.html",
        {"tasks": tasks, "celery_available": celery_available},
    )


@router.get("/api", response_class=JSONResponse)
async def tasks_api():
    """Return task list as JSON with current status."""
    return _get_tasks_with_status()


@router.post("/api", response_class=JSONResponse)
async def submit_task_api(request: Request):
    """Submit a new background task.

    Body: {"prompt": "...", "agent_id": "default"}
    """
    from infrastructure.celery.client import submit_chat_task

    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

    prompt = body.get("prompt", "").strip()
    if not prompt:
        return JSONResponse({"error": "prompt is required"}, status_code=400)

    agent_id = body.get("agent_id", "default")
    task_id = submit_chat_task(prompt=prompt, agent_id=agent_id)

    if task_id is None:
        return JSONResponse(
            {"error": "Celery is not available. Start Redis and a Celery worker."},
            status_code=503,
        )

    task_record = {
        "task_id": task_id,
        "prompt": prompt[:200],
        "agent_id": agent_id,
        "state": "PENDING",
    }
    _submitted_tasks.append(task_record)
    if len(_submitted_tasks) > _MAX_TASK_HISTORY:
        _submitted_tasks.pop(0)

    return JSONResponse(task_record, status_code=202)


@router.get("/api/{task_id}", response_class=JSONResponse)
async def task_status_api(task_id: str):
    """Get status of a specific task."""
    from infrastructure.celery.client import get_task_status

    status = get_task_status(task_id)
    if status is None:
        return JSONResponse(
            {"error": "Celery is not available or task not found"},
            status_code=503,
        )
    return status


@router.post("/api/{task_id}/revoke", response_class=JSONResponse)
async def revoke_task_api(task_id: str):
    """Cancel a pending or running task."""
    from infrastructure.celery.client import revoke_task

    success = revoke_task(task_id)
    if not success:
        return JSONResponse(
            {"error": "Failed to revoke task (Celery unavailable)"},
            status_code=503,
        )
    return {"task_id": task_id, "status": "revoked"}


def _get_tasks_with_status() -> list[dict]:
    """Enrich submitted tasks with current Celery status."""
    from infrastructure.celery.client import get_task_status

    enriched = []
    for record in reversed(_submitted_tasks):
        status = get_task_status(record["task_id"])
        if status:
            record_copy = {**record, **status}
        else:
            record_copy = {**record, "state": "UNKNOWN"}
        enriched.append(record_copy)
    return enriched
