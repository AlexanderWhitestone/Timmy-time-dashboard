"""Paperclip AI API client.

Async HTTP client for communicating with a remote Paperclip server.
All methods degrade gracefully — log the error, return a fallback, never crash.

Paperclip API is mounted at ``/api`` and uses ``local_trusted`` mode on the
VPS, so the board actor is implicit.  When the server sits behind an nginx
auth-gate the client authenticates with Basic-auth on the first request and
re-uses the session cookie thereafter.
"""

from __future__ import annotations

import base64
import logging
from typing import Any, Dict, List, Optional

import httpx

from config import settings
from integrations.paperclip.models import (
    AddCommentRequest,
    CreateIssueRequest,
    PaperclipAgent,
    PaperclipComment,
    PaperclipGoal,
    PaperclipIssue,
    UpdateIssueRequest,
)

logger = logging.getLogger(__name__)


class PaperclipClient:
    """Thin async wrapper around the Paperclip REST API.

    All public methods return typed results on success or ``None`` / ``[]``
    on failure so callers never need to handle exceptions.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout: int = 30,
    ):
        self._base_url = (base_url or settings.paperclip_url).rstrip("/")
        self._api_key = api_key or settings.paperclip_api_key
        self._timeout = timeout or settings.paperclip_timeout
        self._client: Optional[httpx.AsyncClient] = None

    # ── lifecycle ────────────────────────────────────────────────────────

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            headers: Dict[str, str] = {"Accept": "application/json"}
            if self._api_key:
                headers["Authorization"] = f"Bearer {self._api_key}"
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                headers=headers,
                timeout=self._timeout,
            )
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    # ── helpers ──────────────────────────────────────────────────────────

    async def _get(self, path: str, params: Optional[Dict] = None) -> Optional[Any]:
        try:
            resp = await self._get_client().get(path, params=params)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            logger.warning("Paperclip GET %s failed: %s", path, exc)
            return None

    async def _post(self, path: str, json: Optional[Dict] = None) -> Optional[Any]:
        try:
            resp = await self._get_client().post(path, json=json)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            logger.warning("Paperclip POST %s failed: %s", path, exc)
            return None

    async def _patch(self, path: str, json: Optional[Dict] = None) -> Optional[Any]:
        try:
            resp = await self._get_client().patch(path, json=json)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            logger.warning("Paperclip PATCH %s failed: %s", path, exc)
            return None

    async def _delete(self, path: str) -> bool:
        try:
            resp = await self._get_client().delete(path)
            resp.raise_for_status()
            return True
        except Exception as exc:
            logger.warning("Paperclip DELETE %s failed: %s", path, exc)
            return False

    # ── health ───────────────────────────────────────────────────────────

    async def healthy(self) -> bool:
        """Quick connectivity check."""
        data = await self._get("/api/health")
        return data is not None

    # ── companies ────────────────────────────────────────────────────────

    async def list_companies(self) -> List[Dict[str, Any]]:
        data = await self._get("/api/companies")
        return data if isinstance(data, list) else []

    # ── agents ───────────────────────────────────────────────────────────

    async def list_agents(self, company_id: Optional[str] = None) -> List[PaperclipAgent]:
        cid = company_id or settings.paperclip_company_id
        if not cid:
            logger.warning("paperclip_company_id not set — cannot list agents")
            return []
        data = await self._get(f"/api/companies/{cid}/agents")
        if not isinstance(data, list):
            return []
        return [PaperclipAgent(**a) for a in data]

    async def get_agent(self, agent_id: str) -> Optional[PaperclipAgent]:
        data = await self._get(f"/api/agents/{agent_id}")
        return PaperclipAgent(**data) if data else None

    async def wake_agent(
        self,
        agent_id: str,
        issue_id: Optional[str] = None,
        message: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Trigger a heartbeat wake for an agent."""
        body: Dict[str, Any] = {}
        if issue_id:
            body["issueId"] = issue_id
        if message:
            body["message"] = message
        return await self._post(f"/api/agents/{agent_id}/wakeup", json=body)

    async def get_org(self, company_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        cid = company_id or settings.paperclip_company_id
        if not cid:
            return None
        return await self._get(f"/api/companies/{cid}/org")

    # ── issues (tickets) ─────────────────────────────────────────────────

    async def list_issues(
        self,
        company_id: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[PaperclipIssue]:
        cid = company_id or settings.paperclip_company_id
        if not cid:
            return []
        params: Dict[str, str] = {}
        if status:
            params["status"] = status
        data = await self._get(f"/api/companies/{cid}/issues", params=params)
        if not isinstance(data, list):
            return []
        return [PaperclipIssue(**i) for i in data]

    async def get_issue(self, issue_id: str) -> Optional[PaperclipIssue]:
        data = await self._get(f"/api/issues/{issue_id}")
        return PaperclipIssue(**data) if data else None

    async def create_issue(
        self,
        req: CreateIssueRequest,
        company_id: Optional[str] = None,
    ) -> Optional[PaperclipIssue]:
        cid = company_id or settings.paperclip_company_id
        if not cid:
            logger.warning("paperclip_company_id not set — cannot create issue")
            return None
        data = await self._post(
            f"/api/companies/{cid}/issues",
            json=req.model_dump(exclude_none=True),
        )
        return PaperclipIssue(**data) if data else None

    async def update_issue(
        self,
        issue_id: str,
        req: UpdateIssueRequest,
    ) -> Optional[PaperclipIssue]:
        data = await self._patch(
            f"/api/issues/{issue_id}",
            json=req.model_dump(exclude_none=True),
        )
        return PaperclipIssue(**data) if data else None

    async def delete_issue(self, issue_id: str) -> bool:
        return await self._delete(f"/api/issues/{issue_id}")

    # ── issue comments ───────────────────────────────────────────────────

    async def list_comments(self, issue_id: str) -> List[PaperclipComment]:
        data = await self._get(f"/api/issues/{issue_id}/comments")
        if not isinstance(data, list):
            return []
        return [PaperclipComment(**c) for c in data]

    async def add_comment(
        self,
        issue_id: str,
        content: str,
    ) -> Optional[PaperclipComment]:
        data = await self._post(
            f"/api/issues/{issue_id}/comments",
            json={"content": content},
        )
        return PaperclipComment(**data) if data else None

    # ── issue workflow ───────────────────────────────────────────────────

    async def checkout_issue(self, issue_id: str) -> Optional[Dict[str, Any]]:
        """Assign an issue to Timmy (checkout)."""
        body: Dict[str, Any] = {}
        if settings.paperclip_agent_id:
            body["agentId"] = settings.paperclip_agent_id
        return await self._post(f"/api/issues/{issue_id}/checkout", json=body)

    async def release_issue(self, issue_id: str) -> Optional[Dict[str, Any]]:
        """Release a checked-out issue."""
        return await self._post(f"/api/issues/{issue_id}/release")

    # ── goals ────────────────────────────────────────────────────────────

    async def list_goals(self, company_id: Optional[str] = None) -> List[PaperclipGoal]:
        cid = company_id or settings.paperclip_company_id
        if not cid:
            return []
        data = await self._get(f"/api/companies/{cid}/goals")
        if not isinstance(data, list):
            return []
        return [PaperclipGoal(**g) for g in data]

    async def create_goal(
        self,
        title: str,
        description: str = "",
        company_id: Optional[str] = None,
    ) -> Optional[PaperclipGoal]:
        cid = company_id or settings.paperclip_company_id
        if not cid:
            return None
        data = await self._post(
            f"/api/companies/{cid}/goals",
            json={"title": title, "description": description},
        )
        return PaperclipGoal(**data) if data else None

    # ── heartbeat runs ───────────────────────────────────────────────────

    async def list_heartbeat_runs(
        self,
        company_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        cid = company_id or settings.paperclip_company_id
        if not cid:
            return []
        data = await self._get(f"/api/companies/{cid}/heartbeat-runs")
        return data if isinstance(data, list) else []

    async def get_run_events(self, run_id: str) -> List[Dict[str, Any]]:
        data = await self._get(f"/api/heartbeat-runs/{run_id}/events")
        return data if isinstance(data, list) else []

    async def cancel_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        return await self._post(f"/api/heartbeat-runs/{run_id}/cancel")

    # ── approvals ────────────────────────────────────────────────────────

    async def list_approvals(self, company_id: Optional[str] = None) -> List[Dict[str, Any]]:
        cid = company_id or settings.paperclip_company_id
        if not cid:
            return []
        data = await self._get(f"/api/companies/{cid}/approvals")
        return data if isinstance(data, list) else []

    async def approve(self, approval_id: str, comment: str = "") -> Optional[Dict[str, Any]]:
        body: Dict[str, Any] = {}
        if comment:
            body["comment"] = comment
        return await self._post(f"/api/approvals/{approval_id}/approve", json=body)

    async def reject(self, approval_id: str, comment: str = "") -> Optional[Dict[str, Any]]:
        body: Dict[str, Any] = {}
        if comment:
            body["comment"] = comment
        return await self._post(f"/api/approvals/{approval_id}/reject", json=body)


# Module-level singleton
paperclip = PaperclipClient()
