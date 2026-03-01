"""Bug Report routes -- error feedback loop dashboard.

GET  /bugs              -- Bug reports dashboard page
GET  /api/bugs          -- List bug reports (JSON)
GET  /api/bugs/stats    -- Bug report statistics
POST /api/bugs/submit   -- Submit structured bug reports (from AI test runs)
"""

import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from swarm.task_queue.models import create_task, list_tasks

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


# ── Bug Report Submission ────────────────────────────────────────────────────

# Severity → task priority mapping
_SEVERITY_MAP = {"P0": "urgent", "P1": "high", "P2": "normal"}


def _format_bug_description(bug: dict, reporter: str) -> str:
    """Format a bug dict into a markdown task description."""
    parts = [
        f"**Reporter:** {reporter}",
        f"**Severity:** {bug['severity']}",
        "",
        "## Problem",
        bug["description"],
    ]
    if bug.get("evidence"):
        parts += ["", "## Evidence", bug["evidence"]]
    if bug.get("root_cause"):
        parts += ["", "## Suspected Root Cause", bug["root_cause"]]
    if bug.get("fix_options"):
        parts += ["", "## Suggested Fixes"]
        for i, fix in enumerate(bug["fix_options"], 1):
            parts.append(f"{i}. {fix}")
    return "\n".join(parts)


@router.post("/api/bugs/submit", response_class=JSONResponse)
async def submit_bugs(request: Request):
    """Submit structured bug reports from an AI test run.

    Body: { "reporter": "comet", "bugs": [ { "title", "severity", "description", ... } ] }
    """
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": "Invalid JSON"})

    reporter = body.get("reporter", "unknown")
    bugs = body.get("bugs", [])

    if not bugs:
        return JSONResponse(status_code=400, content={"error": "No bugs provided"})

    task_ids = []
    for bug in bugs:
        title = bug.get("title", "")
        severity = bug.get("severity", "")
        description = bug.get("description", "")

        if not title or not severity or not description:
            return JSONResponse(
                status_code=400,
                content={"error": f"Bug missing required fields (title, severity, description)"},
            )

        priority = _SEVERITY_MAP.get(severity, "normal")

        task = create_task(
            title=f"[{severity}] {title}",
            description=_format_bug_description(bug, reporter),
            task_type="bug_report",
            assigned_to="timmy",
            created_by=reporter,
            priority=priority,
            requires_approval=False,
            auto_approve=True,
        )
        task_ids.append(task.id)

    logger.info("Bug report submitted: %d bug(s) from %s", len(task_ids), reporter)

    return {"created": len(task_ids), "task_ids": task_ids}
