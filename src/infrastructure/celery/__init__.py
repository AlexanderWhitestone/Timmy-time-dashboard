"""Celery task queue integration — optional background task processing.

Gracefully degrades when Redis or Celery are unavailable.
"""

from infrastructure.celery.app import celery_app
from infrastructure.celery.client import (
    get_active_tasks,
    get_task_status,
    revoke_task,
    submit_chat_task,
    submit_tool_task,
)

__all__ = [
    "celery_app",
    "get_active_tasks",
    "get_task_status",
    "revoke_task",
    "submit_chat_task",
    "submit_tool_task",
]
