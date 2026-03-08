"""Agent marketplace route — /marketplace endpoints.

DEPRECATED: Personas replaced by brain task queue.
This module is kept for UI compatibility.
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

from brain.client import BrainClient
from dashboard.templating import templates

router = APIRouter(tags=["marketplace"])

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
async def marketplace_json(request: Request):
    """Marketplace JSON API (backward compat)."""
    return await api_list_agents()


@router.get("/marketplace/ui", response_class=HTMLResponse)
async def marketplace_ui(request: Request):
    """Marketplace HTML page."""
    try:
        brain = BrainClient()
        tasks = await brain.get_pending_tasks(limit=20)
    except Exception:
        tasks = []

    # Enrich agents with fields the template expects
    enriched = []
    for agent in AGENT_CATALOG:
        a = dict(agent)
        a.setdefault("status", a.get("default_status", "active"))
        a.setdefault("tasks_completed", 0)
        a.setdefault("total_earned", 0)
        enriched.append(a)

    active = sum(1 for a in enriched if a["status"] == "active")

    return templates.TemplateResponse(
        request,
        "marketplace.html",
        {
            "agents": enriched,
            "pending_tasks": tasks,
            "message": "Personas deprecated — use Brain Task Queue",
            "page_title": "Agent Marketplace",
            "active_count": active,
            "planned_count": 0,
        }
    )


@router.get("/marketplace/{agent_id}")
async def agent_detail(agent_id: str):
    """Get agent details."""
    if agent_id == "orchestrator":
        return AGENT_CATALOG[0]
    return {"error": "Agent not found — personas deprecated"}
