"""Cascade Router status routes."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from timmy.cascade_adapter import get_cascade_adapter
from dashboard.templating import templates

router = APIRouter(prefix="/router", tags=["router"])


@router.get("/status", response_class=HTMLResponse)
async def router_status_page(request: Request):
    """Cascade Router status dashboard."""
    adapter = get_cascade_adapter()
    
    providers = adapter.get_provider_status()
    preferred = adapter.get_preferred_provider()
    
    # Calculate overall stats
    total_requests = sum(p["metrics"]["total"] for p in providers)
    total_success = sum(p["metrics"]["success"] for p in providers)
    total_failed = sum(p["metrics"]["failed"] for p in providers)
    
    avg_latency = 0.0
    if providers:
        avg_latency = sum(p["metrics"]["avg_latency_ms"] for p in providers) / len(providers)
    
    return templates.TemplateResponse(
        request,
        "router_status.html",
        {
            "page_title": "Router Status",
            "providers": providers,
            "preferred_provider": preferred,
            "total_requests": total_requests,
            "total_success": total_success,
            "total_failed": total_failed,
            "avg_latency_ms": round(avg_latency, 1),
        },
    )


@router.get("/api/providers")
async def get_providers():
    """API endpoint for provider status (JSON)."""
    adapter = get_cascade_adapter()
    return {
        "providers": adapter.get_provider_status(),
        "preferred": adapter.get_preferred_provider(),
    }
