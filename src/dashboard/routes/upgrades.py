"""Self-Upgrade Queue dashboard routes."""

from pathlib import Path

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from upgrades.models import list_upgrades, get_upgrade, UpgradeStatus, get_pending_count
from upgrades.queue import UpgradeQueue

router = APIRouter(prefix="/self-modify", tags=["upgrades"])
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


@router.get("/queue", response_class=HTMLResponse)
async def upgrade_queue_page(request: Request):
    """Upgrade queue dashboard."""
    pending = list_upgrades(status=UpgradeStatus.PROPOSED)
    approved = list_upgrades(status=UpgradeStatus.APPROVED)
    history = list_upgrades(status=None)[:20]  # All recent
    
    # Separate history by status
    applied = [u for u in history if u.status == UpgradeStatus.APPLIED][:10]
    rejected = [u for u in history if u.status == UpgradeStatus.REJECTED][:5]
    failed = [u for u in history if u.status == UpgradeStatus.FAILED][:5]
    
    return templates.TemplateResponse(
        request,
        "upgrade_queue.html",
        {
            "page_title": "Upgrade Queue",
            "pending": pending,
            "approved": approved,
            "applied": applied,
            "rejected": rejected,
            "failed": failed,
            "pending_count": len(pending),
        },
    )


@router.post("/queue/{upgrade_id}/approve", response_class=JSONResponse)
async def approve_upgrade_endpoint(upgrade_id: str):
    """Approve an upgrade proposal."""
    upgrade = UpgradeQueue.approve(upgrade_id)
    
    if not upgrade:
        raise HTTPException(404, "Upgrade not found or not in proposed state")
    
    return {"success": True, "upgrade_id": upgrade_id, "status": upgrade.status.value}


@router.post("/queue/{upgrade_id}/reject", response_class=JSONResponse)
async def reject_upgrade_endpoint(upgrade_id: str):
    """Reject an upgrade proposal."""
    upgrade = UpgradeQueue.reject(upgrade_id)
    
    if not upgrade:
        raise HTTPException(404, "Upgrade not found or not in proposed state")
    
    return {"success": True, "upgrade_id": upgrade_id, "status": upgrade.status.value}


@router.post("/queue/{upgrade_id}/apply", response_class=JSONResponse)
async def apply_upgrade_endpoint(upgrade_id: str):
    """Apply an approved upgrade."""
    success, message = UpgradeQueue.apply(upgrade_id)
    
    if not success:
        raise HTTPException(400, message)
    
    return {"success": True, "message": message}


@router.get("/queue/{upgrade_id}/diff", response_class=HTMLResponse)
async def view_diff(request: Request, upgrade_id: str):
    """View full diff for an upgrade."""
    upgrade = get_upgrade(upgrade_id)
    
    if not upgrade:
        raise HTTPException(404, "Upgrade not found")
    
    diff = UpgradeQueue.get_full_diff(upgrade_id)
    
    return templates.TemplateResponse(
        request,
        "upgrade_diff.html",
        {
            "upgrade": upgrade,
            "diff": diff,
        },
    )


@router.get("/api/pending-count", response_class=JSONResponse)
async def get_pending_upgrade_count():
    """Get count of pending upgrades (for nav badge)."""
    return {"count": get_pending_count()}
