"""Event Log routes for viewing system events."""

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from swarm.event_log import (
    EventType,
    list_events,
    get_event_summary,
    get_recent_events,
)

router = APIRouter(prefix="/swarm", tags=["events"])
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


@router.get("/events", response_class=HTMLResponse)
async def events_page(
    request: Request,
    event_type: Optional[str] = None,
    task_id: Optional[str] = None,
    agent_id: Optional[str] = None,
):
    """Event log viewer page."""
    # Parse event type filter
    evt_type = None
    if event_type:
        try:
            evt_type = EventType(event_type)
        except ValueError:
            pass
    
    # Get events
    events = list_events(
        event_type=evt_type,
        task_id=task_id,
        agent_id=agent_id,
        limit=100,
    )
    
    # Get summary stats
    summary = get_event_summary(minutes=60)
    
    return templates.TemplateResponse(
        request,
        "events.html",
        {
            "page_title": "Event Log",
            "events": events,
            "summary": summary,
            "filter_type": event_type,
            "filter_task": task_id,
            "filter_agent": agent_id,
            "event_types": [e.value for e in EventType],
        },
    )


@router.get("/events/partial", response_class=HTMLResponse)
async def events_partial(
    request: Request,
    event_type: Optional[str] = None,
    task_id: Optional[str] = None,
    agent_id: Optional[str] = None,
):
    """Event log partial for HTMX updates."""
    evt_type = None
    if event_type:
        try:
            evt_type = EventType(event_type)
        except ValueError:
            pass
    
    events = list_events(
        event_type=evt_type,
        task_id=task_id,
        agent_id=agent_id,
        limit=100,
    )
    
    return templates.TemplateResponse(
        request,
        "partials/events_table.html",
        {
            "events": events,
        },
    )
