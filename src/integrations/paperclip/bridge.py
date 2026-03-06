"""Paperclip bridge — CEO-level orchestration logic.

Timmy acts as the CEO: reviews issues, delegates to agents, tracks goals,
and approves/rejects work.  All business logic lives here; routes stay thin.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from config import settings
from integrations.paperclip.client import PaperclipClient, paperclip
from integrations.paperclip.models import (
    CreateIssueRequest,
    PaperclipAgent,
    PaperclipGoal,
    PaperclipIssue,
    PaperclipStatusResponse,
    UpdateIssueRequest,
)

logger = logging.getLogger(__name__)


class PaperclipBridge:
    """Bidirectional bridge between Timmy and Paperclip.

    Timmy is the CEO — he creates issues, delegates to agents via wakeup,
    reviews results, and manages the company's goals.
    """

    def __init__(self, client: Optional[PaperclipClient] = None):
        self.client = client or paperclip

    # ── status / health ──────────────────────────────────────────────────

    async def get_status(self) -> PaperclipStatusResponse:
        """Return integration status for the dashboard."""
        if not settings.paperclip_enabled:
            return PaperclipStatusResponse(
                enabled=False,
                paperclip_url=settings.paperclip_url,
            )

        connected = await self.client.healthy()
        agent_count = 0
        issue_count = 0
        error = None

        if connected:
            try:
                agents = await self.client.list_agents()
                agent_count = len(agents)
                issues = await self.client.list_issues()
                issue_count = len(issues)
            except Exception as exc:
                error = str(exc)
        else:
            error = "Cannot reach Paperclip server"

        return PaperclipStatusResponse(
            enabled=True,
            connected=connected,
            paperclip_url=settings.paperclip_url,
            company_id=settings.paperclip_company_id,
            agent_count=agent_count,
            issue_count=issue_count,
            error=error,
        )

    # ── CEO actions: issue management ────────────────────────────────────

    async def create_and_assign(
        self,
        title: str,
        description: str = "",
        assignee_id: Optional[str] = None,
        priority: Optional[str] = None,
        wake: bool = True,
    ) -> Optional[PaperclipIssue]:
        """Create an issue and optionally assign + wake an agent.

        This is the primary CEO action: decide what needs doing, create
        the ticket, assign it to the right agent, and kick off execution.
        """
        req = CreateIssueRequest(
            title=title,
            description=description,
            priority=priority,
            assignee_id=assignee_id,
        )
        issue = await self.client.create_issue(req)
        if not issue:
            logger.error("Failed to create issue: %s", title)
            return None

        logger.info("Created issue %s: %s", issue.id, title)

        if assignee_id and wake:
            result = await self.client.wake_agent(assignee_id, issue_id=issue.id)
            if result:
                logger.info("Woke agent %s for issue %s", assignee_id, issue.id)
            else:
                logger.warning("Failed to wake agent %s", assignee_id)

        return issue

    async def delegate_issue(
        self,
        issue_id: str,
        agent_id: str,
        message: Optional[str] = None,
    ) -> bool:
        """Assign an existing issue to an agent and wake them."""
        updated = await self.client.update_issue(
            issue_id,
            UpdateIssueRequest(assignee_id=agent_id),
        )
        if not updated:
            return False

        if message:
            await self.client.add_comment(issue_id, f"[CEO] {message}")

        await self.client.wake_agent(agent_id, issue_id=issue_id)
        return True

    async def review_issue(
        self,
        issue_id: str,
    ) -> Dict[str, Any]:
        """Gather all context for CEO review of an issue."""
        issue = await self.client.get_issue(issue_id)
        comments = await self.client.list_comments(issue_id)

        return {
            "issue": issue.model_dump() if issue else None,
            "comments": [c.model_dump() for c in comments],
        }

    async def close_issue(self, issue_id: str, comment: Optional[str] = None) -> bool:
        """Close an issue as the CEO."""
        if comment:
            await self.client.add_comment(issue_id, f"[CEO] {comment}")
        result = await self.client.update_issue(
            issue_id,
            UpdateIssueRequest(status="done"),
        )
        return result is not None

    # ── CEO actions: team management ─────────────────────────────────────

    async def get_team(self) -> List[PaperclipAgent]:
        """Get the full agent roster."""
        return await self.client.list_agents()

    async def get_org_chart(self) -> Optional[Dict[str, Any]]:
        """Get the organizational hierarchy."""
        return await self.client.get_org()

    # ── CEO actions: goal management ─────────────────────────────────────

    async def list_goals(self) -> List[PaperclipGoal]:
        return await self.client.list_goals()

    async def set_goal(self, title: str, description: str = "") -> Optional[PaperclipGoal]:
        return await self.client.create_goal(title, description)

    # ── CEO actions: approvals ───────────────────────────────────────────

    async def pending_approvals(self) -> List[Dict[str, Any]]:
        return await self.client.list_approvals()

    async def approve(self, approval_id: str, comment: str = "") -> bool:
        result = await self.client.approve(approval_id, comment)
        return result is not None

    async def reject(self, approval_id: str, comment: str = "") -> bool:
        result = await self.client.reject(approval_id, comment)
        return result is not None

    # ── CEO actions: monitoring ──────────────────────────────────────────

    async def active_runs(self) -> List[Dict[str, Any]]:
        """Get currently running heartbeat executions."""
        return await self.client.list_heartbeat_runs()

    async def cancel_run(self, run_id: str) -> bool:
        result = await self.client.cancel_run(run_id)
        return result is not None


# Module-level singleton
bridge = PaperclipBridge()
