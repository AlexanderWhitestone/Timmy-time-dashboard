"""Celery background task tool — allows Timmy to submit tasks to a worker queue.

When Celery/Redis is unavailable, returns a graceful error dict.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


def submit_background_task(task_description: str, agent_id: str = "default") -> dict[str, Any]:
    """Submit a task to run in the background via Celery.

    Use this tool when a user asks you to work on something that might
    take a while — research, analysis, code generation, etc. The task
    will be processed by a background worker and the user can check
    progress on the /tasks page.

    Args:
        task_description: What to work on (sent as a chat prompt to the agent).
        agent_id: Which agent should handle it (default: timmy).

    Returns:
        Dict with task_id, status, and message.
    """
    try:
        from infrastructure.celery.client import submit_chat_task

        task_id = submit_chat_task(
            prompt=task_description,
            agent_id=agent_id,
            session_id="celery-background",
        )

        if task_id is None:
            return {
                "success": False,
                "error": "Background task queue is not available (Redis/Celery not running).",
                "task_id": None,
            }

        return {
            "success": True,
            "task_id": task_id,
            "agent_id": agent_id,
            "status": "submitted",
            "message": (
                f"Background task submitted (ID: {task_id[:8]}...). "
                f"Check progress at /tasks. Task: {task_description[:100]}"
            ),
        }

    except Exception as exc:
        logger.error("Failed to submit background task: %s", exc)
        return {
            "success": False,
            "error": str(exc),
            "task_id": None,
        }
