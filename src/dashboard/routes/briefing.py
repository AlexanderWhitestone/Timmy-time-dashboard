"""Briefing routes — Morning briefing and approval queue.

GET  /briefing                         — render the briefing page
GET  /briefing/approvals               — HTMX partial: pending approval cards
POST /briefing/approvals/{id}/approve  — approve an item (HTMX)
POST /briefing/approvals/{id}/reject   — reject an item (HTMX)
"""

import logging
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from timmy.briefing import engine as briefing_engine
from timmy import approvals as approval_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/briefing", tags=["briefing"])
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


@router.get("", response_class=HTMLResponse)
async def get_briefing(request: Request):
    """Return today's briefing page (generated or cached)."""
    briefing = briefing_engine.get_or_generate()
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
