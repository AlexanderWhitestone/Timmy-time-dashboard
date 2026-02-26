"""Work Order queue dashboard routes."""

import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from work_orders.models import (
    WorkOrder,
    WorkOrderCategory,
    WorkOrderPriority,
    WorkOrderStatus,
    create_work_order,
    get_counts_by_status,
    get_pending_count,
    get_work_order,
    list_work_orders,
    update_work_order_status,
)
from work_orders.risk import compute_risk_score, should_auto_execute

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/work-orders", tags=["work-orders"])
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


# ── Submission ─────────────────────────────────────────────────────────────────


@router.post("/submit", response_class=JSONResponse)
async def submit_work_order(
    title: str = Form(...),
    description: str = Form(""),
    priority: str = Form("medium"),
    category: str = Form("suggestion"),
    submitter: str = Form("unknown"),
    submitter_type: str = Form("user"),
    related_files: str = Form(""),
):
    """Submit a new work order (form-encoded).

    This is the primary API for external tools (like Comet) to submit
    work orders and suggestions.
    """
    files = [f.strip() for f in related_files.split(",") if f.strip()] if related_files else []

    wo = create_work_order(
        title=title,
        description=description,
        priority=priority,
        category=category,
        submitter=submitter,
        submitter_type=submitter_type,
        related_files=files,
    )

    # Auto-triage: determine execution mode
    auto = should_auto_execute(wo)
    risk = compute_risk_score(wo)
    mode = "auto" if auto else "manual"
    update_work_order_status(
        wo.id, WorkOrderStatus.TRIAGED, execution_mode=mode,
    )

    # Notify
    try:
        from notifications.push import notifier
        notifier.notify(
            title="New Work Order",
            message=f"{wo.submitter} submitted: {wo.title}",
            category="work_order",
            native=wo.priority in (WorkOrderPriority.CRITICAL, WorkOrderPriority.HIGH),
        )
    except Exception:
        pass

    logger.info("Work order submitted: %s (risk=%d, mode=%s)", wo.title, risk, mode)

    return {
        "success": True,
        "work_order_id": wo.id,
        "title": wo.title,
        "risk_score": risk,
        "execution_mode": mode,
        "status": "triaged",
    }


@router.post("/submit/json", response_class=JSONResponse)
async def submit_work_order_json(request: Request):
    """Submit a new work order (JSON body)."""
    body = await request.json()
    files = body.get("related_files", [])
    if isinstance(files, str):
        files = [f.strip() for f in files.split(",") if f.strip()]

    wo = create_work_order(
        title=body.get("title", ""),
        description=body.get("description", ""),
        priority=body.get("priority", "medium"),
        category=body.get("category", "suggestion"),
        submitter=body.get("submitter", "unknown"),
        submitter_type=body.get("submitter_type", "user"),
        related_files=files,
    )

    auto = should_auto_execute(wo)
    risk = compute_risk_score(wo)
    mode = "auto" if auto else "manual"
    update_work_order_status(
        wo.id, WorkOrderStatus.TRIAGED, execution_mode=mode,
    )

    try:
        from notifications.push import notifier
        notifier.notify(
            title="New Work Order",
            message=f"{wo.submitter} submitted: {wo.title}",
            category="work_order",
        )
    except Exception:
        pass

    logger.info("Work order submitted (JSON): %s (risk=%d, mode=%s)", wo.title, risk, mode)

    return {
        "success": True,
        "work_order_id": wo.id,
        "title": wo.title,
        "risk_score": risk,
        "execution_mode": mode,
        "status": "triaged",
    }


# ── CRUD / Query ───────────────────────────────────────────────────────────────


@router.get("", response_class=JSONResponse)
async def list_orders(
    status: Optional[str] = None,
    priority: Optional[str] = None,
    category: Optional[str] = None,
    submitter: Optional[str] = None,
    limit: int = 100,
):
    """List work orders with optional filters."""
    s = WorkOrderStatus(status) if status else None
    p = WorkOrderPriority(priority) if priority else None
    c = WorkOrderCategory(category) if category else None

    orders = list_work_orders(status=s, priority=p, category=c, submitter=submitter, limit=limit)
    return {
        "work_orders": [
            {
                "id": wo.id,
                "title": wo.title,
                "description": wo.description,
                "priority": wo.priority.value,
                "category": wo.category.value,
                "status": wo.status.value,
                "submitter": wo.submitter,
                "submitter_type": wo.submitter_type,
                "execution_mode": wo.execution_mode,
                "created_at": wo.created_at,
                "updated_at": wo.updated_at,
            }
            for wo in orders
        ],
        "count": len(orders),
    }


@router.get("/api/counts", response_class=JSONResponse)
async def work_order_counts():
    """Get work order counts by status (for nav badges)."""
    counts = get_counts_by_status()
    return {
        "pending": counts.get("submitted", 0) + counts.get("triaged", 0),
        "in_progress": counts.get("in_progress", 0),
        "total": sum(counts.values()),
        "by_status": counts,
    }


# ── Dashboard UI (must be before /{wo_id} to avoid path conflict) ─────────────


@router.get("/queue", response_class=HTMLResponse)
async def work_order_queue_page(request: Request):
    """Work order queue dashboard page."""
    pending = list_work_orders(status=WorkOrderStatus.SUBMITTED) + \
              list_work_orders(status=WorkOrderStatus.TRIAGED)
    active = list_work_orders(status=WorkOrderStatus.APPROVED) + \
             list_work_orders(status=WorkOrderStatus.IN_PROGRESS)
    completed = list_work_orders(status=WorkOrderStatus.COMPLETED, limit=20)
    rejected = list_work_orders(status=WorkOrderStatus.REJECTED, limit=10)

    return templates.TemplateResponse(
        request,
        "work_orders.html",
        {
            "page_title": "Work Orders",
            "pending": pending,
            "active": active,
            "completed": completed,
            "rejected": rejected,
            "pending_count": len(pending),
            "priorities": [p.value for p in WorkOrderPriority],
            "categories": [c.value for c in WorkOrderCategory],
        },
    )


@router.get("/queue/pending", response_class=HTMLResponse)
async def work_order_pending_partial(request: Request):
    """HTMX partial: pending work orders."""
    pending = list_work_orders(status=WorkOrderStatus.SUBMITTED) + \
              list_work_orders(status=WorkOrderStatus.TRIAGED)
    return templates.TemplateResponse(
        request,
        "partials/work_order_cards.html",
        {"orders": pending, "section": "pending"},
    )


@router.get("/queue/active", response_class=HTMLResponse)
async def work_order_active_partial(request: Request):
    """HTMX partial: active work orders."""
    active = list_work_orders(status=WorkOrderStatus.APPROVED) + \
             list_work_orders(status=WorkOrderStatus.IN_PROGRESS)
    return templates.TemplateResponse(
        request,
        "partials/work_order_cards.html",
        {"orders": active, "section": "active"},
    )


# ── Single work order (must be after /queue, /api to avoid conflict) ──────────


@router.get("/{wo_id}", response_class=JSONResponse)
async def get_order(wo_id: str):
    """Get a single work order by ID."""
    wo = get_work_order(wo_id)
    if not wo:
        raise HTTPException(404, "Work order not found")
    return {
        "id": wo.id,
        "title": wo.title,
        "description": wo.description,
        "priority": wo.priority.value,
        "category": wo.category.value,
        "status": wo.status.value,
        "submitter": wo.submitter,
        "submitter_type": wo.submitter_type,
        "estimated_effort": wo.estimated_effort,
        "related_files": wo.related_files,
        "execution_mode": wo.execution_mode,
        "swarm_task_id": wo.swarm_task_id,
        "result": wo.result,
        "rejection_reason": wo.rejection_reason,
        "created_at": wo.created_at,
        "triaged_at": wo.triaged_at,
        "approved_at": wo.approved_at,
        "started_at": wo.started_at,
        "completed_at": wo.completed_at,
    }


# ── Workflow actions ───────────────────────────────────────────────────────────


@router.post("/{wo_id}/approve", response_class=HTMLResponse)
async def approve_order(request: Request, wo_id: str):
    """Approve a work order for execution."""
    wo = update_work_order_status(wo_id, WorkOrderStatus.APPROVED)
    if not wo:
        raise HTTPException(404, "Work order not found")
    return templates.TemplateResponse(
        request,
        "partials/work_order_card.html",
        {"wo": wo},
    )


@router.post("/{wo_id}/reject", response_class=HTMLResponse)
async def reject_order(request: Request, wo_id: str, reason: str = Form("")):
    """Reject a work order."""
    wo = update_work_order_status(
        wo_id, WorkOrderStatus.REJECTED, rejection_reason=reason,
    )
    if not wo:
        raise HTTPException(404, "Work order not found")
    return templates.TemplateResponse(
        request,
        "partials/work_order_card.html",
        {"wo": wo},
    )


@router.post("/{wo_id}/execute", response_class=JSONResponse)
async def execute_order(wo_id: str):
    """Trigger execution of an approved work order."""
    wo = get_work_order(wo_id)
    if not wo:
        raise HTTPException(404, "Work order not found")
    if wo.status not in (WorkOrderStatus.APPROVED, WorkOrderStatus.TRIAGED):
        raise HTTPException(400, f"Cannot execute work order in {wo.status.value} status")

    update_work_order_status(wo_id, WorkOrderStatus.IN_PROGRESS)

    try:
        from work_orders.executor import work_order_executor
        success, result = work_order_executor.execute(wo)
        if success:
            update_work_order_status(wo_id, WorkOrderStatus.COMPLETED, result=result)
        else:
            update_work_order_status(wo_id, WorkOrderStatus.COMPLETED, result=f"Failed: {result}")
    except Exception as exc:
        update_work_order_status(wo_id, WorkOrderStatus.COMPLETED, result=f"Error: {exc}")

    final = get_work_order(wo_id)
    return {
        "success": True,
        "work_order_id": wo_id,
        "status": final.status.value if final else "unknown",
        "result": final.result if final else str(exc),
    }
