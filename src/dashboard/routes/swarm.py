"""Swarm-related dashboard routes (events, live feed)."""

import json
import logging
from typing import Optional

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

from spark.engine import spark_engine
from dashboard.templating import templates
from infrastructure.ws_manager.handler import ws_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/swarm", tags=["swarm"])


@router.get("/events", response_class=HTMLResponse)
async def swarm_events(
    request: Request,
    task_id: Optional[str] = None,
    agent_id: Optional[str] = None,
    event_type: Optional[str] = None,
):
    """Event log page."""
    events = spark_engine.get_timeline(limit=100)
    
    # Filter if requested
    if task_id:
        events = [e for e in events if e.task_id == task_id]
    if agent_id:
        events = [e for e in events if e.agent_id == agent_id]
    if event_type:
        events = [e for e in events if e.event_type == event_type]
        
    # Prepare summary and event types for template
    summary = {}
    event_types = set()
    for e in events:
        etype = e.event_type
        event_types.add(etype)
        summary[etype] = summary.get(etype, 0) + 1
        
    return templates.TemplateResponse(
        request,
        "events.html",
        {
            "events": events,
            "summary": summary,
            "event_types": sorted(list(event_types)),
            "filter_task": task_id,
            "filter_agent": agent_id,
            "filter_type": event_type,
        },
    )


@router.get("/live", response_class=HTMLResponse)
async def swarm_live(request: Request):
    """Live swarm activity page."""
    status = spark_engine.status()
    events = spark_engine.get_timeline(limit=20)

    return templates.TemplateResponse(
        request,
        "swarm_live.html",
        {
            "status": status,
            "events": events,
        },
    )


@router.websocket("/live")
async def swarm_ws(websocket: WebSocket):
    """WebSocket endpoint for live swarm updates."""
    await ws_manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)


@router.get("/agents/sidebar", response_class=HTMLResponse)
async def agents_sidebar(request: Request):
    """Sidebar partial showing agent status for the home page."""
    from config import settings

    agents = [
        {
            "id": "default",
            "name": settings.agent_name,
            "status": "idle",
            "type": "local",
            "capabilities": "chat,reasoning,research,planning",
            "last_seen": None,
        }
    ]
    return templates.TemplateResponse(
        request, "partials/swarm_agents_sidebar.html", {"agents": agents}
    )
