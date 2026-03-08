"""Work Orders routes — SQLite-backed submit/review/execute pipeline."""

import logging
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse

from dashboard.templating import templates

logger = logging.getLogger(__name__)

router = APIRouter(tags=["work-orders"])

DB_PATH = Path("data/work_orders.db")

PRIORITIES = ["low", "medium", "high", "critical"]
CATEGORIES = ["bug", "feature", "suggestion", "maintenance", "security"]
VALID_STATUSES = {"submitted", "triaged", "approved", "in_progress", "completed", "rejected"}


def _get_db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS work_orders (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            description TEXT DEFAULT '',
            priority TEXT DEFAULT 'medium',
            category TEXT DEFAULT 'suggestion',
            submitter TEXT DEFAULT 'dashboard',
            related_files TEXT DEFAULT '',
            status TEXT DEFAULT 'submitted',
            result TEXT DEFAULT '',
            rejection_reason TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now')),
            completed_at TEXT
        )
    """)
    conn.commit()
    return conn


class _EnumLike:
    def __init__(self, v: str):
        self.value = v

    def __str__(self):
        return self.value

    def __eq__(self, other):
        if isinstance(other, str):
            return self.value == other
        return NotImplemented


class _WOView:
    """View object for Jinja template rendering."""

    def __init__(self, row: dict):
        self.id = row["id"]
        self.title = row.get("title", "")
        self.description = row.get("description", "")
        self.priority = _EnumLike(row.get("priority", "medium"))
        self.category = _EnumLike(row.get("category", "suggestion"))
        self.submitter = row.get("submitter", "dashboard")
        self.status = _EnumLike(row.get("status", "submitted"))
        raw_files = row.get("related_files", "")
        self.related_files = [f.strip() for f in raw_files.split(",") if f.strip()] if raw_files else []
        self.result = row.get("result", "")
        self.rejection_reason = row.get("rejection_reason", "")
        self.created_at = row.get("created_at", "")
        self.completed_at = row.get("completed_at")
        self.execution_mode = None


def _row_to_dict(row: sqlite3.Row) -> dict:
    return dict(row)


def _query_wos(db, statuses):
    placeholders = ",".join("?" for _ in statuses)
    return [
        _WOView(_row_to_dict(r))
        for r in db.execute(
            f"SELECT * FROM work_orders WHERE status IN ({placeholders}) ORDER BY created_at DESC",
            statuses,
        ).fetchall()
    ]


# ---------------------------------------------------------------------------
# Page route
# ---------------------------------------------------------------------------

@router.get("/work-orders/queue", response_class=HTMLResponse)
async def work_orders_page(request: Request):
    db = _get_db()
    try:
        pending = _query_wos(db, ["submitted", "triaged"])
        active = _query_wos(db, ["approved", "in_progress"])
        completed = _query_wos(db, ["completed"])
        rejected = _query_wos(db, ["rejected"])
    finally:
        db.close()

    return templates.TemplateResponse(request, "work_orders.html", {
        "pending_count": len(pending),
        "pending": pending,
        "active": active,
        "completed": completed,
        "rejected": rejected,
        "priorities": PRIORITIES,
        "categories": CATEGORIES,
    })


# ---------------------------------------------------------------------------
# Form submit
# ---------------------------------------------------------------------------

@router.post("/work-orders/submit", response_class=HTMLResponse)
async def submit_work_order(
    request: Request,
    title: str = Form(...),
    description: str = Form(""),
    priority: str = Form("medium"),
    category: str = Form("suggestion"),
    submitter: str = Form("dashboard"),
    related_files: str = Form(""),
):
    wo_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    priority = priority if priority in PRIORITIES else "medium"
    category = category if category in CATEGORIES else "suggestion"

    db = _get_db()
    try:
        db.execute(
            "INSERT INTO work_orders (id, title, description, priority, category, submitter, related_files, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (wo_id, title, description, priority, category, submitter, related_files, now),
        )
        db.commit()
        row = db.execute("SELECT * FROM work_orders WHERE id=?", (wo_id,)).fetchone()
    finally:
        db.close()

    wo = _WOView(_row_to_dict(row))
    return templates.TemplateResponse(request, "partials/work_order_card.html", {"wo": wo})


# ---------------------------------------------------------------------------
# HTMX partials
# ---------------------------------------------------------------------------

@router.get("/work-orders/queue/pending", response_class=HTMLResponse)
async def pending_partial(request: Request):
    db = _get_db()
    try:
        wos = _query_wos(db, ["submitted", "triaged"])
    finally:
        db.close()
    if not wos:
        return HTMLResponse(
            '<div style="color: var(--text-muted); font-size: 0.8rem; padding: 12px 0;">'
            "No pending work orders.</div>"
        )
    parts = []
    for wo in wos:
        parts.append(
            templates.TemplateResponse(request, "partials/work_order_card.html", {"wo": wo}).body.decode()
        )
    return HTMLResponse("".join(parts))


@router.get("/work-orders/queue/active", response_class=HTMLResponse)
async def active_partial(request: Request):
    db = _get_db()
    try:
        wos = _query_wos(db, ["approved", "in_progress"])
    finally:
        db.close()
    if not wos:
        return HTMLResponse(
            '<div style="color: var(--text-muted); font-size: 0.8rem; padding: 12px 0;">'
            "No work orders currently in progress.</div>"
        )
    parts = []
    for wo in wos:
        parts.append(
            templates.TemplateResponse(request, "partials/work_order_card.html", {"wo": wo}).body.decode()
        )
    return HTMLResponse("".join(parts))


# ---------------------------------------------------------------------------
# Action endpoints
# ---------------------------------------------------------------------------

async def _update_status(request: Request, wo_id: str, new_status: str, **extra):
    completed_at = datetime.utcnow().isoformat() if new_status in ("completed", "rejected") else None
    db = _get_db()
    try:
        sets = ["status=?", "completed_at=COALESCE(?, completed_at)"]
        vals = [new_status, completed_at]
        for col, val in extra.items():
            sets.append(f"{col}=?")
            vals.append(val)
        vals.append(wo_id)
        db.execute(f"UPDATE work_orders SET {', '.join(sets)} WHERE id=?", vals)
        db.commit()
        row = db.execute("SELECT * FROM work_orders WHERE id=?", (wo_id,)).fetchone()
    finally:
        db.close()
    if not row:
        raise HTTPException(404, "Work order not found")
    wo = _WOView(_row_to_dict(row))
    return templates.TemplateResponse(request, "partials/work_order_card.html", {"wo": wo})


@router.post("/work-orders/{wo_id}/approve", response_class=HTMLResponse)
async def approve_wo(request: Request, wo_id: str):
    return await _update_status(request, wo_id, "approved")


@router.post("/work-orders/{wo_id}/reject", response_class=HTMLResponse)
async def reject_wo(request: Request, wo_id: str):
    return await _update_status(request, wo_id, "rejected")


@router.post("/work-orders/{wo_id}/execute", response_class=HTMLResponse)
async def execute_wo(request: Request, wo_id: str):
    return await _update_status(request, wo_id, "in_progress")
