"""Task processor for Timmy — consumes tasks from the queue one at a time.

This module provides a background loop that Timmy uses to process tasks
from the queue, including chat responses and self-generated tasks.
"""

import asyncio
import logging
from typing import Optional, Callable

from swarm.task_queue.models import (
    QueueTask,
    TaskStatus,
    get_current_task_for_agent,
    get_next_pending_task,
    update_task_status,
    update_task_steps,
    get_task,
)

logger = logging.getLogger(__name__)


class TaskProcessor:
    """Processes tasks from the queue for a specific agent."""

    def __init__(self, agent_id: str = "timmy"):
        self.agent_id = agent_id
        self._current_task: Optional[QueueTask] = None
        self._running = False
        self._handlers: dict[str, Callable] = {}
        self._user_callback: Optional[Callable[[str, str], None]] = (
            None  # (message_type, content)
        )

    def register_handler(self, task_type: str, handler: Callable[[QueueTask], str]):
        """Register a handler for a specific task type.

        Handler receives the task and returns the result string.
        """
        self._handlers[task_type] = handler

    def set_user_callback(self, callback: Callable[[str, str], None]):
        """Set callback for pushing messages to the user.

        Args:
            callback: Function that takes (message_type, content)
                     message_type: 'response', 'progress', 'notification'
        """
        self._user_callback = callback

    def push_to_user(self, message_type: str, content: str):
        """Push a message to the user via the registered callback."""
        if self._user_callback:
            try:
                self._user_callback(message_type, content)
            except Exception as e:
                logger.error("Failed to push message to user: %s", e)
        else:
            logger.debug("No user callback set, message not pushed: %s", content[:100])

    async def process_next_task(self) -> Optional[QueueTask]:
        """Process the next available task for this agent.

        Returns the task that was processed, or None if no tasks available.
        """
        # Check if already working on something
        current = get_current_task_for_agent(self.agent_id)
        if current:
            logger.debug("Already processing task: %s", current.id)
            return None

        # Get next task
        task = get_next_pending_task(self.agent_id)
        if not task:
            logger.debug("No pending tasks for %s", self.agent_id)
            return None

        # Start processing
        self._current_task = task
        update_task_status(task.id, TaskStatus.RUNNING)

        try:
            logger.info("Processing task: %s (type: %s)", task.title, task.task_type)

            # Update steps to show we're working
            update_task_steps(
                task.id,
                [{"description": f"Processing: {task.title}", "status": "running"}],
            )

            # Get handler for this task type
            handler = self._handlers.get(task.task_type)
            if handler:
                result = handler(task)
            else:
                result = f"No handler for task type: {task.task_type}"

            # Mark complete
            update_task_status(task.id, TaskStatus.COMPLETED, result=result)
            update_task_steps(
                task.id,
                [{"description": f"Completed: {task.title}", "status": "completed"}],
            )

            logger.info("Task completed: %s", task.id)
            return task

        except Exception as e:
            logger.error("Task failed: %s - %s", task.id, e)
            update_task_status(task.id, TaskStatus.FAILED, result=str(e))
            raise
        finally:
            self._current_task = None

    async def run_loop(self, interval_seconds: float = 5.0):
        """Run the task processing loop.

        This should be called as a background task.
        """
        self._running = True
        logger.info("Task processor started for %s", self.agent_id)

        while self._running:
            try:
                await self.process_next_task()
            except Exception as e:
                logger.error("Task processor error: %s", e)

            await asyncio.sleep(interval_seconds)

        logger.info("Task processor stopped for %s", self.agent_id)

    def stop(self):
        """Stop the task processing loop."""
        self._running = False

    @property
    def current_task(self) -> Optional[QueueTask]:
        """Get the currently processing task."""
        if self._current_task:
            return get_task(self._current_task.id)
        return get_current_task_for_agent(self.agent_id)


# Global processor instance
task_processor = TaskProcessor("timmy")


def get_task_processor() -> TaskProcessor:
    """Get the global task processor instance."""
    return task_processor
