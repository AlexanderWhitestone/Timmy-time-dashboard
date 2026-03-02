"""Hands Dashboard Routes — DEPRECATED.

Replaced by brain task queue. This module provides compatibility redirects.
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

from brain.client import BrainClient

router = APIRouter(prefix="/hands", tags=["hands"])

# Initialize brain client
_brain: BrainClient = None

def get_brain() -> BrainClient:
    global _brain
    if _brain is None:
        _brain = BrainClient()
    return _brain


@router.get("/api/hands")
async def api_list_hands():
    """Return pending tasks from brain queue (replaces Hands list)."""
    brain = get_brain()
    tasks = await brain.get_pending_tasks(limit=100)
    
    # Convert tasks to hand-like format for UI compatibility
    hands = []
    for task in tasks:
        hands.append({
            "name": f"task-{task['id']}",
            "description": task['content'][:100],
            "enabled": True,
            "status": "pending",
            "schedule": None,
            "last_run": None,
            "next_run": task['created_at'],
            "run_count": 0,
            "task_type": task['type'],
            "priority": task['priority'],
        })
    
    return hands


@router.get("/api/hands/{name}")
async def api_get_hand(name: str):
    """Get task details."""
    # Extract task ID from name
    if name.startswith("task-"):
        try:
            task_id = int(name.split("-")[1])
            # Return basic info
            return {
                "name": name,
                "description": "Task from distributed queue",
                "enabled": True,
                "status": "pending",
                "schedule": None,
            }
        except:
            pass
    
    return JSONResponse(
        status_code=404,
        content={"error": "Hand not found - use brain task queue"}
    )


@router.post("/api/hands/{name}/trigger")
async def api_trigger_hand(name: str):
    """Trigger is now just submitting to brain queue."""
    return {"status": "deprecated", "message": "Use POST /tasks instead"}


@router.get("", response_class=HTMLResponse)
async def hands_page(request: Request):
    """Redirect to new tasks UI."""
    from fastapi.templating import Jinja2Templates
    from pathlib import Path
    
    templates = Jinja2Templates(
        directory=str(Path(__file__).parent.parent / "templates")
    )
    
    # Return simple message about migration
    return templates.TemplateResponse(
        "hands.html",
        {
            "request": request,
            "hands": [],
            "message": "Hands system migrated to Brain Task Queue",
        }
    )
