"""Mobile-optimized dashboard route — /mobile endpoint.

Provides a simplified, mobile-first view of the dashboard that
prioritizes the chat interface and essential status information.
Designed for quick access from a phone's home screen.

The /mobile/local endpoint loads a small LLM directly into the
browser via WebLLM so Timmy can run on an iPhone with no server.
"""

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from config import settings

router = APIRouter(tags=["mobile"])
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


@router.get("/mobile", response_class=HTMLResponse)
async def mobile_dashboard(request: Request):
    """Render the mobile-optimized dashboard.

    Falls back to the main index template which is already responsive.
    A dedicated mobile template can be added later for a more
    streamlined experience.
    """
    return templates.TemplateResponse(request, "index.html")


@router.get("/mobile/local", response_class=HTMLResponse)
async def mobile_local_dashboard(request: Request):
    """Mobile dashboard with in-browser local model inference.

    Loads a small LLM (via WebLLM / WebGPU) directly into Safari
    so Timmy works on an iPhone without any server connection.
    Falls back to server-side Ollama when the local model is
    unavailable or the user prefers it.
    """
    return templates.TemplateResponse(
        request,
        "mobile_local.html",
        {
            "browser_model_enabled": settings.browser_model_enabled,
            "browser_model_id": settings.browser_model_id,
            "browser_model_fallback": settings.browser_model_fallback,
            "server_model": settings.ollama_model,
            "page_title": "Timmy — Local AI",
        },
    )


@router.get("/mobile/local-models")
async def local_models_config():
    """Return browser model configuration for the JS client."""
    return {
        "enabled": settings.browser_model_enabled,
        "default_model": settings.browser_model_id,
        "fallback_to_server": settings.browser_model_fallback,
        "server_model": settings.ollama_model,
        "server_url": settings.ollama_url,
    }


@router.get("/mobile/status")
async def mobile_status():
    """Lightweight status endpoint optimized for mobile polling."""
    from dashboard.routes.health import check_ollama

    ollama_ok = await check_ollama()
    return {
        "ollama": "up" if ollama_ok else "down",
        "model": settings.ollama_model,
        "agent": "timmy",
        "ready": True,
        "browser_model_enabled": settings.browser_model_enabled,
        "browser_model_id": settings.browser_model_id,
    }
