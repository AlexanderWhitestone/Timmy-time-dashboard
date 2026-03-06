"""Pydantic models for Paperclip AI API objects."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ── Inbound: Paperclip → Timmy ──────────────────────────────────────────────


class PaperclipIssue(BaseModel):
    """A ticket/issue in Paperclip's task system."""

    id: str
    title: str
    description: str = ""
    status: str = "open"
    priority: Optional[str] = None
    assignee_id: Optional[str] = None
    project_id: Optional[str] = None
    labels: List[str] = Field(default_factory=list)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class PaperclipComment(BaseModel):
    """A comment on a Paperclip issue."""

    id: str
    issue_id: str
    content: str
    author: Optional[str] = None
    created_at: Optional[str] = None


class PaperclipAgent(BaseModel):
    """An agent in the Paperclip org chart."""

    id: str
    name: str
    role: str = ""
    status: str = "active"
    adapter_type: Optional[str] = None
    company_id: Optional[str] = None


class PaperclipGoal(BaseModel):
    """A company goal in Paperclip."""

    id: str
    title: str
    description: str = ""
    status: str = "active"
    company_id: Optional[str] = None


class HeartbeatRun(BaseModel):
    """A heartbeat execution run."""

    id: str
    agent_id: str
    status: str
    issue_id: Optional[str] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None


# ── Outbound: Timmy → Paperclip ─────────────────────────────────────────────


class CreateIssueRequest(BaseModel):
    """Request to create a new issue in Paperclip."""

    title: str
    description: str = ""
    priority: Optional[str] = None
    assignee_id: Optional[str] = None
    project_id: Optional[str] = None
    labels: List[str] = Field(default_factory=list)


class UpdateIssueRequest(BaseModel):
    """Request to update an existing issue."""

    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    assignee_id: Optional[str] = None


class AddCommentRequest(BaseModel):
    """Request to add a comment to an issue."""

    content: str


class WakeAgentRequest(BaseModel):
    """Request to wake an agent via heartbeat."""

    issue_id: Optional[str] = None
    message: Optional[str] = None


# ── API route models ─────────────────────────────────────────────────────────


class PaperclipStatusResponse(BaseModel):
    """Response for GET /api/paperclip/status."""

    enabled: bool
    connected: bool = False
    paperclip_url: str = ""
    company_id: str = ""
    agent_count: int = 0
    issue_count: int = 0
    error: Optional[str] = None
