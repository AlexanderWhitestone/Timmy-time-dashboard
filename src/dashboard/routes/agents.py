import logging
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from timmy.session import chat as timmy_chat
from dashboard.store import message_log

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agents", tags=["agents"])
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


@router.get("")
async def list_agents():
    """Return registered agents."""
    from config import settings

    return {
        "agents": [
            {
                "id": "orchestrator",
                "name": "Orchestrator",
                "status": "idle",
                "capabilities": "chat,reasoning,research,planning",
                "type": "local",
                "model": settings.ollama_model,
                "backend": "ollama",
                "version": "1.0.0",
            }
        ]
    }


@router.get("/timmy/panel", response_class=HTMLResponse)
async def timmy_panel(request: Request):
    """Chat panel — for HTMX main-panel swaps."""
    return templates.TemplateResponse(
        request, "partials/timmy_panel.html", {"agent": None}
    )


@router.get("/timmy/history", response_class=HTMLResponse)
async def get_history(request: Request):
    return templates.TemplateResponse(
        request,
        "partials/history.html",
        {"messages": message_log.all()},
    )


@router.delete("/timmy/history", response_class=HTMLResponse)
async def clear_history(request: Request):
    message_log.clear()
    return templates.TemplateResponse(
        request,
        "partials/history.html",
        {"messages": []},
    )


@router.post("/timmy/chat", response_class=HTMLResponse)
async def chat_timmy(request: Request, message: str = Form(...)):
    """Chat — synchronous response."""
    timestamp = datetime.now().strftime("%H:%M:%S")
    response_text = None
    error_text = None

    try:
        response_text = timmy_chat(message)
    except Exception as exc:
        logger.error("Chat error: %s", exc)
        error_text = f"Chat error: {exc}"

    message_log.append(role="user", content=message, timestamp=timestamp, source="browser")
    if response_text is not None:
        message_log.append(role="agent", content=response_text, timestamp=timestamp, source="browser")
    elif error_text:
        message_log.append(role="error", content=error_text, timestamp=timestamp, source="browser")

    return templates.TemplateResponse(
        request,
        "partials/chat_message.html",
        {
            "user_message": message,
            "response": response_text,
            "error": error_text,
            "timestamp": timestamp,
            "task_id": None,
            "queue_info": None,
        },
    )
