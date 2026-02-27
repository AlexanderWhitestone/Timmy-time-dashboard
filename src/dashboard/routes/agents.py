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
    re.compile(
        r"\b(?:add|put|schedule|queue|submit)\b.*\b(?:to the|on the|in the)?\s*(?:queue|task(?:\s*queue)?|task list)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\bschedule\s+(?:this|that|a)\b", re.IGNORECASE),
    re.compile(r"\bcreate\s+(?:a\s+|an\s+)?(?:\w+\s+){0,3}task\b", re.IGNORECASE),
]
# Questions about tasks/queue should NOT trigger task creation
_QUESTION_PREFIXES = re.compile(
    r"^(?:what|how|why|can you explain|could you explain|tell me about|explain|"
    r"what(?:'s| is| are| would))\b",
    re.IGNORECASE,
)
_QUESTION_FRAMES = re.compile(
    r"\b(?:how (?:do|does|would|can|should)|what (?:is|are|would)|"
    r"can you (?:explain|describe|tell)|best way to)\b",
    re.IGNORECASE,
)

# Known agent names for task assignment parsing
_KNOWN_AGENTS = frozenset(
    {
        "timmy",
        "echo",
        "mace",
        "helm",
        "seer",
        "forge",
        "quill",
        "pixel",
        "lyra",
        "reel",
    }
)
_AGENT_PATTERN = re.compile(
    r"\bfor\s+(" + "|".join(_KNOWN_AGENTS) + r")\b", re.IGNORECASE
)

# Priority keywords → task priority mapping
_PRIORITY_MAP = {
    "urgent": "urgent",
    "critical": "urgent",
    "asap": "urgent",
    "emergency": "urgent",
    "high priority": "high",
    "high-priority": "high",
    "important": "high",
    "low priority": "low",
    "low-priority": "low",
    "minor": "low",
}

# Queue context detection
_QUEUE_QUERY_PATTERN = re.compile(
    r"\b(?:task(?:s|\s+queue)?|queue|what(?:'s| is) (?:in |on )?(?:the )?queue)\b",
    re.IGNORECASE,
)


def _extract_agent_from_message(message: str) -> str:
    """Extract target agent name from message, defaulting to 'timmy'."""
    m = _AGENT_PATTERN.search(message)
    if m:
        return m.group(1).lower()
    return "timmy"


def _extract_priority_from_message(message: str) -> str:
    """Extract priority level from message, defaulting to 'normal'."""
    msg_lower = message.lower()
    for keyword, priority in sorted(_PRIORITY_MAP.items(), key=lambda x: -len(x[0])):
        if keyword in msg_lower:
            return priority
    return "normal"


def _extract_task_from_message(message: str) -> dict | None:
    """If the message looks like a task-queue request, return task details.

    Returns None for meta-questions about tasks (e.g. "how do I create a task?").
    """
    if _QUESTION_PREFIXES.search(message) or _QUESTION_FRAMES.search(message):
        return None
    for pattern in _QUEUE_PATTERNS:
        if pattern.search(message):
            # Strip the queue instruction to get the actual task description
            title = re.sub(
                r"\b(?:add|put|schedule|queue|submit|create)\b.*?\b(?:to the|on the|in the|an?)?(?:\s+\w+){0,3}\s*(?:queue|task(?:\s*queue)?|task list)\b",
                "",
                message,
                flags=re.IGNORECASE,
            ).strip(" ,:;-")
            # Strip "for {agent}" from title
            title = _AGENT_PATTERN.sub("", title).strip(" ,:;-")
            # Strip priority keywords from title
            title = re.sub(
                r"\b(?:urgent|critical|asap|emergency|high[- ]priority|important|low[- ]priority|minor)\b",
                "",
                title,
                flags=re.IGNORECASE,
            ).strip(" ,:;-")
            # Strip leading "to " that often remains
            title = re.sub(r"^to\s+", "", title, flags=re.IGNORECASE).strip()
            # Clean up double spaces
            title = re.sub(r"\s{2,}", " ", title).strip()
            # Fallback to full message if stripping removed everything
            if not title or len(title) < 5:
                title = message
            # Capitalize first letter
            title = title[0].upper() + title[1:] if title else title
            agent = _extract_agent_from_message(message)
            priority = _extract_priority_from_message(message)
            return {
                "title": title[:120],
                "description": message,
                "agent": agent,
                "priority": priority,
            }
    return None


def _build_queue_context() -> str:
    """Build a concise task queue summary for context injection."""
    try:
        from swarm.task_queue.models import get_counts_by_status, list_tasks, TaskStatus

        counts = get_counts_by_status()
        pending = counts.get("pending_approval", 0)
        running = counts.get("running", 0)
        completed = counts.get("completed", 0)

        parts = [
            f"[System: Task queue — {pending} pending approval, {running} running, {completed} completed."
        ]
        if pending > 0:
            tasks = list_tasks(status=TaskStatus.PENDING_APPROVAL, limit=5)
            if tasks:
                items = ", ".join(f'"{t.title}" ({t.assigned_to})' for t in tasks)
                parts.append(f"Pending: {items}.")
        if running > 0:
            tasks = list_tasks(status=TaskStatus.RUNNING, limit=5)
            if tasks:
                items = ", ".join(f'"{t.title}" ({t.assigned_to})' for t in tasks)
                parts.append(f"Running: {items}.")
        return " ".join(parts) + "]"
    except Exception as exc:
        logger.debug("Failed to build queue context: %s", exc)
        return ""


# Static metadata for known agents — enriched onto live registry entries.
_AGENT_METADATA: dict[str, dict] = {
    "timmy": {
        "type": "sovereign",
        "model": "",  # Injected dynamically from settings
        "backend": "ollama",
        "version": "1.0.0",
    },
}


@router.get("")
async def list_agents():
    """Return all registered agents with live status from the swarm registry."""
    from swarm import registry as swarm_registry
    from config import settings

    # Inject model name from settings into timmy metadata
    metadata = dict(_AGENT_METADATA)
    if "timmy" in metadata and not metadata["timmy"].get("model"):
        metadata["timmy"]["model"] = settings.ollama_model

    agents = swarm_registry.list_agents()
    return {
        "agents": [
            {
                "id": a.id,
                "name": a.name,
                "status": a.status,
                "capabilities": a.capabilities,
                **metadata.get(a.id, {}),
            }
            for a in agents
        ]
    }


@router.get("/timmy/panel", response_class=HTMLResponse)
async def timmy_panel(request: Request):
    """Timmy chat panel — for HTMX main-panel swaps."""
    from swarm import registry as swarm_registry

    agent = swarm_registry.get_agent("timmy")
    return templates.TemplateResponse(
        request, "partials/timmy_panel.html", {"agent": agent}
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
    """Chat with Timmy - queues message as task for async processing."""
    from swarm.task_queue.models import create_task, get_queue_status_for_task

    timestamp = datetime.now().strftime("%H:%M:%S")
    task_id = None
    response_text = None
    error_text = None
    queue_info = None

    # Check if the user wants to queue a task (explicit queue request)
    task_info = _extract_task_from_message(message)
    if task_info:
        try:
            task = create_task(
                title=task_info["title"],
                description=task_info["description"],
                created_by="user",
                assigned_to=task_info.get("agent", "timmy"),
                priority=task_info.get("priority", "normal"),
                requires_approval=True,
                task_type="task_request",
            )
            task_id = task.id
            priority_label = (
                f" | Priority: `{task.priority.value}`"
                if task.priority.value != "normal"
                else ""
            )
            response_text = (
                f"Task queued for approval: **{task.title}**\n\n"
                f"Assigned to: `{task.assigned_to}`{priority_label} | "
                f"Status: `{task.status.value}` | "
                f"[View Task Queue](/tasks)"
            )
            logger.info(
                "Chat → task queue: %s → %s (id=%s)",
                task.title,
                task.assigned_to,
                task.id,
            )
        except Exception as exc:
            logger.error("Failed to create task from chat: %s", exc)
            task_info = None

    # Normal chat: always queue for async processing
    if not task_info:
        try:
            import asyncio

            # Create a chat response task (auto-approved for timmy)
            # Priority is "high" to jump ahead of Timmy's self-generated "thought" tasks
            # but below any "urgent" tasks Timmy might create
            task = create_task(
                title=message[:100] + ("..." if len(message) > 100 else ""),
                description=message,
                created_by="user",
                assigned_to="timmy",
                priority="high",  # Higher than thought tasks, lower than urgent
                requires_approval=True,
                auto_approve=True,  # Auto-approve chat responses
                task_type="chat_response",
            )
            task_id = task.id
            queue_info = get_queue_status_for_task(task.id)

            # Push queue position via WebSocket immediately
            try:
                from infrastructure.ws_manager.handler import ws_manager

                asyncio.create_task(
                    ws_manager.broadcast(
                        "queue_update",
                        {
                            "task_id": task.id,
                            "position": queue_info.get("position", 1),
                            "total": queue_info.get("total", 1),
                            "percent_ahead": queue_info.get("percent_ahead", 0),
                            "status": "queued",
                        },
                    )
                )
            except Exception as e:
                logger.debug("Failed to push queue update via WS: %s", e)

            # Acknowledge queuing
            position = queue_info.get("position", 1)
            total = queue_info.get("total", 1)
            percent_ahead = queue_info.get("percent_ahead", 0)

            response_text = (
                f"Message queued for Timmy's attention.\n\n"
                f"**Queue position:** {position}/{total} ({100 - percent_ahead}% complete ahead of you)\n\n"
                f"_Timmy will respond shortly..._"
            )
            logger.info(
                "Chat → queued: %s (id=%s, position=%d/%d)",
                message[:50],
                task.id,
                position,
                total,
            )
        except Exception as exc:
            logger.error("Failed to queue chat message: %s", exc)
            error_text = f"Failed to queue message: {exc}"

    # Log to message history (for context, even though async)
    message_log.append(role="user", content=message, timestamp=timestamp)
    if response_text is not None:
        message_log.append(role="agent", content=response_text, timestamp=timestamp)
    else:
        message_log.append(
            role="error", content=error_text or "Unknown error", timestamp=timestamp
        )

    return templates.TemplateResponse(
        request,
        "partials/chat_message.html",
        {
            "user_message": message,
            "response": response_text,
            "error": error_text,
            "timestamp": timestamp,
            "task_id": task_id,
            "queue_info": queue_info,
        },
    )
