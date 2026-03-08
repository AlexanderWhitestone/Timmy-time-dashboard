"""Bridge module: exposes create_task() for programmatic task creation.

Used by infrastructure.error_capture to auto-create bug report tasks
in the same SQLite database the dashboard routes use.
"""

import logging
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

DB_PATH = Path("data/tasks.db")


@dataclass
class TaskRecord:
    """Lightweight return value from create_task()."""

    id: str
    title: str
    status: str


def _ensure_db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            description TEXT DEFAULT '',
            status TEXT DEFAULT 'pending_approval',
            priority TEXT DEFAULT 'normal',
            assigned_to TEXT DEFAULT '',
            created_by TEXT DEFAULT 'operator',
            result TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now')),
            completed_at TEXT
        )
    """)
    conn.commit()
    return conn


def create_task(
    title: str,
    description: str = "",
    assigned_to: str = "default",
    created_by: str = "system",
    priority: str = "normal",
    requires_approval: bool = True,
    auto_approve: bool = False,
    task_type: str = "",
) -> TaskRecord:
    """Insert a task into the SQLite task queue and return a TaskRecord.

    Args:
        title: Task title (e.g. "[BUG] ConnectionError: ...")
        description: Markdown body with error details / stack trace
        assigned_to: Agent or queue to assign to
        created_by: Who created the task ("system", "operator", etc.)
        priority: "low" | "normal" | "high" | "urgent"
        requires_approval: If False and auto_approve, skip pending_approval
        auto_approve: If True, set status to "approved" immediately
        task_type: Optional tag (e.g. "bug_report")

    Returns:
        TaskRecord with the new task's id, title, and status.
    """
    valid_priorities = {"low", "normal", "high", "urgent"}
    if priority not in valid_priorities:
        priority = "normal"

    status = "approved" if (auto_approve and not requires_approval) else "pending_approval"
    task_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()

    # Store task_type in description header if provided
    if task_type:
        description = f"**Type:** {task_type}\n{description}"

    db = _ensure_db()
    try:
        db.execute(
            "INSERT INTO tasks (id, title, description, status, priority, assigned_to, created_by, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (task_id, title, description, status, priority, assigned_to, created_by, now),
        )
        db.commit()
    finally:
        db.close()

    logger.info("Task created: %s — %s [%s]", task_id[:8], title[:60], status)
    return TaskRecord(id=task_id, title=title, status=status)


def get_task_summary_for_briefing() -> dict:
    """Return a summary of task counts by status for the morning briefing."""
    db = _ensure_db()
    try:
        rows = db.execute(
            "SELECT status, COUNT(*) as cnt FROM tasks GROUP BY status"
        ).fetchall()
    finally:
        db.close()

    summary = {r["status"]: r["cnt"] for r in rows}
    summary["total"] = sum(summary.values())
    return summary
