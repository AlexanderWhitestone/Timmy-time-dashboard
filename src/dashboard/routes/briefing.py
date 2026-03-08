"""Briefing routes — Morning briefing and approval queue.

GET  /briefing                         — render the briefing page
GET  /briefing/approvals               — HTMX partial: pending approval cards
POST /briefing/approvals/{id}/approve  — approve an item (HTMX)
POST /briefing/approvals/{id}/reject   — reject an item (HTMX)
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

from timmy.briefing import Briefing, engine as briefing_engine
from timmy import approvals as approval_store
from dashboard.templating import templates

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/briefing", tags=["briefing"])


@router.get("", response_class=HTMLResponse)
async def get_briefing(request: Request):
    """Return today's briefing page (generated or cached)."""
    try:
        briefing = briefing_engine.get_or_generate()
    except Exception:
        logger.exception("Briefing generation failed")
        now = datetime.now(timezone.utc)
        briefing = Briefing(
            generated_at=now,
            summary=(
                "Good morning. The briefing could not be generated right now. "
                "Check that Ollama is running and try again."
            ),
            period_start=now,
            period_end=now,
        )
    return templates.TemplateResponse(
        request,
        "briefing.html",
        {"briefing": briefing},
    )


@router.get("/approvals", response_class=HTMLResponse)
async def get_approvals(request: Request):
    """Return HTMX partial with all pending approval items."""
    items = approval_store.list_pending()
    return templates.TemplateResponse(
        request,
        "partials/approval_cards.html",
        {"items": items},
    )


@router.post("/approvals/{item_id}/approve", response_class=HTMLResponse)
async def approve_item(request: Request, item_id: str):
    """Approve an approval item; return the updated card via HTMX."""
    item = approval_store.approve(item_id)
    if item is None:
        return HTMLResponse("<p class='text-danger'>Item not found.</p>", status_code=404)
    return templates.TemplateResponse(
        request,
        "partials/approval_card_single.html",
        {"item": item},
    )


@router.post("/approvals/{item_id}/reject", response_class=HTMLResponse)
async def reject_item(request: Request, item_id: str):
    """Reject an approval item; return the updated card via HTMX."""
    item = approval_store.reject(item_id)
    if item is None:
        return HTMLResponse("<p class='text-danger'>Item not found.</p>", status_code=404)
    return templates.TemplateResponse(
        request,
        "partials/approval_card_single.html",
        {"item": item},
    )


@router.post("/regenerate", response_class=JSONResponse)
async def regenerate_briefing():
    """Force-regenerate today's briefing."""
    try:
        briefing = briefing_engine.generate()
        return JSONResponse({"success": True, "generated_at": str(briefing.generated_at)})
    except Exception as exc:
        logger.exception("Failed to regenerate briefing")
        return JSONResponse({"success": False, "error": str(exc)}, status_code=500)
