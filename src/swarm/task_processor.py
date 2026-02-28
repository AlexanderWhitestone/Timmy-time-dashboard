"""Task processor for Timmy — consumes tasks from the queue one at a time.

This module provides a background loop that Timmy uses to process tasks
from the queue, including chat responses and self-generated tasks.

On startup, the processor reconciles zombie tasks (stuck in RUNNING from
a previous crash), drains all approved tasks, then enters the steady-state
polling loop.  Tasks that have no registered handler are moved to BACKLOGGED
so they don't block the queue.
"""

import asyncio
import logging
from typing import Optional, Callable

from swarm.task_queue.models import (
    QueueTask,
    TaskStatus,
    get_all_actionable_tasks,
    get_current_task_for_agent,
    get_next_pending_task,
    list_tasks,
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

    def reconcile_zombie_tasks(self) -> int:
        """Reset tasks stuck in RUNNING from a previous crash.

        Called once on startup.  Any task in RUNNING status is assumed to
        be orphaned (the process that was executing it died).  These are
        moved back to APPROVED so the processor can retry them.

        Returns the count of tasks reset.
        """
        zombies = list_tasks(status=TaskStatus.RUNNING, assigned_to=self.agent_id)
        count = 0
        for task in zombies:
            update_task_status(
                task.id,
                TaskStatus.FAILED,
                result="Server restarted — task did not complete. Will be retried.",
            )
            # Immediately re-queue as approved so it gets picked up again
            update_task_status(task.id, TaskStatus.APPROVED, result=None)
            count += 1
            logger.info(
                "Recycled zombie task: %s (%s)", task.title, task.id
            )
        if count:
            logger.info("Reconciled %d zombie task(s) for %s", count, self.agent_id)
        return count

    def _backlog_task(self, task: QueueTask, reason: str) -> None:
        """Move a task to the backlog with a reason."""
        update_task_status(
            task.id,
            TaskStatus.BACKLOGGED,
            result=f"Backlogged: {reason}",
            backlog_reason=reason,
        )
        update_task_steps(
            task.id,
            [{"description": f"Backlogged: {reason}", "status": "backlogged"}],
        )
        logger.info("Task backlogged: %s — %s", task.title, reason)

    async def process_single_task(self, task: QueueTask) -> Optional[QueueTask]:
        """Process one specific task.  Backlog it if we can't handle it.

        Returns the task on success, or None if backlogged/failed.
        """
        # No handler → backlog immediately
        handler = self._handlers.get(task.task_type)
        if not handler:
            self._backlog_task(task, f"No handler for task type: {task.task_type}")
            return None

        # Tasks still awaiting approval shouldn't be auto-executed
        if task.status == TaskStatus.PENDING_APPROVAL and task.requires_approval:
            logger.debug("Skipping task %s — needs human approval", task.id)
            return None

        self._current_task = task
        update_task_status(task.id, TaskStatus.RUNNING)

        try:
            logger.info("Processing task: %s (type: %s)", task.title, task.task_type)

            update_task_steps(
                task.id,
                [{"description": f"Processing: {task.title}", "status": "running"}],
            )

            result = handler(task)

            update_task_status(task.id, TaskStatus.COMPLETED, result=result)
            update_task_steps(
                task.id,
                [{"description": f"Completed: {task.title}", "status": "completed"}],
            )

            logger.info("Task completed: %s", task.id)
            return task

        except Exception as e:
            error_msg = str(e)
            logger.error("Task failed: %s - %s", task.id, error_msg)

            # Determine if this is a permanent (backlog) or transient (fail) error
            if self._is_permanent_failure(e):
                self._backlog_task(task, error_msg)
            else:
                update_task_status(task.id, TaskStatus.FAILED, result=error_msg)

            return None
        finally:
            self._current_task = None

    def _is_permanent_failure(self, error: Exception) -> bool:
        """Decide whether an error means the task can never succeed.

        Permanent failures get backlogged; transient ones stay as FAILED
        so they can be retried.
        """
        msg = str(error).lower()
        permanent_indicators = [
            "no handler",
            "not implemented",
            "unsupported",
            "not supported",
            "permission denied",
            "forbidden",
            "not found",
            "invalid task",
        ]
        return any(indicator in msg for indicator in permanent_indicators)

    async def drain_queue(self) -> dict:
        """Iterate through ALL actionable tasks right now — called on startup.

        Processes every approved/auto-approved task in priority order.
        Tasks that can't be handled are backlogged.  Tasks still requiring
        human approval are skipped (left in PENDING_APPROVAL).

        Returns a summary dict with counts of processed, backlogged, skipped.
        """
        tasks = get_all_actionable_tasks(self.agent_id)
        summary = {"processed": 0, "backlogged": 0, "skipped": 0, "failed": 0}

        if not tasks:
            logger.info("Startup drain: no pending tasks for %s", self.agent_id)
            return summary

        logger.info(
            "Startup drain: %d task(s) to iterate through for %s",
            len(tasks),
            self.agent_id,
        )

        for task in tasks:
            # Skip tasks that need human approval
            if task.status == TaskStatus.PENDING_APPROVAL and task.requires_approval:
                logger.debug("Drain: skipping %s (needs approval)", task.title)
                summary["skipped"] += 1
                continue

            # No handler? Backlog it
            if task.task_type not in self._handlers:
                self._backlog_task(task, f"No handler for task type: {task.task_type}")
                summary["backlogged"] += 1
                continue

            # Try to process
            result = await self.process_single_task(task)
            if result:
                summary["processed"] += 1
            else:
                # Check if it was backlogged vs failed
                refreshed = get_task(task.id)
                if refreshed and refreshed.status == TaskStatus.BACKLOGGED:
                    summary["backlogged"] += 1
                else:
                    summary["failed"] += 1

        logger.info(
            "Startup drain complete: %d processed, %d backlogged, %d skipped, %d failed",
            summary["processed"],
            summary["backlogged"],
            summary["skipped"],
            summary["failed"],
        )
        return summary

    async def process_next_task(self) -> Optional[QueueTask]:
        """Process the next available task for this agent.

        Returns the task that was processed, or None if no tasks available.
        Uses in-memory _current_task (not DB status) to check concurrency,
        so zombie RUNNING rows from a previous crash don't block the queue.
        """
        # Check if we're actively working on something right now
        if self._current_task is not None:
            logger.debug("Already processing task: %s", self._current_task.id)
            return None

        # Get next approved task (pending_approval escalations are skipped)
        task = get_next_pending_task(self.agent_id)
        if not task:
            logger.debug("No pending tasks for %s", self.agent_id)
            return None

        return await self.process_single_task(task)

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
