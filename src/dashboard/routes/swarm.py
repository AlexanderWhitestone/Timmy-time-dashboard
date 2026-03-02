"""Swarm dashboard routes — /swarm/* endpoints.

Provides REST endpoints for viewing swarm agents, tasks, and the
live WebSocket feed. Coordinator/learner/auction plumbing has been
removed — established tools will replace the homebrew orchestration.
"""

import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from swarm import registry
from swarm.tasks import TaskStatus, list_tasks as _list_tasks, get_task as _get_task
from infrastructure.ws_manager.handler import ws_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/swarm", tags=["swarm"])
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


@router.get("")
async def swarm_status():
    """Return the current swarm status summary."""
    agents = registry.list_agents()
    tasks = _list_tasks()
    return {
        "agents": len(agents),
        "tasks": len(tasks),
        "status": "operational",
    }


@router.get("/live", response_class=HTMLResponse)
async def swarm_live_page(request: Request):
    """Render the live swarm dashboard page."""
    return templates.TemplateResponse(
        request, "swarm_live.html", {"page_title": "Swarm Live"}
    )


@router.get("/mission-control", response_class=HTMLResponse)
async def mission_control_page(request: Request):
    """Render the Mission Control dashboard."""
    return templates.TemplateResponse(
        request, "mission_control.html", {"page_title": "Mission Control"}
    )


@router.get("/agents")
async def list_swarm_agents():
    """List all registered swarm agents."""
    agents = registry.list_agents()
    return {
        "agents": [
            {
                "id": a.id,
                "name": a.name,
                "status": a.status,
                "capabilities": a.capabilities,
                "last_seen": a.last_seen,
            }
            for a in agents
        ]
    }


@router.get("/tasks")
async def list_tasks(status: Optional[str] = None):
    """List swarm tasks, optionally filtered by status."""
    task_status = TaskStatus(status.lower()) if status else None
    tasks = _list_tasks(status=task_status)
    return {
        "tasks": [
            {
                "id": t.id,
                "description": t.description,
                "status": t.status.value,
                "assigned_agent": t.assigned_agent,
                "result": t.result,
                "created_at": t.created_at,
                "completed_at": t.completed_at,
            }
            for t in tasks
        ]
    }


@router.get("/tasks/{task_id}")
async def get_task(task_id: str):
    """Get details for a specific task."""
    task = _get_task(task_id)
    if task is None:
        return {"error": "Task not found"}
    return {
        "id": task.id,
        "description": task.description,
        "status": task.status.value,
        "assigned_agent": task.assigned_agent,
        "result": task.result,
        "created_at": task.created_at,
        "completed_at": task.completed_at,
    }


@router.get("/insights")
async def swarm_insights():
    """Placeholder — learner metrics removed. Will be replaced by brain memory stats."""
    return {"agents": {}, "note": "Learner deprecated. Use brain.memory for insights."}


@router.get("/insights/{agent_id}")
async def agent_insights(agent_id: str):
    """Placeholder — learner metrics removed."""
    return {"agent_id": agent_id, "note": "Learner deprecated. Use brain.memory for insights."}


# ── UI endpoints (return HTML partials for HTMX) ─────────────────────────────

@router.get("/agents/sidebar", response_class=HTMLResponse)
async def agents_sidebar(request: Request):
    """Sidebar partial: all registered agents."""
    agents = registry.list_agents()
    return templates.TemplateResponse(
        request, "partials/swarm_agents_sidebar.html", {"agents": agents}
    )


@router.get("/agents/{agent_id}/panel", response_class=HTMLResponse)
async def agent_panel(agent_id: str, request: Request):
    """Main-panel partial: agent detail."""
    agent = registry.get_agent(agent_id)
    if agent is None:
        raise HTTPException(404, "Agent not found")
    return templates.TemplateResponse(
        request,
        "partials/agent_panel.html",
        {"agent": agent, "tasks": []},
    )


# ── WebSocket live feed ──────────────────────────────────────────────────

@router.websocket("/live")
async def swarm_live(websocket: WebSocket):
    """WebSocket endpoint for live swarm event streaming."""
    try:
        await ws_manager.connect(websocket)
    except Exception as exc:
        logger.warning("WebSocket accept failed: %s", exc)
        return
    try:
        while True:
            data = await websocket.receive_text()
            logger.debug("WS received: %s", data[:100])
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception as exc:
        logger.error("WebSocket error: %s", exc)
        ws_manager.disconnect(websocket)
