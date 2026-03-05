"""Client API for submitting and querying Celery tasks.

All functions gracefully return None/empty when Celery is unavailable.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


def _get_app():
    """Get the Celery app instance."""
    from infrastructure.celery.app import celery_app
    return celery_app


def submit_chat_task(
    prompt: str,
    agent_id: str = "timmy",
    session_id: str = "celery",
) -> str | None:
    """Submit a chat task to the Celery queue.

    Returns:
        Task ID string, or None if Celery is unavailable.
    """
    app = _get_app()
    if app is None:
        logger.debug("Celery unavailable — chat task not submitted")
        return None

    try:
        from infrastructure.celery.tasks import run_agent_chat
        result = run_agent_chat.delay(prompt, agent_id=agent_id, session_id=session_id)
        logger.info("Submitted chat task %s for %s", result.id, agent_id)
        return result.id
    except Exception as exc:
        logger.warning("Failed to submit chat task: %s", exc)
        return None


def submit_tool_task(
    tool_name: str,
    kwargs: dict | None = None,
    agent_id: str = "timmy",
) -> str | None:
    """Submit a tool execution task to the Celery queue.

    Returns:
        Task ID string, or None if Celery is unavailable.
    """
    app = _get_app()
    if app is None:
        logger.debug("Celery unavailable — tool task not submitted")
        return None

    try:
        from infrastructure.celery.tasks import execute_tool
        result = execute_tool.delay(tool_name, kwargs=kwargs or {}, agent_id=agent_id)
        logger.info("Submitted tool task %s: %s", result.id, tool_name)
        return result.id
    except Exception as exc:
        logger.warning("Failed to submit tool task: %s", exc)
        return None


def get_task_status(task_id: str) -> dict[str, Any] | None:
    """Get status of a Celery task.

    Returns:
        Dict with state, result, etc., or None if Celery unavailable.
    """
    app = _get_app()
    if app is None:
        return None

    try:
        result = app.AsyncResult(task_id)
        data: dict[str, Any] = {
            "task_id": task_id,
            "state": result.state,
            "ready": result.ready(),
        }
        if result.ready():
            data["result"] = result.result
        if result.failed():
            data["error"] = str(result.result)
        return data
    except Exception as exc:
        logger.warning("Failed to get task status: %s", exc)
        return None


def get_active_tasks() -> list[dict[str, Any]]:
    """List currently active/reserved tasks.

    Returns:
        List of task dicts, or empty list if Celery unavailable.
    """
    app = _get_app()
    if app is None:
        return []

    try:
        inspector = app.control.inspect()
        active = inspector.active() or {}
        reserved = inspector.reserved() or {}

        tasks = []
        for worker_tasks in active.values():
            for t in worker_tasks:
                tasks.append({
                    "task_id": t.get("id"),
                    "name": t.get("name"),
                    "state": "STARTED",
                    "args": t.get("args"),
                    "worker": t.get("hostname"),
                })
        for worker_tasks in reserved.values():
            for t in worker_tasks:
                tasks.append({
                    "task_id": t.get("id"),
                    "name": t.get("name"),
                    "state": "PENDING",
                    "args": t.get("args"),
                })
        return tasks
    except Exception as exc:
        logger.warning("Failed to inspect active tasks: %s", exc)
        return []


def revoke_task(task_id: str) -> bool:
    """Revoke (cancel) a pending or running task.

    Returns:
        True if revoke was sent, False if Celery unavailable.
    """
    app = _get_app()
    if app is None:
        return False

    try:
        app.control.revoke(task_id, terminate=True)
        logger.info("Revoked task %s", task_id)
        return True
    except Exception as exc:
        logger.warning("Failed to revoke task: %s", exc)
        return False
