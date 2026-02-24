"""Spark Intelligence dashboard routes.

GET  /spark          — JSON status (API)
GET  /spark/ui       — HTML Spark Intelligence dashboard
GET  /spark/timeline — HTMX partial: recent event timeline
GET  /spark/insights — HTMX partial: advisories and insights
GET  /spark/predictions — HTMX partial: EIDOS predictions
"""

import json
import logging
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from spark.engine import spark_engine

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/spark", tags=["spark"])
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


@router.get("/ui", response_class=HTMLResponse)
async def spark_ui(request: Request):
    """Render the Spark Intelligence dashboard page."""
    status = spark_engine.status()
    advisories = spark_engine.get_advisories()
    timeline = spark_engine.get_timeline(limit=20)
    predictions = spark_engine.get_predictions(limit=10)
    memories = spark_engine.get_memories(limit=10)

    # Parse event data JSON for template display
    timeline_enriched = []
    for ev in timeline:
        entry = {
            "id": ev.id,
            "event_type": ev.event_type,
            "agent_id": ev.agent_id,
            "task_id": ev.task_id,
            "description": ev.description,
            "importance": ev.importance,
            "created_at": ev.created_at,
        }
        try:
            entry["data"] = json.loads(ev.data)
        except (json.JSONDecodeError, TypeError):
            entry["data"] = {}
        timeline_enriched.append(entry)

    # Enrich predictions for display
    predictions_enriched = []
    for p in predictions:
        entry = {
            "id": p.id,
            "task_id": p.task_id,
            "prediction_type": p.prediction_type,
            "accuracy": p.accuracy,
            "created_at": p.created_at,
            "evaluated_at": p.evaluated_at,
        }
        try:
            entry["predicted"] = json.loads(p.predicted_value)
        except (json.JSONDecodeError, TypeError):
            entry["predicted"] = {}
        try:
            entry["actual"] = json.loads(p.actual_value) if p.actual_value else None
        except (json.JSONDecodeError, TypeError):
            entry["actual"] = None
        predictions_enriched.append(entry)

    return templates.TemplateResponse(
        request,
        "spark.html",
        {
            "status": status,
            "advisories": advisories,
            "timeline": timeline_enriched,
            "predictions": predictions_enriched,
            "memories": memories,
        },
    )


@router.get("", response_class=HTMLResponse)
async def spark_status_json():
    """Return Spark Intelligence status as JSON."""
    from fastapi.responses import JSONResponse
    status = spark_engine.status()
    advisories = spark_engine.get_advisories()
    return JSONResponse({
        "status": status,
        "advisories": [
            {
                "category": a.category,
                "priority": a.priority,
                "title": a.title,
                "detail": a.detail,
                "suggested_action": a.suggested_action,
                "subject": a.subject,
                "evidence_count": a.evidence_count,
            }
            for a in advisories
        ],
    })


@router.get("/timeline", response_class=HTMLResponse)
async def spark_timeline(request: Request):
    """HTMX partial: recent event timeline."""
    timeline = spark_engine.get_timeline(limit=20)
    timeline_enriched = []
    for ev in timeline:
        entry = {
            "id": ev.id,
            "event_type": ev.event_type,
            "agent_id": ev.agent_id,
            "task_id": ev.task_id,
            "description": ev.description,
            "importance": ev.importance,
            "created_at": ev.created_at,
        }
        try:
            entry["data"] = json.loads(ev.data)
        except (json.JSONDecodeError, TypeError):
            entry["data"] = {}
        timeline_enriched.append(entry)

    return templates.TemplateResponse(
        request,
        "partials/spark_timeline.html",
        {"timeline": timeline_enriched},
    )


@router.get("/insights", response_class=HTMLResponse)
async def spark_insights(request: Request):
    """HTMX partial: advisories and consolidated memories."""
    advisories = spark_engine.get_advisories()
    memories = spark_engine.get_memories(limit=10)
    return templates.TemplateResponse(
        request,
        "partials/spark_insights.html",
        {"advisories": advisories, "memories": memories},
    )
