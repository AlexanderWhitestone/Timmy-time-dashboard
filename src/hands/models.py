"""Hands Models — Pydantic schemas for HAND.toml manifests.

Defines the data structures for autonomous Hand agents:
- HandConfig: Complete hand configuration from HAND.toml
- HandState: Runtime state tracking
- HandExecution: Execution record for audit trail
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field, validator


class HandStatus(str, Enum):
    """Runtime status of a Hand."""
    DISABLED = "disabled"
    IDLE = "idle"
    SCHEDULED = "scheduled"
    RUNNING = "running"
    PAUSED = "paused"
    ERROR = "error"


class HandOutcome(str, Enum):
    """Outcome of a Hand execution."""
    SUCCESS = "success"
    FAILURE = "failure"
    APPROVAL_PENDING = "approval_pending"
    TIMEOUT = "timeout"
    SKIPPED = "skipped"


class TriggerType(str, Enum):
    """Types of execution triggers."""
    SCHEDULE = "schedule"  # Cron schedule
    MANUAL = "manual"      # User triggered
    EVENT = "event"        # Event-driven
    WEBHOOK = "webhook"    # External webhook


# ── HAND.toml Schema Models ───────────────────────────────────────────────

class ToolRequirement(BaseModel):
    """A required tool for the Hand."""
    name: str
    version: Optional[str] = None
    optional: bool = False


class OutputConfig(BaseModel):
    """Output configuration for Hand results."""
    dashboard: bool = True
    channel: Optional[str] = None  # e.g., "telegram", "discord"
    format: str = "markdown"  # markdown, json, html
    file_drop: Optional[str] = None  # Path to write output files


class ApprovalGate(BaseModel):
    """An approval gate for sensitive operations."""
    action: str  # e.g., "post_tweet", "send_payment"
    description: str
    auto_approve_after: Optional[int] = None  # Seconds to auto-approve


class ScheduleConfig(BaseModel):
    """Schedule configuration for the Hand."""
    cron: Optional[str] = None  # Cron expression
    interval: Optional[int] = None  # Seconds between runs
    at: Optional[str] = None  # Specific time (HH:MM)
    timezone: str = "UTC"
    
    @validator('cron')
    def validate_cron(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        # Basic cron validation (5 fields)
        parts = v.split()
        if len(parts) != 5:
            raise ValueError("Cron expression must have 5 fields: minute hour day month weekday")
        return v


class HandConfig(BaseModel):
    """Complete Hand configuration from HAND.toml.
    
    Example HAND.toml:
        [hand]
        name = "oracle"
        schedule = "0 7,19 * * *"
        description = "Bitcoin and on-chain intelligence briefing"
        
        [tools]
        required = ["mempool_fetch", "fee_estimate"]
        
        [approval_gates]
        post_tweet = { action = "post_tweet", description = "Post to Twitter" }
        
        [output]
        dashboard = true
        channel = "telegram"
    """
    
    # Required fields
    name: str = Field(..., description="Unique hand identifier")
    description: str = Field(..., description="What this Hand does")
    
    # Schedule (one of these must be set)
    schedule: Optional[ScheduleConfig] = None
    trigger: Optional[TriggerType] = TriggerType.SCHEDULE
    
    # Optional fields
    enabled: bool = True
    version: str = "1.0.0"
    author: Optional[str] = None
    
    # Tools
    tools_required: list[str] = Field(default_factory=list)
    tools_optional: list[str] = Field(default_factory=list)
    
    # Approval gates
    approval_gates: list[ApprovalGate] = Field(default_factory=list)
    
    # Output configuration
    output: OutputConfig = Field(default_factory=OutputConfig)
    
    # File paths (set at runtime)
    hand_dir: Optional[Path] = Field(None, exclude=True)
    system_prompt_path: Optional[Path] = None
    skill_paths: list[Path] = Field(default_factory=list)
    
    class Config:
        extra = "allow"  # Allow additional fields for extensibility
    
    @property
    def system_md_path(self) -> Optional[Path]:
        """Path to SYSTEM.md file."""
        if self.hand_dir:
            return self.hand_dir / "SYSTEM.md"
        return None
    
    @property
    def skill_md_paths(self) -> list[Path]:
        """Paths to SKILL.md files."""
        if self.hand_dir:
            skill_dir = self.hand_dir / "skills"
            if skill_dir.exists():
                return list(skill_dir.glob("*.md"))
        return []


# ── Runtime State Models ─────────────────────────────────────────────────

@dataclass
class HandState:
    """Runtime state of a Hand."""
    name: str
    status: HandStatus = HandStatus.IDLE
    last_run: Optional[datetime] = None
    next_run: Optional[datetime] = None
    run_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    error_message: Optional[str] = None
    is_paused: bool = False
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status.value,
            "last_run": self.last_run.isoformat() if self.last_run else None,
            "next_run": self.next_run.isoformat() if self.next_run else None,
            "run_count": self.run_count,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "error_message": self.error_message,
            "is_paused": self.is_paused,
        }


@dataclass
class HandExecution:
    """Record of a Hand execution."""
    id: str
    hand_name: str
    trigger: TriggerType
    started_at: datetime
    completed_at: Optional[datetime] = None
    outcome: HandOutcome = HandOutcome.SKIPPED
    output: str = ""
    error: Optional[str] = None
    approval_id: Optional[str] = None
    files_generated: list[str] = field(default_factory=list)
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "hand_name": self.hand_name,
            "trigger": self.trigger.value,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "outcome": self.outcome.value,
            "output": self.output,
            "error": self.error,
            "approval_id": self.approval_id,
            "files_generated": self.files_generated,
        }


# ── Approval Queue Models ────────────────────────────────────────────────

class ApprovalStatus(str, Enum):
    """Status of an approval request."""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    AUTO_APPROVED = "auto_approved"


@dataclass
class ApprovalRequest:
    """A request for user approval."""
    id: str
    hand_name: str
    action: str
    description: str
    context: dict[str, Any] = field(default_factory=dict)
    status: ApprovalStatus = ApprovalStatus.PENDING
    created_at: datetime = field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[str] = None
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "hand_name": self.hand_name,
            "action": self.action,
            "description": self.description,
            "context": self.context,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "resolved_by": self.resolved_by,
        }
