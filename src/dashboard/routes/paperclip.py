"""Paperclip AI integration routes.

Timmy-as-CEO: create issues, delegate to agents, review work, manage goals.
All business logic lives in the bridge — these routes stay thin.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/paperclip", tags=["paperclip"])


def _disabled_response() -> JSONResponse:
    return JSONResponse({"enabled": False, "detail": "Paperclip integration is disabled"})


# ── Status ───────────────────────────────────────────────────────────────────


@router.get("/status")
async def paperclip_status():
    """Integration health check."""
    if not settings.paperclip_enabled:
        return _disabled_response()

    from integrations.paperclip.bridge import bridge

    status = await bridge.get_status()
    return status.model_dump()


# ── Issues (CEO creates & manages tickets) ───────────────────────────────────


@router.get("/issues")
async def list_issues(status: Optional[str] = None):
    """List all issues in the company."""
    if not settings.paperclip_enabled:
        return _disabled_response()

    from integrations.paperclip.bridge import bridge

    issues = await bridge.client.list_issues(status=status)
    return [i.model_dump() for i in issues]


@router.get("/issues/{issue_id}")
async def get_issue(issue_id: str):
    """Get issue details with comments (CEO review)."""
    if not settings.paperclip_enabled:
        return _disabled_response()

    from integrations.paperclip.bridge import bridge

    return await bridge.review_issue(issue_id)


@router.post("/issues")
async def create_issue(request: Request):
    """Create a new issue and optionally assign to an agent."""
    if not settings.paperclip_enabled:
        return _disabled_response()

    body = await request.json()
    title = body.get("title")
    if not title:
        return JSONResponse({"error": "title is required"}, status_code=400)

    from integrations.paperclip.bridge import bridge

    issue = await bridge.create_and_assign(
        title=title,
        description=body.get("description", ""),
        assignee_id=body.get("assignee_id"),
        priority=body.get("priority"),
        wake=body.get("wake", True),
    )

    if not issue:
        return JSONResponse({"error": "Failed to create issue"}, status_code=502)

    return issue.model_dump()


@router.post("/issues/{issue_id}/delegate")
async def delegate_issue(issue_id: str, request: Request):
    """Delegate an issue to an agent (CEO assignment)."""
    if not settings.paperclip_enabled:
        return _disabled_response()

    body = await request.json()
    agent_id = body.get("agent_id")
    if not agent_id:
        return JSONResponse({"error": "agent_id is required"}, status_code=400)

    from integrations.paperclip.bridge import bridge

    ok = await bridge.delegate_issue(
        issue_id=issue_id,
        agent_id=agent_id,
        message=body.get("message"),
    )

    if not ok:
        return JSONResponse({"error": "Failed to delegate issue"}, status_code=502)

    return {"ok": True, "issue_id": issue_id, "agent_id": agent_id}


@router.post("/issues/{issue_id}/close")
async def close_issue(issue_id: str, request: Request):
    """Close an issue (CEO sign-off)."""
    if not settings.paperclip_enabled:
        return _disabled_response()

    body = await request.json()

    from integrations.paperclip.bridge import bridge

    ok = await bridge.close_issue(issue_id, comment=body.get("comment"))

    if not ok:
        return JSONResponse({"error": "Failed to close issue"}, status_code=502)

    return {"ok": True, "issue_id": issue_id}


@router.post("/issues/{issue_id}/comment")
async def add_comment(issue_id: str, request: Request):
    """Add a CEO comment to an issue."""
    if not settings.paperclip_enabled:
        return _disabled_response()

    body = await request.json()
    content = body.get("content")
    if not content:
        return JSONResponse({"error": "content is required"}, status_code=400)

    from integrations.paperclip.bridge import bridge

    comment = await bridge.client.add_comment(issue_id, f"[CEO] {content}")

    if not comment:
        return JSONResponse({"error": "Failed to add comment"}, status_code=502)

    return comment.model_dump()


# ── Agents (team management) ─────────────────────────────────────────────────


@router.get("/agents")
async def list_agents():
    """List all agents in the org."""
    if not settings.paperclip_enabled:
        return _disabled_response()

    from integrations.paperclip.bridge import bridge

    agents = await bridge.get_team()
    return [a.model_dump() for a in agents]


@router.get("/org")
async def org_chart():
    """Get the organizational chart."""
    if not settings.paperclip_enabled:
        return _disabled_response()

    from integrations.paperclip.bridge import bridge

    org = await bridge.get_org_chart()
    return org or {"error": "Could not retrieve org chart"}


@router.post("/agents/{agent_id}/wake")
async def wake_agent(agent_id: str, request: Request):
    """Wake an agent to start working."""
    if not settings.paperclip_enabled:
        return _disabled_response()

    body = await request.json()

    from integrations.paperclip.bridge import bridge

    result = await bridge.client.wake_agent(
        agent_id,
        issue_id=body.get("issue_id"),
        message=body.get("message"),
    )

    if not result:
        return JSONResponse({"error": "Failed to wake agent"}, status_code=502)

    return result


# ── Goals ────────────────────────────────────────────────────────────────────


@router.get("/goals")
async def list_goals():
    """List company goals."""
    if not settings.paperclip_enabled:
        return _disabled_response()

    from integrations.paperclip.bridge import bridge

    goals = await bridge.list_goals()
    return [g.model_dump() for g in goals]


@router.post("/goals")
async def create_goal(request: Request):
    """Set a new company goal (CEO directive)."""
    if not settings.paperclip_enabled:
        return _disabled_response()

    body = await request.json()
    title = body.get("title")
    if not title:
        return JSONResponse({"error": "title is required"}, status_code=400)

    from integrations.paperclip.bridge import bridge

    goal = await bridge.set_goal(title, body.get("description", ""))

    if not goal:
        return JSONResponse({"error": "Failed to create goal"}, status_code=502)

    return goal.model_dump()


# ── Approvals ────────────────────────────────────────────────────────────────


@router.get("/approvals")
async def list_approvals():
    """List pending approvals for CEO review."""
    if not settings.paperclip_enabled:
        return _disabled_response()

    from integrations.paperclip.bridge import bridge

    return await bridge.pending_approvals()


@router.post("/approvals/{approval_id}/approve")
async def approve(approval_id: str, request: Request):
    """Approve an agent's action."""
    if not settings.paperclip_enabled:
        return _disabled_response()

    body = await request.json()

    from integrations.paperclip.bridge import bridge

    ok = await bridge.approve(approval_id, body.get("comment", ""))

    if not ok:
        return JSONResponse({"error": "Failed to approve"}, status_code=502)

    return {"ok": True, "approval_id": approval_id}


@router.post("/approvals/{approval_id}/reject")
async def reject(approval_id: str, request: Request):
    """Reject an agent's action."""
    if not settings.paperclip_enabled:
        return _disabled_response()

    body = await request.json()

    from integrations.paperclip.bridge import bridge

    ok = await bridge.reject(approval_id, body.get("comment", ""))

    if not ok:
        return JSONResponse({"error": "Failed to reject"}, status_code=502)

    return {"ok": True, "approval_id": approval_id}


# ── Runs (monitoring) ────────────────────────────────────────────────────────


@router.get("/runs")
async def list_runs():
    """List active heartbeat runs."""
    if not settings.paperclip_enabled:
        return _disabled_response()

    from integrations.paperclip.bridge import bridge

    return await bridge.active_runs()


@router.post("/runs/{run_id}/cancel")
async def cancel_run(run_id: str):
    """Cancel a running heartbeat execution."""
    if not settings.paperclip_enabled:
        return _disabled_response()

    from integrations.paperclip.bridge import bridge

    ok = await bridge.cancel_run(run_id)

    if not ok:
        return JSONResponse({"error": "Failed to cancel run"}, status_code=502)

    return {"ok": True, "run_id": run_id}
