"""Paperclip task runner — automated issue processing loop.

Timmy grabs open issues assigned to him, processes each one, posts a
completion comment, marks the issue done, and creates a recursive
follow-up task for himself.

Green-path workflow:
1. Poll Paperclip for open issues assigned to Timmy
2. Check out the first issue in queue
3. Process it (delegate to orchestrator)
4. Post completion comment with the result
5. Mark the issue done
6. Create a follow-up task for himself (recursive musing)
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Coroutine, Dict, List, Optional

from config import settings
from integrations.paperclip.bridge import PaperclipBridge, bridge as default_bridge
from integrations.paperclip.models import PaperclipIssue

logger = logging.getLogger(__name__)


class TaskRunner:
    """Autonomous task loop: grab → process → complete → follow-up.

    The runner operates on a single cycle via ``run_once`` (testable) or
    continuously via ``start`` with ``paperclip_poll_interval``.
    """

    def __init__(
        self,
        bridge: Optional[PaperclipBridge] = None,
        process_fn: Optional[Callable[[str, str, Dict], Coroutine[Any, Any, str]]] = None,
    ):
        self.bridge = bridge or default_bridge
        # process_fn(task_id, description, context) -> result string
        self._process_fn = process_fn
        self._running = False

    # ── single cycle ──────────────────────────────────────────────────

    async def grab_next_task(self) -> Optional[PaperclipIssue]:
        """Grab the first open issue assigned to Timmy."""
        agent_id = settings.paperclip_agent_id
        if not agent_id:
            logger.warning("paperclip_agent_id not set — cannot grab tasks")
            return None

        issues = await self.bridge.client.list_issues(status="open")
        # Filter to issues assigned to Timmy, take the first one
        for issue in issues:
            if issue.assignee_id == agent_id:
                return issue

        return None

    async def process_task(self, issue: PaperclipIssue) -> str:
        """Process an issue: check out, run through the processor, return result."""
        # Check out the issue so others know we're working on it
        await self.bridge.client.checkout_issue(issue.id)

        context = {
            "issue_id": issue.id,
            "title": issue.title,
            "priority": issue.priority,
            "labels": issue.labels,
        }

        if self._process_fn:
            result = await self._process_fn(issue.id, issue.description or issue.title, context)
        else:
            result = f"Processed task: {issue.title}"

        return result

    async def complete_task(self, issue: PaperclipIssue, result: str) -> bool:
        """Post completion comment and mark issue done."""
        # Post the result as a comment
        await self.bridge.client.add_comment(
            issue.id,
            f"[Timmy] Task completed.\n\n{result}",
        )

        # Mark the issue as done
        return await self.bridge.close_issue(issue.id, comment=None)

    async def create_follow_up(self, original: PaperclipIssue, result: str) -> Optional[PaperclipIssue]:
        """Create a recursive follow-up task for Timmy.

        Timmy muses about task automation and writes a follow-up issue
        assigned to himself — the recursive self-improvement loop.
        """
        follow_up_title = f"Follow-up: {original.title}"
        follow_up_description = (
            f"Automated follow-up from completed task '{original.title}' "
            f"(issue {original.id}).\n\n"
            f"Previous result:\n{result}\n\n"
            "Review the outcome and determine if further action is needed. "
            "Muse about task automation improvements and recursive self-improvement."
        )

        return await self.bridge.create_and_assign(
            title=follow_up_title,
            description=follow_up_description,
            assignee_id=settings.paperclip_agent_id,
            priority=original.priority,
            wake=False,  # Don't wake immediately — let the next poll pick it up
        )

    async def run_once(self) -> Optional[Dict[str, Any]]:
        """Execute one full cycle of the green-path workflow.

        Returns a summary dict on success, None if no work found.
        """
        # Step 1: Grab next task
        issue = await self.grab_next_task()
        if not issue:
            logger.debug("No tasks in queue for Timmy")
            return None

        logger.info("Grabbed task %s: %s", issue.id, issue.title)

        # Step 2: Process the task
        result = await self.process_task(issue)
        logger.info("Processed task %s", issue.id)

        # Step 3: Complete it
        completed = await self.complete_task(issue, result)
        if not completed:
            logger.warning("Failed to mark task %s as done", issue.id)

        # Step 4: Create follow-up
        follow_up = await self.create_follow_up(issue, result)
        follow_up_id = follow_up.id if follow_up else None
        if follow_up:
            logger.info("Created follow-up %s for task %s", follow_up.id, issue.id)

        return {
            "original_issue_id": issue.id,
            "original_title": issue.title,
            "result": result,
            "completed": completed,
            "follow_up_issue_id": follow_up_id,
        }

    # ── continuous loop ───────────────────────────────────────────────

    async def start(self) -> None:
        """Run the task loop continuously using paperclip_poll_interval."""
        interval = settings.paperclip_poll_interval
        if interval <= 0:
            logger.info("Task runner disabled (poll_interval=%d)", interval)
            return

        self._running = True
        logger.info("Task runner started (poll every %ds)", interval)

        while self._running:
            try:
                await self.run_once()
            except Exception as exc:
                logger.error("Task runner cycle failed: %s", exc)

            await asyncio.sleep(interval)

    def stop(self) -> None:
        """Signal the loop to stop."""
        self._running = False
        logger.info("Task runner stopping")


# Module-level singleton
task_runner = TaskRunner()
