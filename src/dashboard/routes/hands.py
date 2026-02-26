"""Hands Dashboard Routes.

API endpoints and HTMX views for managing autonomous Hands:
- Hand status and control
- Approval queue management
- Execution history
- Manual triggering
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse

from hands import HandRegistry, HandRunner, HandScheduler
from hands.models import HandConfig, HandStatus, TriggerType

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/hands", tags=["hands"])

# Global instances (would be properly injected in production)
_registry: Optional[HandRegistry] = None
_scheduler: Optional[HandScheduler] = None
_runner: Optional[HandRunner] = None


def get_registry() -> HandRegistry:
    """Get or create HandRegistry singleton."""
    global _registry
    if _registry is None:
        _registry = HandRegistry()
    return _registry


def get_scheduler() -> HandScheduler:
    """Get or create HandScheduler singleton."""
    global _scheduler
    if _scheduler is None:
        _scheduler = HandScheduler(get_registry())
    return _scheduler


def get_runner() -> HandRunner:
    """Get or create HandRunner singleton."""
    global _runner
    if _runner is None:
        _runner = HandRunner(get_registry())
    return _runner


# ── API Endpoints ─────────────────────────────────────────────────────────

@router.get("/api/hands")
async def api_list_hands():
    """List all Hands with their status."""
    registry = get_registry()
    
    hands = []
    for hand in registry.list_hands():
        state = registry.get_state(hand.name)
        hands.append({
            "name": hand.name,
            "description": hand.description,
            "enabled": hand.enabled,
            "status": state.status.value,
            "schedule": hand.schedule.cron if hand.schedule else None,
            "last_run": state.last_run.isoformat() if state.last_run else None,
            "next_run": state.next_run.isoformat() if state.next_run else None,
            "run_count": state.run_count,
        })
    
    return hands


@router.get("/api/hands/{name}")
async def api_get_hand(name: str):
    """Get detailed information about a Hand."""
    registry = get_registry()
    
    try:
        hand = registry.get_hand(name)
        state = registry.get_state(name)
        
        return {
            "name": hand.name,
            "description": hand.description,
            "enabled": hand.enabled,
            "version": hand.version,
            "author": hand.author,
            "status": state.status.value,
            "schedule": {
                "cron": hand.schedule.cron if hand.schedule else None,
                "timezone": hand.schedule.timezone if hand.schedule else "UTC",
            },
            "tools": {
                "required": hand.tools_required,
                "optional": hand.tools_optional,
            },
            "approval_gates": [
                {"action": g.action, "description": g.description}
                for g in hand.approval_gates
            ],
            "output": {
                "dashboard": hand.output.dashboard,
                "channel": hand.output.channel,
                "format": hand.output.format,
            },
            "state": state.to_dict(),
        }
        
    except Exception as e:
        return JSONResponse(
            status_code=404,
            content={"error": f"Hand not found: {name}"},
        )


@router.post("/api/hands/{name}/trigger")
async def api_trigger_hand(name: str):
    """Manually trigger a Hand to run."""
    scheduler = get_scheduler()
    
    success = await scheduler.trigger_hand_now(name)
    
    if success:
        return {"success": True, "message": f"Hand {name} triggered"}
    else:
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": f"Failed to trigger Hand {name}"},
        )


@router.post("/api/hands/{name}/pause")
async def api_pause_hand(name: str):
    """Pause a scheduled Hand."""
    scheduler = get_scheduler()
    
    if scheduler.pause_hand(name):
        return {"success": True, "message": f"Hand {name} paused"}
    else:
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": f"Failed to pause Hand {name}"},
        )


@router.post("/api/hands/{name}/resume")
async def api_resume_hand(name: str):
    """Resume a paused Hand."""
    scheduler = get_scheduler()
    
    if scheduler.resume_hand(name):
        return {"success": True, "message": f"Hand {name} resumed"}
    else:
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": f"Failed to resume Hand {name}"},
        )


@router.get("/api/approvals")
async def api_get_pending_approvals():
    """Get all pending approval requests."""
    registry = get_registry()
    
    approvals = await registry.get_pending_approvals()
    
    return [
        {
            "id": a.id,
            "hand_name": a.hand_name,
            "action": a.action,
            "description": a.description,
            "created_at": a.created_at.isoformat(),
            "expires_at": a.expires_at.isoformat() if a.expires_at else None,
        }
        for a in approvals
    ]


@router.post("/api/approvals/{approval_id}/approve")
async def api_approve_request(approval_id: str):
    """Approve a pending request."""
    registry = get_registry()
    
    if await registry.resolve_approval(approval_id, approved=True):
        return {"success": True, "message": "Request approved"}
    else:
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": "Failed to approve request"},
        )


@router.post("/api/approvals/{approval_id}/reject")
async def api_reject_request(approval_id: str):
    """Reject a pending request."""
    registry = get_registry()
    
    if await registry.resolve_approval(approval_id, approved=False):
        return {"success": True, "message": "Request rejected"}
    else:
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": "Failed to reject request"},
        )


@router.get("/api/executions")
async def api_get_executions(hand_name: Optional[str] = None, limit: int = 50):
    """Get recent Hand executions."""
    registry = get_registry()
    
    executions = await registry.get_recent_executions(hand_name, limit)
    
    return executions


# ── HTMX Page Routes ─────────────────────────────────────────────────────

@router.get("", response_class=HTMLResponse)
async def hands_page(request: Request):
    """Main Hands dashboard page."""
    from dashboard.app import templates
    
    return templates.TemplateResponse(
        "hands.html",
        {
            "request": request,
            "title": "Hands",
        },
    )


@router.get("/list", response_class=HTMLResponse)
async def hands_list_partial(request: Request):
    """HTMX partial for Hands list."""
    from dashboard.app import templates
    
    registry = get_registry()
    
    hands_data = []
    for hand in registry.list_hands():
        state = registry.get_state(hand.name)
        hands_data.append({
            "config": hand,
            "state": state,
        })
    
    return templates.TemplateResponse(
        "partials/hands_list.html",
        {
            "request": request,
            "hands": hands_data,
        },
    )


@router.get("/approvals", response_class=HTMLResponse)
async def approvals_partial(request: Request):
    """HTMX partial for approval queue."""
    from dashboard.app import templates
    
    registry = get_registry()
    approvals = await registry.get_pending_approvals()
    
    return templates.TemplateResponse(
        "partials/approvals_list.html",
        {
            "request": request,
            "approvals": approvals,
        },
    )


@router.get("/executions", response_class=HTMLResponse)
async def executions_partial(request: Request, hand_name: Optional[str] = None):
    """HTMX partial for execution history."""
    from dashboard.app import templates
    
    registry = get_registry()
    executions = await registry.get_recent_executions(hand_name, limit=20)
    
    return templates.TemplateResponse(
        "partials/hand_executions.html",
        {
            "request": request,
            "executions": executions,
            "hand_name": hand_name,
        },
    )


@router.get("/{name}/detail", response_class=HTMLResponse)
async def hand_detail_partial(request: Request, name: str):
    """HTMX partial for Hand detail."""
    from dashboard.app import templates
    
    registry = get_registry()
    
    try:
        hand = registry.get_hand(name)
        state = registry.get_state(name)
        
        return templates.TemplateResponse(
            "partials/hand_detail.html",
            {
                "request": request,
                "hand": hand,
                "state": state,
            },
        )
    except Exception:
        return templates.TemplateResponse(
            "partials/error.html",
            {
                "request": request,
                "message": f"Hand {name} not found",
            },
        )
