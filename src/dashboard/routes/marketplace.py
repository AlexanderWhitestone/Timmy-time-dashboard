"""Agent marketplace route — /marketplace endpoints.

The marketplace is where agents advertise their capabilities and pricing.
Other agents (or the user) can browse available agents and hire them for
tasks via Lightning payments.

Endpoints
---------
GET /marketplace        — JSON catalog (API)
GET /marketplace/ui     — HTML page wired to real registry + stats
GET /marketplace/{id}   — JSON details for a single agent
"""

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from swarm import registry as swarm_registry
from swarm import stats as swarm_stats
from swarm.personas import list_personas

router = APIRouter(tags=["marketplace"])
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))

# ── Static catalog ───────────────────────────────────────────────────────────
# Timmy is listed first as the free sovereign agent; the six personas follow.

# Timmy is always active — it IS the sovereign agent, not a planned persona.
_TIMMY_ENTRY = {
    "id": "timmy",
    "name": "Timmy",
    "role": "Sovereign Commander",
    "description": (
        "Primary AI companion. Coordinates the swarm, manages tasks, "
        "and maintains sovereignty."
    ),
    "capabilities": "chat,reasoning,coordination",
    "rate_sats": 0,
    "default_status": "active",  # always active even if not in the swarm registry
}

AGENT_CATALOG: list[dict] = [_TIMMY_ENTRY] + [
    {
        "id": p["id"],
        "name": p["name"],
        "role": p["role"],
        "description": p["description"],
        "capabilities": p["capabilities"],
        "rate_sats": p["rate_sats"],
        "default_status": "planned",  # persona is planned until spawned
    }
    for p in list_personas()
]


def _build_enriched_catalog() -> list[dict]:
    """Merge static catalog with live registry status and historical stats.

    For each catalog entry:
    - status: registry value (idle/busy/offline) when the agent is spawned,
              or default_status ("active" for Timmy, "planned" for personas)
    - tasks_completed / total_earned: pulled from bid_history stats
    """
    registry_agents = swarm_registry.list_agents()
    by_name: dict[str, object] = {a.name.lower(): a for a in registry_agents}
    all_stats = swarm_stats.get_all_agent_stats()

    enriched = []
    for entry in AGENT_CATALOG:
        e = dict(entry)
        reg = by_name.get(e["name"].lower())

        if reg is not None:
            # Timmy is always "active" in the marketplace — it's the sovereign
            # agent, not just a task worker.  Registry idle/busy is internal state.
            e["status"] = "active" if e["id"] == "timmy" else reg.status
            agent_stats = all_stats.get(reg.id, {})
            e["tasks_completed"] = agent_stats.get("tasks_won", 0)
            e["total_earned"] = agent_stats.get("total_earned", 0)
        else:
            e["status"] = e.pop("default_status", "planned")
            e["tasks_completed"] = 0
            e["total_earned"] = 0

        # Remove internal field if it wasn't already popped
        e.pop("default_status", None)
        enriched.append(e)
    return enriched


# ── Routes ───────────────────────────────────────────────────────────────────

@router.get("/marketplace/ui", response_class=HTMLResponse)
async def marketplace_ui(request: Request):
    """Render the marketplace HTML page with live registry data."""
    agents = _build_enriched_catalog()
    active = [a for a in agents if a["status"] in ("idle", "busy", "active")]
    planned = [a for a in agents if a["status"] == "planned"]
    return templates.TemplateResponse(
        request,
        "marketplace.html",
        {
            "page_title": "Agent Marketplace",
            "agents": agents,
            "active_count": len(active),
            "planned_count": len(planned),
        },
    )


@router.get("/marketplace")
async def marketplace():
    """Return the agent marketplace catalog as JSON."""
    agents = _build_enriched_catalog()
    active = [a for a in agents if a["status"] in ("idle", "busy", "active")]
    planned = [a for a in agents if a["status"] == "planned"]
    return {
        "agents": agents,
        "active_count": len(active),
        "planned_count": len(planned),
        "total": len(agents),
    }


@router.get("/marketplace/{agent_id}")
async def marketplace_agent(agent_id: str):
    """Get details for a specific marketplace agent."""
    agents = _build_enriched_catalog()
    agent = next((a for a in agents if a["id"] == agent_id), None)
    if agent is None:
        return {"error": "Agent not found in marketplace"}
    return agent
