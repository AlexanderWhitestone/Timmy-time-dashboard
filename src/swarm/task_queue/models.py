"""Task Queue data model — SQLite-backed CRUD with human-in-the-loop states.

Table: task_queue in data/swarm.db
"""

import json
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional


DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "swarm.db"


class TaskStatus(str, Enum):
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    VETOED = "vetoed"
    FAILED = "failed"
    BACKLOGGED = "backlogged"


class TaskPriority(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


@dataclass
class TaskStep:
    description: str
    status: str = "pending"  # pending, running, completed, failed
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    output: Optional[str] = None


@dataclass
class QueueTask:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    title: str = ""
    description: str = ""
    task_type: str = "chat_response"  # chat_response, thought, internal, external
    assigned_to: str = "timmy"
    created_by: str = "user"
    status: TaskStatus = TaskStatus.PENDING_APPROVAL
    priority: TaskPriority = TaskPriority.NORMAL
    requires_approval: bool = True
    auto_approve: bool = False
    parent_task_id: Optional[str] = None
    result: Optional[str] = None
    steps: list = field(default_factory=list)
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    updated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    queue_position: Optional[int] = None  # Position in queue when created
    backlog_reason: Optional[str] = None  # Why the task was backlogged


# ── Auto-Approve Rules ──────────────────────────────────────────────────

AUTO_APPROVE_RULES = [
    {"assigned_to": "timmy", "type": "chat_response"},
    {"assigned_to": "timmy", "type": "thought"},
    {"assigned_to": "timmy", "type": "internal"},
    {"assigned_to": "forge", "type": "run_tests"},
    {"priority": "urgent", "created_by": "timmy"},
    {"type": "bug_report", "created_by": "system"},
]


def should_auto_approve(task: QueueTask) -> bool:
    """Check if a task matches any auto-approve rule."""
    if not task.auto_approve:
        return False
    for rule in AUTO_APPROVE_RULES:
        match = True
        for key, val in rule.items():
            if key == "type":
                if task.task_type != val:
                    match = False
                    break
                continue
            task_val = getattr(task, key, None)
            if isinstance(task_val, Enum):
                task_val = task_val.value
            if task_val != val:
                match = False
                break
        if match:
            return True
    return False


# ── Database ─────────────────────────────────────────────────────────────


def _get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS task_queue (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            description TEXT DEFAULT '',
            task_type TEXT DEFAULT 'chat_response',
            assigned_to TEXT DEFAULT 'timmy',
            created_by TEXT DEFAULT 'user',
            status TEXT DEFAULT 'pending_approval',
            priority TEXT DEFAULT 'normal',
            requires_approval INTEGER DEFAULT 1,
            auto_approve INTEGER DEFAULT 0,
            parent_task_id TEXT,
            result TEXT,
            steps TEXT DEFAULT '[]',
            created_at TEXT NOT NULL,
            started_at TEXT,
            completed_at TEXT,
            updated_at TEXT NOT NULL,
            queue_position INTEGER,
            backlog_reason TEXT
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tq_status ON task_queue(status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tq_priority ON task_queue(priority)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tq_created ON task_queue(created_at)")

    # Migrate existing tables - add new columns if they don't exist
    try:
        conn.execute(
            "ALTER TABLE task_queue ADD COLUMN task_type TEXT DEFAULT 'chat_response'"
        )
    except sqlite3.OperationalError:
        pass  # Column already exists
    try:
        conn.execute("ALTER TABLE task_queue ADD COLUMN queue_position INTEGER")
    except sqlite3.OperationalError:
        pass  # Column already exists
    try:
        conn.execute("ALTER TABLE task_queue ADD COLUMN backlog_reason TEXT")
    except sqlite3.OperationalError:
        pass  # Column already exists

    conn.commit()
    return conn


def _row_to_task(row: sqlite3.Row) -> QueueTask:
    d = dict(row)
    steps_raw = d.pop("steps", "[]")
    try:
        steps = json.loads(steps_raw) if steps_raw else []
    except (json.JSONDecodeError, TypeError):
        steps = []
    return QueueTask(
        id=d["id"],
        title=d["title"],
        description=d.get("description", ""),
        task_type=d.get("task_type", "chat_response"),
        assigned_to=d.get("assigned_to", "timmy"),
        created_by=d.get("created_by", "user"),
        status=TaskStatus(d["status"]),
        priority=TaskPriority(d.get("priority", "normal")),
        requires_approval=bool(d.get("requires_approval", 1)),
        auto_approve=bool(d.get("auto_approve", 0)),
        parent_task_id=d.get("parent_task_id"),
        result=d.get("result"),
        steps=steps,
        created_at=d["created_at"],
        started_at=d.get("started_at"),
        completed_at=d.get("completed_at"),
        updated_at=d["updated_at"],
        queue_position=d.get("queue_position"),
        backlog_reason=d.get("backlog_reason"),
    )


# ── CRUD ─────────────────────────────────────────────────────────────────


def create_task(
    title: str,
    description: str = "",
    assigned_to: str = "timmy",
    created_by: str = "user",
    priority: str = "normal",
    requires_approval: bool = True,
    auto_approve: bool = False,
    parent_task_id: Optional[str] = None,
    steps: Optional[list] = None,
    task_type: str = "chat_response",
) -> QueueTask:
    """Create a new task in the queue."""
    now = datetime.now(timezone.utc).isoformat()

    # Calculate queue position - count tasks ahead in queue (pending or approved)
    queue_position = get_queue_position_ahead(assigned_to)

    task = QueueTask(
        title=title,
        description=description,
        task_type=task_type,
        assigned_to=assigned_to,
        created_by=created_by,
        status=TaskStatus.PENDING_APPROVAL,
        priority=TaskPriority(priority),
        requires_approval=requires_approval,
        auto_approve=auto_approve,
        parent_task_id=parent_task_id,
        steps=steps or [],
        created_at=now,
        updated_at=now,
        queue_position=queue_position,
    )

    # Check auto-approve
    if should_auto_approve(task):
        task.status = TaskStatus.APPROVED
        task.requires_approval = False

    conn = _get_conn()
    conn.execute(
        """INSERT INTO task_queue
           (id, title, description, task_type, assigned_to, created_by, status, priority,
            requires_approval, auto_approve, parent_task_id, result, steps,
            created_at, started_at, completed_at, updated_at, queue_position,
            backlog_reason)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            task.id,
            task.title,
            task.description,
            task.task_type,
            task.assigned_to,
            task.created_by,
            task.status.value,
            task.priority.value,
            int(task.requires_approval),
            int(task.auto_approve),
            task.parent_task_id,
            task.result,
            json.dumps(task.steps),
            task.created_at,
            task.started_at,
            task.completed_at,
            task.updated_at,
            task.queue_position,
            task.backlog_reason,
        ),
    )
    conn.commit()
    conn.close()
    return task


def get_task(task_id: str) -> Optional[QueueTask]:
    conn = _get_conn()
    row = conn.execute("SELECT * FROM task_queue WHERE id = ?", (task_id,)).fetchone()
    conn.close()
    return _row_to_task(row) if row else None


def list_tasks(
    status: Optional[TaskStatus] = None,
    priority: Optional[TaskPriority] = None,
    assigned_to: Optional[str] = None,
    created_by: Optional[str] = None,
    limit: int = 100,
) -> list[QueueTask]:
    clauses, params = [], []
    if status:
        clauses.append("status = ?")
        params.append(status.value)
    if priority:
        clauses.append("priority = ?")
        params.append(priority.value)
    if assigned_to:
        clauses.append("assigned_to = ?")
        params.append(assigned_to)
    if created_by:
        clauses.append("created_by = ?")
        params.append(created_by)

    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    params.append(limit)

    conn = _get_conn()
    rows = conn.execute(
        f"SELECT * FROM task_queue{where} ORDER BY created_at DESC LIMIT ?",
        params,
    ).fetchall()
    conn.close()
    return [_row_to_task(r) for r in rows]


def update_task_status(
    task_id: str,
    new_status: TaskStatus,
    result: Optional[str] = None,
    backlog_reason: Optional[str] = None,
) -> Optional[QueueTask]:
    now = datetime.now(timezone.utc).isoformat()
    conn = _get_conn()

    updates = ["status = ?", "updated_at = ?"]
    params = [new_status.value, now]

    if new_status == TaskStatus.RUNNING:
        updates.append("started_at = ?")
        params.append(now)
    elif new_status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.VETOED):
        updates.append("completed_at = ?")
        params.append(now)

    if result is not None:
        updates.append("result = ?")
        params.append(result)

    if backlog_reason is not None:
        updates.append("backlog_reason = ?")
        params.append(backlog_reason)

    params.append(task_id)
    conn.execute(
        f"UPDATE task_queue SET {', '.join(updates)} WHERE id = ?",
        params,
    )
    conn.commit()

    row = conn.execute("SELECT * FROM task_queue WHERE id = ?", (task_id,)).fetchone()
    conn.close()
    return _row_to_task(row) if row else None


def update_task(
    task_id: str,
    title: Optional[str] = None,
    description: Optional[str] = None,
    assigned_to: Optional[str] = None,
    priority: Optional[str] = None,
) -> Optional[QueueTask]:
    """Update task fields (for MODIFY action)."""
    now = datetime.now(timezone.utc).isoformat()
    conn = _get_conn()

    updates = ["updated_at = ?"]
    params = [now]

    if title is not None:
        updates.append("title = ?")
        params.append(title)
    if description is not None:
        updates.append("description = ?")
        params.append(description)
    if assigned_to is not None:
        updates.append("assigned_to = ?")
        params.append(assigned_to)
    if priority is not None:
        updates.append("priority = ?")
        params.append(priority)

    params.append(task_id)
    conn.execute(
        f"UPDATE task_queue SET {', '.join(updates)} WHERE id = ?",
        params,
    )
    conn.commit()

    row = conn.execute("SELECT * FROM task_queue WHERE id = ?", (task_id,)).fetchone()
    conn.close()
    return _row_to_task(row) if row else None


def update_task_steps(task_id: str, steps: list) -> bool:
    """Update the steps array for a running task."""
    now = datetime.now(timezone.utc).isoformat()
    conn = _get_conn()
    cursor = conn.execute(
        "UPDATE task_queue SET steps = ?, updated_at = ? WHERE id = ?",
        (json.dumps(steps), now, task_id),
    )
    conn.commit()
    ok = cursor.rowcount > 0
    conn.close()
    return ok


def get_counts_by_status() -> dict[str, int]:
    conn = _get_conn()
    rows = conn.execute(
        "SELECT status, COUNT(*) as cnt FROM task_queue GROUP BY status"
    ).fetchall()
    conn.close()
    return {r["status"]: r["cnt"] for r in rows}


def get_pending_count() -> int:
    conn = _get_conn()
    row = conn.execute(
        "SELECT COUNT(*) as cnt FROM task_queue WHERE status = 'pending_approval'"
    ).fetchone()
    conn.close()
    return row["cnt"] if row else 0


def get_queue_position_ahead(assigned_to: str) -> int:
    """Get count of tasks ahead of new tasks for a given assignee.

    Counts tasks that are pending_approval or approved (waiting to be processed).
    """
    conn = _get_conn()
    row = conn.execute(
        """SELECT COUNT(*) as cnt FROM task_queue 
           WHERE assigned_to = ? AND status IN ('pending_approval', 'approved', 'running')
           AND created_at < datetime('now')""",
        (assigned_to,),
    ).fetchone()
    conn.close()
    return row["cnt"] if row else 0


def get_queue_status_for_task(task_id: str) -> dict:
    """Get queue position info for a specific task."""
    task = get_task(task_id)
    if not task:
        return {"error": "Task not found"}

    conn = _get_conn()
    # Count tasks ahead of this one (created earlier, not completed)
    ahead = conn.execute(
        """SELECT COUNT(*) as cnt FROM task_queue 
           WHERE assigned_to = ? AND status NOT IN ('completed', 'failed', 'vetoed')
           AND created_at < ?""",
        (task.assigned_to, task.created_at),
    ).fetchone()
    total = conn.execute(
        """SELECT COUNT(*) as cnt FROM task_queue 
           WHERE assigned_to = ? AND status NOT IN ('completed', 'failed', 'vetoed')""",
        (task.assigned_to,),
    ).fetchone()
    conn.close()

    position = ahead["cnt"] + 1 if ahead else 1
    total_count = total["cnt"] if total else 1

    return {
        "task_id": task_id,
        "position": position,
        "total": total_count,
        "percent_ahead": int((ahead["cnt"] / total_count * 100))
        if total_count > 0
        else 0,
    }


def get_current_task_for_agent(assigned_to: str) -> Optional[QueueTask]:
    """Get the currently running task for an agent."""
    conn = _get_conn()
    row = conn.execute(
        """SELECT * FROM task_queue 
           WHERE assigned_to = ? AND status = 'running'
           ORDER BY started_at DESC LIMIT 1""",
        (assigned_to,),
    ).fetchone()
    conn.close()
    return _row_to_task(row) if row else None


def get_next_pending_task(assigned_to: str) -> Optional[QueueTask]:
    """Get the next pending/approved task for an agent to work on."""
    conn = _get_conn()
    row = conn.execute(
        """SELECT * FROM task_queue 
           WHERE assigned_to = ? AND status IN ('approved', 'pending_approval')
           ORDER BY 
               CASE priority
                   WHEN 'urgent' THEN 1
                   WHEN 'high' THEN 2
                   WHEN 'normal' THEN 3
                   WHEN 'low' THEN 4
               END,
               created_at ASC
           LIMIT 1""",
        (assigned_to,),
    ).fetchone()
    conn.close()
    return _row_to_task(row) if row else None


def get_task_summary_for_briefing() -> dict:
    """Get task stats for the morning briefing."""
    counts = get_counts_by_status()
    conn = _get_conn()
    # Failed tasks
    failed = conn.execute(
        "SELECT title, result FROM task_queue WHERE status = 'failed' ORDER BY updated_at DESC LIMIT 5"
    ).fetchall()
    # Backlogged tasks
    backlogged = conn.execute(
        "SELECT title, backlog_reason FROM task_queue WHERE status = 'backlogged' ORDER BY updated_at DESC LIMIT 5"
    ).fetchall()
    conn.close()

    return {
        "pending_approval": counts.get("pending_approval", 0),
        "running": counts.get("running", 0),
        "completed": counts.get("completed", 0),
        "failed": counts.get("failed", 0),
        "vetoed": counts.get("vetoed", 0),
        "backlogged": counts.get("backlogged", 0),
        "total": sum(counts.values()),
        "recent_failures": [
            {"title": r["title"], "result": r["result"]} for r in failed
        ],
        "recent_backlogged": [
            {"title": r["title"], "reason": r["backlog_reason"]} for r in backlogged
        ],
    }


def list_backlogged_tasks(
    assigned_to: Optional[str] = None, limit: int = 50
) -> list[QueueTask]:
    """List all backlogged tasks, optionally filtered by assignee."""
    conn = _get_conn()
    if assigned_to:
        rows = conn.execute(
            """SELECT * FROM task_queue WHERE status = 'backlogged' AND assigned_to = ?
               ORDER BY priority, created_at ASC LIMIT ?""",
            (assigned_to, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT * FROM task_queue WHERE status = 'backlogged'
               ORDER BY priority, created_at ASC LIMIT ?""",
            (limit,),
        ).fetchall()
    conn.close()
    return [_row_to_task(r) for r in rows]


def get_all_actionable_tasks(assigned_to: str) -> list[QueueTask]:
    """Get all tasks that should be processed on startup — approved or auto-approved pending.

    Returns tasks ordered by priority then creation time (urgent first, oldest first).
    """
    conn = _get_conn()
    rows = conn.execute(
        """SELECT * FROM task_queue
           WHERE assigned_to = ? AND status IN ('approved', 'pending_approval')
           ORDER BY
               CASE priority
                   WHEN 'urgent' THEN 1
                   WHEN 'high' THEN 2
                   WHEN 'normal' THEN 3
                   WHEN 'low' THEN 4
               END,
               created_at ASC""",
        (assigned_to,),
    ).fetchall()
    conn.close()
    return [_row_to_task(r) for r in rows]
