"""System-level dashboard routes (ledger, upgrades, etc.)."""

import logging

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

from dashboard.templating import templates

logger = logging.getLogger(__name__)

router = APIRouter(tags=["system"])


@router.get("/lightning/ledger", response_class=HTMLResponse)
async def lightning_ledger(request: Request):
    """Ledger and balance page."""
    # Mock data for now, as this seems to be a UI-first feature
    balance = {
        "available_sats": 1337,
        "incoming_total_sats": 2000,
        "outgoing_total_sats": 663,
        "fees_paid_sats": 5,
        "net_sats": 1337,
        "pending_incoming_sats": 0,
        "pending_outgoing_sats": 0,
    }
    
    # Mock transactions
    from collections import namedtuple
    from enum import Enum
    
    class TxType(Enum):
        incoming = "incoming"
        outgoing = "outgoing"
        
    class TxStatus(Enum):
        completed = "completed"
        pending = "pending"
        
    Tx = namedtuple("Tx", ["tx_type", "status", "amount_sats", "payment_hash", "memo", "created_at"])
    
    transactions = [
        Tx(TxType.outgoing, TxStatus.completed, 50, "hash1", "Model inference", "2026-03-04 10:00:00"),
        Tx(TxType.incoming, TxStatus.completed, 1000, "hash2", "Manual deposit", "2026-03-03 15:00:00"),
    ]
    
    return templates.TemplateResponse(
        request,
        "ledger.html",
        {
            "balance": balance,
            "transactions": transactions,
            "tx_types": ["incoming", "outgoing"],
            "tx_statuses": ["completed", "pending"],
            "filter_type": None,
            "filter_status": None,
            "stats": {},
        },
    )


@router.get("/self-modify/queue", response_class=HTMLResponse)
async def self_modify_queue(request: Request):
    """Self-modification / upgrade queue page."""
    return templates.TemplateResponse(
        request,
        "upgrade_queue.html",
        {
            "pending_count": 0,
            "pending": [],
            "approved": [],
            "applied": [],
            "rejected": [],
            "failed": [],
        },
    )


@router.get("/swarm/mission-control", response_class=HTMLResponse)
async def mission_control(request: Request):
    return templates.TemplateResponse(request, "mission_control.html", {})


@router.get("/bugs", response_class=HTMLResponse)
async def bugs_page(request: Request):
    return templates.TemplateResponse(request, "bugs.html", {
        "bugs": [], "total": 0, "stats": {}, "filter_status": None,
    })


@router.get("/self-coding", response_class=HTMLResponse)
async def self_coding(request: Request):
    return templates.TemplateResponse(request, "self_coding.html", {"stats": {}})


@router.get("/hands", response_class=HTMLResponse)
async def hands_page(request: Request):
    return templates.TemplateResponse(request, "hands.html", {"executions": []})


@router.get("/creative/ui", response_class=HTMLResponse)
async def creative_ui(request: Request):
    return templates.TemplateResponse(request, "creative.html", {})


@router.get("/api/notifications", response_class=JSONResponse)
async def api_notifications():
    """Return recent system events for the notification dropdown."""
    try:
        from spark.engine import spark_engine
        events = spark_engine.get_timeline(limit=20)
        return JSONResponse([
            {
                "event_type": e.event_type,
                "title": getattr(e, "description", e.event_type),
                "timestamp": str(getattr(e, "timestamp", "")),
            }
            for e in events
        ])
    except Exception:
        return JSONResponse([])
