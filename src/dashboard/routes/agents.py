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
    timestamp = datetime.now().strftime("%H:%M:%S")
    response_text = None
    error_text = None

    # Check if the user wants to queue a task instead of chatting
    task_info = _extract_task_from_message(message)
    if task_info:
        try:
            from swarm.task_queue.models import create_task

            task = create_task(
                title=task_info["title"],
                description=task_info["description"],
                created_by="user",
                assigned_to=task_info.get("agent", "timmy"),
                priority=task_info.get("priority", "normal"),
                requires_approval=True,
            )
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

    # Normal chat path (also used as fallback if task creation failed)
    if not task_info:
        try:
            now = datetime.now()
            context_parts = [
                f"[System: Current date/time is {now.strftime('%A, %B %d, %Y at %I:%M %p')}]"
            ]
            if _QUEUE_QUERY_PATTERN.search(message):
                queue_ctx = _build_queue_context()
                if queue_ctx:
                    context_parts.append(queue_ctx)
            context_prefix = "\n".join(context_parts) + "\n\n"
            response_text = timmy_chat(context_prefix + message)
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
