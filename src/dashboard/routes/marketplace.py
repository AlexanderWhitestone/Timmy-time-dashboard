"""Agent marketplace route — /marketplace endpoints.

DEPRECATED: Personas replaced by brain task queue.
This module is kept for UI compatibility.
"""

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from brain.client import BrainClient

router = APIRouter(tags=["marketplace"])
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))

# Orchestrator only — personas deprecated
AGENT_CATALOG = [
    {
        "id": "orchestrator",
        "name": "Orchestrator",
        "role": "Local AI",
        "description": (
            "Primary AI agent. Coordinates tasks, manages memory. "
            "Uses distributed brain."
        ),
        "capabilities": "chat,reasoning,coordination,memory",
        "rate_sats": 0,
        "default_status": "active",
    }
]


@router.get("/api/marketplace/agents")
async def api_list_agents():
    """Return agent catalog with current status (JSON API)."""
    try:
        brain = BrainClient()
        pending_tasks = len(await brain.get_pending_tasks(limit=1000))
    except Exception:
        pending_tasks = 0
    
    catalog = [dict(AGENT_CATALOG[0])]
    catalog[0]["pending_tasks"] = pending_tasks
    catalog[0]["status"] = "active"
    
    # Include 'total' for backward compatibility with tests
    return {"agents": catalog, "total": len(catalog)}


@router.get("/marketplace")
async def marketplace_ui(request: Request):
    """Marketplace page — returns JSON for API requests, HTML for browser."""
    # Check if client wants JSON (common test clients don't set Accept header)
    accept = request.headers.get("accept", "")
    # Return JSON if Accept header indicates JSON OR if no preference (default to JSON for API)
    if "application/json" in accept or accept == "*/*" or not accept:
        return await api_list_agents()
    
    # Browser request - return HTML
    try:
        brain = BrainClient()
        tasks = await brain.get_pending_tasks(limit=20)
    except Exception:
        tasks = []
    
    return templates.TemplateResponse(
        request,
        "marketplace.html",
        {
            "agents": AGENT_CATALOG,
            "pending_tasks": tasks,
            "message": "Personas deprecated — use Brain Task Queue",
        }
    )


@router.get("/marketplace/{agent_id}")
async def agent_detail(agent_id: str):
    """Get agent details."""
    if agent_id == "orchestrator":
        return AGENT_CATALOG[0]
    return {"error": "Agent not found — personas deprecated"}
