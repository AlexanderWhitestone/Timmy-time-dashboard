"""Grok (xAI) dashboard routes — premium cloud augmentation controls.

Endpoints
---------
GET  /grok/status     — JSON status (API)
POST /grok/toggle     — Enable/disable Grok Mode (HTMX)
POST /grok/chat       — Direct Grok query (HTMX)
GET  /grok/stats      — Usage statistics (JSON)
"""

import logging
from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/grok", tags=["grok"])
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))

# In-memory toggle state (persists per process lifetime)
_grok_mode_active: bool = False


@router.get("/status")
async def grok_status():
    """Return Grok backend status as JSON."""
    from timmy.backends import grok_available

    status = {
        "enabled": settings.grok_enabled,
        "available": grok_available(),
        "active": _grok_mode_active,
        "model": settings.grok_default_model,
        "free_mode": settings.grok_free,
        "max_sats_per_query": settings.grok_max_sats_per_query,
        "api_key_set": bool(settings.xai_api_key),
    }

    # Include usage stats if backend exists
    try:
        from timmy.backends import get_grok_backend
        backend = get_grok_backend()
        status["stats"] = {
            "total_requests": backend.stats.total_requests,
            "total_prompt_tokens": backend.stats.total_prompt_tokens,
            "total_completion_tokens": backend.stats.total_completion_tokens,
            "estimated_cost_sats": backend.stats.estimated_cost_sats,
            "errors": backend.stats.errors,
        }
    except Exception:
        status["stats"] = None

    return status


@router.post("/toggle")
async def toggle_grok_mode(request: Request):
    """Toggle Grok Mode on/off. Returns HTMX partial for the toggle card."""
    global _grok_mode_active

    from timmy.backends import grok_available

    if not grok_available():
        return HTMLResponse(
            '<div class="alert" style="color: var(--danger);">'
            "Grok unavailable — set GROK_ENABLED=true and XAI_API_KEY in .env"
            "</div>",
            status_code=200,
        )

    _grok_mode_active = not _grok_mode_active
    state = "ACTIVE" if _grok_mode_active else "STANDBY"

    logger.info("Grok Mode toggled: %s", state)

    # Log to Spark
    try:
        from spark.engine import spark_engine
        import json

        spark_engine.on_tool_executed(
            agent_id="timmy",
            tool_name="grok_mode_toggle",
            success=True,
        )
    except Exception:
        pass

    return HTMLResponse(
        _render_toggle_card(_grok_mode_active),
        status_code=200,
    )


@router.post("/chat", response_class=HTMLResponse)
async def grok_chat(request: Request, message: str = Form(...)):
    """Send a message directly to Grok and return HTMX chat partial."""
    from timmy.backends import grok_available, get_grok_backend
    from dashboard.store import message_log
    from datetime import datetime

    timestamp = datetime.now().strftime("%H:%M:%S")

    if not grok_available():
        error = "Grok is not available. Set GROK_ENABLED=true and XAI_API_KEY."
        message_log.append(role="user", content=f"[Grok] {message}", timestamp=timestamp, source="browser")
        message_log.append(role="error", content=error, timestamp=timestamp, source="browser")
        return templates.TemplateResponse(
            request,
            "partials/chat_message.html",
            {
                "user_message": f"[Grok] {message}",
                "response": None,
                "error": error,
                "timestamp": timestamp,
            },
        )

    backend = get_grok_backend()

    # Generate invoice if monetization is active
    invoice_note = ""
    if not settings.grok_free:
        try:
            from lightning.factory import get_backend as get_ln_backend

            ln = get_ln_backend()
            sats = min(settings.grok_max_sats_per_query, 100)
            inv = ln.create_invoice(sats, f"Grok: {message[:50]}")
            invoice_note = f" | {sats} sats"
        except Exception:
            pass

    try:
        result = backend.run(message)
        response_text = f"**[Grok]{invoice_note}:** {result.content}"
    except Exception as exc:
        response_text = None
        error = f"Grok error: {exc}"

    message_log.append(
        role="user", content=f"[Ask Grok] {message}", timestamp=timestamp, source="browser"
    )
    if response_text:
        message_log.append(role="agent", content=response_text, timestamp=timestamp, source="browser")
        return templates.TemplateResponse(
            request,
            "partials/chat_message.html",
            {
                "user_message": f"[Ask Grok] {message}",
                "response": response_text,
                "error": None,
                "timestamp": timestamp,
            },
        )
    else:
        message_log.append(role="error", content=error, timestamp=timestamp, source="browser")
        return templates.TemplateResponse(
            request,
            "partials/chat_message.html",
            {
                "user_message": f"[Ask Grok] {message}",
                "response": None,
                "error": error,
                "timestamp": timestamp,
            },
        )


@router.get("/stats")
async def grok_stats():
    """Return detailed Grok usage statistics."""
    try:
        from timmy.backends import get_grok_backend

        backend = get_grok_backend()
        return {
            "total_requests": backend.stats.total_requests,
            "total_prompt_tokens": backend.stats.total_prompt_tokens,
            "total_completion_tokens": backend.stats.total_completion_tokens,
            "total_latency_ms": round(backend.stats.total_latency_ms, 2),
            "avg_latency_ms": round(
                backend.stats.total_latency_ms / max(backend.stats.total_requests, 1),
                2,
            ),
            "estimated_cost_sats": backend.stats.estimated_cost_sats,
            "errors": backend.stats.errors,
            "model": settings.grok_default_model,
        }
    except Exception as exc:
        return {"error": str(exc)}


def _render_toggle_card(active: bool) -> str:
    """Render the Grok Mode toggle card HTML."""
    color = "#00ff88" if active else "#666"
    state = "ACTIVE" if active else "STANDBY"
    glow = "0 0 20px rgba(0, 255, 136, 0.4)" if active else "none"

    return f"""
    <div id="grok-toggle-card"
         style="border: 2px solid {color}; border-radius: 12px; padding: 16px;
                background: var(--bg-secondary); box-shadow: {glow};
                transition: all 0.3s ease;">
        <div style="display: flex; justify-content: space-between; align-items: center;">
            <div>
                <div style="font-weight: 700; font-size: 1.1rem; color: {color};">
                    GROK MODE: {state}
                </div>
                <div style="font-size: 0.8rem; color: var(--text-muted); margin-top: 4px;">
                    xAI frontier reasoning | {settings.grok_default_model}
                </div>
            </div>
            <button hx-post="/grok/toggle"
                    hx-target="#grok-toggle-card"
                    hx-swap="outerHTML"
                    style="background: {color}; color: #000; border: none;
                           border-radius: 8px; padding: 8px 20px; cursor: pointer;
                           font-weight: 700; font-family: inherit;">
                {'DEACTIVATE' if active else 'ACTIVATE'}
            </button>
        </div>
    </div>
    """


def is_grok_mode_active() -> bool:
    """Check if Grok Mode is currently active (used by other modules)."""
    return _grok_mode_active
