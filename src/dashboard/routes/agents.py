from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from timmy.agent import create_timmy
from dashboard.store import message_log

router = APIRouter(prefix="/agents", tags=["agents"])
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))

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

    try:
        agent = create_timmy()
        run = agent.run(message, stream=False)
        response_text = run.content if hasattr(run, "content") else str(run)
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
