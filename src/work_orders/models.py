"""Database models for Work Order system."""

import json
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional

DB_PATH = Path("data/swarm.db")


class WorkOrderStatus(str, Enum):
    SUBMITTED = "submitted"
    TRIAGED = "triaged"
    APPROVED = "approved"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    REJECTED = "rejected"


class WorkOrderPriority(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class WorkOrderCategory(str, Enum):
    BUG = "bug"
    FEATURE = "feature"
    IMPROVEMENT = "improvement"
    OPTIMIZATION = "optimization"
    SUGGESTION = "suggestion"


@dataclass
class WorkOrder:
    """A work order / suggestion submitted by a user or agent."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    title: str = ""
    description: str = ""
    priority: WorkOrderPriority = WorkOrderPriority.MEDIUM
    category: WorkOrderCategory = WorkOrderCategory.SUGGESTION
    status: WorkOrderStatus = WorkOrderStatus.SUBMITTED
    submitter: str = "unknown"
    submitter_type: str = "user"  # user | agent | system
    estimated_effort: Optional[str] = None  # small | medium | large
    related_files: list[str] = field(default_factory=list)
    execution_mode: Optional[str] = None  # auto | manual
    swarm_task_id: Optional[str] = None
    result: Optional[str] = None
    rejection_reason: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    triaged_at: Optional[str] = None
    approved_at: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


def _get_conn() -> sqlite3.Connection:
    """Get database connection with schema initialized."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS work_orders (
            id              TEXT PRIMARY KEY,
            title           TEXT NOT NULL,
            description     TEXT NOT NULL DEFAULT '',
            priority        TEXT NOT NULL DEFAULT 'medium',
            category        TEXT NOT NULL DEFAULT 'suggestion',
            status          TEXT NOT NULL DEFAULT 'submitted',
            submitter       TEXT NOT NULL DEFAULT 'unknown',
            submitter_type  TEXT NOT NULL DEFAULT 'user',
            estimated_effort TEXT,
            related_files   TEXT,
            execution_mode  TEXT,
            swarm_task_id   TEXT,
            result          TEXT,
            rejection_reason TEXT,
            created_at      TEXT NOT NULL,
            triaged_at      TEXT,
            approved_at     TEXT,
            started_at      TEXT,
            completed_at    TEXT,
            updated_at      TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_wo_status ON work_orders(status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_wo_priority ON work_orders(priority)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_wo_submitter ON work_orders(submitter)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_wo_created ON work_orders(created_at)")
    conn.commit()
    return conn


def _row_to_work_order(row: sqlite3.Row) -> WorkOrder:
    """Convert a database row to a WorkOrder."""
    return WorkOrder(
        id=row["id"],
        title=row["title"],
        description=row["description"],
        priority=WorkOrderPriority(row["priority"]),
        category=WorkOrderCategory(row["category"]),
        status=WorkOrderStatus(row["status"]),
        submitter=row["submitter"],
        submitter_type=row["submitter_type"],
        estimated_effort=row["estimated_effort"],
        related_files=json.loads(row["related_files"]) if row["related_files"] else [],
        execution_mode=row["execution_mode"],
        swarm_task_id=row["swarm_task_id"],
        result=row["result"],
        rejection_reason=row["rejection_reason"],
        created_at=row["created_at"],
        triaged_at=row["triaged_at"],
        approved_at=row["approved_at"],
        started_at=row["started_at"],
        completed_at=row["completed_at"],
        updated_at=row["updated_at"],
    )


def create_work_order(
    title: str,
    description: str = "",
    priority: str = "medium",
    category: str = "suggestion",
    submitter: str = "unknown",
    submitter_type: str = "user",
    estimated_effort: Optional[str] = None,
    related_files: Optional[list[str]] = None,
) -> WorkOrder:
    """Create a new work order."""
    wo = WorkOrder(
        title=title,
        description=description,
        priority=WorkOrderPriority(priority),
        category=WorkOrderCategory(category),
        submitter=submitter,
        submitter_type=submitter_type,
        estimated_effort=estimated_effort,
        related_files=related_files or [],
    )

    conn = _get_conn()
    conn.execute(
        """
        INSERT INTO work_orders (
            id, title, description, priority, category, status,
            submitter, submitter_type, estimated_effort, related_files,
            created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            wo.id, wo.title, wo.description,
            wo.priority.value, wo.category.value, wo.status.value,
            wo.submitter, wo.submitter_type, wo.estimated_effort,
            json.dumps(wo.related_files) if wo.related_files else None,
            wo.created_at, wo.updated_at,
        ),
    )
    conn.commit()
    conn.close()
    return wo


def get_work_order(wo_id: str) -> Optional[WorkOrder]:
    """Get a work order by ID."""
    conn = _get_conn()
    row = conn.execute(
        "SELECT * FROM work_orders WHERE id = ?", (wo_id,)
    ).fetchone()
    conn.close()
    if not row:
        return None
    return _row_to_work_order(row)


def list_work_orders(
    status: Optional[WorkOrderStatus] = None,
    priority: Optional[WorkOrderPriority] = None,
    category: Optional[WorkOrderCategory] = None,
    submitter: Optional[str] = None,
    limit: int = 100,
) -> list[WorkOrder]:
    """List work orders with optional filters."""
    conn = _get_conn()
    conditions = []
    params: list = []

    if status:
        conditions.append("status = ?")
        params.append(status.value)
    if priority:
        conditions.append("priority = ?")
        params.append(priority.value)
    if category:
        conditions.append("category = ?")
        params.append(category.value)
    if submitter:
        conditions.append("submitter = ?")
        params.append(submitter)

    where = "WHERE " + " AND ".join(conditions) if conditions else ""
    rows = conn.execute(
        f"SELECT * FROM work_orders {where} ORDER BY created_at DESC LIMIT ?",
        params + [limit],
    ).fetchall()
    conn.close()
    return [_row_to_work_order(r) for r in rows]


def update_work_order_status(
    wo_id: str,
    new_status: WorkOrderStatus,
    **kwargs,
) -> Optional[WorkOrder]:
    """Update a work order's status and optional fields."""
    now = datetime.now(timezone.utc).isoformat()
    sets = ["status = ?", "updated_at = ?"]
    params: list = [new_status.value, now]

    # Auto-set timestamp fields based on status transition
    timestamp_map = {
        WorkOrderStatus.TRIAGED: "triaged_at",
        WorkOrderStatus.APPROVED: "approved_at",
        WorkOrderStatus.IN_PROGRESS: "started_at",
        WorkOrderStatus.COMPLETED: "completed_at",
        WorkOrderStatus.REJECTED: "completed_at",
    }
    ts_field = timestamp_map.get(new_status)
    if ts_field:
        sets.append(f"{ts_field} = ?")
        params.append(now)

    # Apply additional keyword fields
    allowed_fields = {
        "execution_mode", "swarm_task_id", "result",
        "rejection_reason", "estimated_effort",
    }
    for key, val in kwargs.items():
        if key in allowed_fields:
            sets.append(f"{key} = ?")
            params.append(val)

    params.append(wo_id)
    conn = _get_conn()
    cursor = conn.execute(
        f"UPDATE work_orders SET {', '.join(sets)} WHERE id = ?",
        params,
    )
    conn.commit()
    updated = cursor.rowcount > 0
    conn.close()

    if not updated:
        return None
    return get_work_order(wo_id)


def get_pending_count() -> int:
    """Get count of submitted/triaged work orders awaiting review."""
    conn = _get_conn()
    row = conn.execute(
        "SELECT COUNT(*) as count FROM work_orders WHERE status IN (?, ?)",
        (WorkOrderStatus.SUBMITTED.value, WorkOrderStatus.TRIAGED.value),
    ).fetchone()
    conn.close()
    return row["count"]


def get_counts_by_status() -> dict[str, int]:
    """Get work order counts grouped by status."""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT status, COUNT(*) as count FROM work_orders GROUP BY status"
    ).fetchall()
    conn.close()
    return {r["status"]: r["count"] for r in rows}
