"""Lightning Ledger routes for viewing transactions and balance."""

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from lightning.ledger import (
    TransactionType,
    TransactionStatus,
    list_transactions,
    get_balance,
    get_transaction_stats,
)

router = APIRouter(prefix="/lightning", tags=["ledger"])
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


@router.get("/ledger", response_class=HTMLResponse)
async def ledger_page(
    request: Request,
    tx_type: Optional[str] = None,
    status: Optional[str] = None,
):
    """Lightning ledger page with balance and transactions."""
    # Parse filters
    filter_type = None
    if tx_type:
        try:
            filter_type = TransactionType(tx_type)
        except ValueError:
            pass
    
    filter_status = None
    if status:
        try:
            filter_status = TransactionStatus(status)
        except ValueError:
            pass
    
    # Get data
    balance = get_balance()
    transactions = list_transactions(
        tx_type=filter_type,
        status=filter_status,
        limit=50,
    )
    stats = get_transaction_stats(days=7)
    
    return templates.TemplateResponse(
        request,
        "ledger.html",
        {
            "page_title": "Lightning Ledger",
            "balance": balance,
            "transactions": transactions,
            "stats": stats,
            "filter_type": tx_type,
            "filter_status": status,
            "tx_types": [t.value for t in TransactionType],
            "tx_statuses": [s.value for s in TransactionStatus],
        },
    )


@router.get("/ledger/partial", response_class=HTMLResponse)
async def ledger_partial(
    request: Request,
    tx_type: Optional[str] = None,
    status: Optional[str] = None,
):
    """Ledger transactions partial for HTMX updates."""
    filter_type = None
    if tx_type:
        try:
            filter_type = TransactionType(tx_type)
        except ValueError:
            pass
    
    filter_status = None
    if status:
        try:
            filter_status = TransactionStatus(status)
        except ValueError:
            pass
    
    transactions = list_transactions(
        tx_type=filter_type,
        status=filter_status,
        limit=50,
    )
    
    return templates.TemplateResponse(
        request,
        "partials/ledger_table.html",
        {
            "transactions": transactions,
        },
    )
