import logging
import re
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

# ── Task queue detection ──────────────────────────────────────────────────
# Patterns that indicate the user wants to queue a task rather than chat
_QUEUE_PATTERNS = [
    re.compile(r"\b(?:add|put|schedule|queue|submit)\b.*\b(?:to the|on the|in the)?\s*(?:queue|task(?:\s*queue)?|task list)\b", re.IGNORECASE),
    re.compile(r"\bschedule\s+(?:this|that|a)\b", re.IGNORECASE),
    re.compile(r"\bcreate\s+(?:a\s+)?task\b", re.IGNORECASE),
]


def _extract_task_from_message(message: str) -> dict | None:
    """If the message looks like a task-queue request, return task details."""
    for pattern in _QUEUE_PATTERNS:
        if pattern.search(message):
            # Strip the queue instruction to get the actual task description
            title = re.sub(
                r"\b(?:add|put|schedule|queue|submit|create)\b.*?\b(?:to the|on the|in the|a)?\s*(?:queue|task(?:\s*queue)?|task list)\b",
                "", message, flags=re.IGNORECASE,
            ).strip(" ,:;-")
            # If stripping removed everything, use the full message
            if not title or len(title) < 5:
                title = message
            return {"title": title[:120], "description": message}
    return None

# Static metadata for known agents — enriched onto live registry entries.
_AGENT_METADATA: dict[str, dict] = {
    "timmy": {
        "type": "sovereign",
        "model": "llama3.2",
        "backend": "ollama",
        "version": "1.0.0",
    },
}


@router.get("")
async def list_agents():
    """Return all registered agents with live status from the swarm registry."""
    from swarm import registry as swarm_registry
    agents = swarm_registry.list_agents()
    return {
        "agents": [
            {
                "id": a.id,
                "name": a.name,
                "status": a.status,
                "capabilities": a.capabilities,
                **_AGENT_METADATA.get(a.id, {}),
            }
            for a in agents
        ]
    }


@router.get("/timmy/panel", response_class=HTMLResponse)
async def timmy_panel(request: Request):
    """Timmy chat panel — for HTMX main-panel swaps."""
    from swarm import registry as swarm_registry
    agent = swarm_registry.get_agent("timmy")
    return templates.TemplateResponse(request, "partials/timmy_panel.html", {"agent": agent})


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
    timestamp = datetime.now().strftime("%H:%M:%S")
    response_text = None
    error_text = None

    # Check if the user wants to queue a task instead of chatting
    task_info = _extract_task_from_message(message)
    if task_info:
        try:
            from task_queue.models import create_task
            task = create_task(
                title=task_info["title"],
                description=task_info["description"],
                created_by="user",
                assigned_to="timmy",
                priority="normal",
                requires_approval=True,
            )
            response_text = (
                f"Task queued for approval: **{task.title}**\n\n"
                f"Status: `{task.status.value}` | "
                f"[View Task Queue](/tasks)"
            )
            logger.info("Chat → task queue: %s (id=%s)", task.title, task.id)
        except Exception as exc:
            logger.error("Failed to create task from chat: %s", exc)
            # Fall through to normal chat if task creation fails
            task_info = None

    # Normal chat path (also used as fallback if task creation failed)
    if not task_info:
        try:
            response_text = timmy_chat(message)
        except Exception as exc:
            error_text = f"Timmy is offline: {exc}"

    message_log.append(role="user", content=message, timestamp=timestamp)
    if response_text is not None:
        message_log.append(role="agent", content=response_text, timestamp=timestamp)
    else:
        message_log.append(role="error", content=error_text, timestamp=timestamp)

    return templates.TemplateResponse(
        request,
        "partials/chat_message.html",
        {
            "user_message": message,
            "response": response_text,
            "error": error_text,
            "timestamp": timestamp,
        },
    )
