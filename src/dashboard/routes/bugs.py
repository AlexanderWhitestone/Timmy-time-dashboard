"""Bug Report routes -- error feedback loop dashboard.

GET  /bugs           -- Bug reports dashboard page
GET  /api/bugs       -- List bug reports (JSON)
GET  /api/bugs/stats -- Bug report statistics
"""

import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from swarm.task_queue.models import list_tasks

logger = logging.getLogger(__name__)
router = APIRouter(tags=["bugs"])
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


def _get_bug_reports(status: Optional[str] = None, limit: int = 50) -> list:
    """Get bug report tasks from the task queue."""
    all_tasks = list_tasks(limit=limit)
    bugs = [t for t in all_tasks if t.task_type == "bug_report"]
    if status:
        bugs = [t for t in bugs if t.status.value == status]
    return bugs


@router.get("/bugs", response_class=HTMLResponse)
async def bugs_page(request: Request, status: Optional[str] = None):
    """Bug reports dashboard page."""
    bugs = _get_bug_reports(status=status, limit=200)

    # Count by status
    all_bugs = _get_bug_reports(limit=500)
    stats: dict[str, int] = {}
    for bug in all_bugs:
        s = bug.status.value
        stats[s] = stats.get(s, 0) + 1

    return templates.TemplateResponse(
        request,
        "bugs.html",
        {
            "page_title": "Bug Reports",
            "bugs": bugs,
            "stats": stats,
            "total": len(all_bugs),
            "filter_status": status,
        },
    )


@router.get("/api/bugs", response_class=JSONResponse)
async def api_list_bugs(status: Optional[str] = None, limit: int = 50):
    """List bug reports as JSON."""
    bugs = _get_bug_reports(status=status, limit=limit)
    return {
        "bugs": [
            {
                "id": b.id,
                "title": b.title,
                "description": b.description,
                "status": b.status.value,
                "priority": b.priority.value,
                "created_at": b.created_at,
                "result": b.result,
            }
            for b in bugs
        ],
        "count": len(bugs),
    }


@router.get("/api/bugs/stats", response_class=JSONResponse)
async def api_bug_stats():
    """Bug report statistics."""
    all_bugs = _get_bug_reports(limit=500)
    stats: dict[str, int] = {}
    for bug in all_bugs:
        s = bug.status.value
        stats[s] = stats.get(s, 0) + 1
    return {"stats": stats, "total": len(all_bugs)}
