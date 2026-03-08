"""Swarm event log — records system events to SQLite.

Provides EventType enum, EventLogEntry dataclass, and log_event() function
used by error_capture, thinking engine, and the event broadcaster.
"""

import logging
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

DB_PATH = Path("data/events.db")


class EventType(Enum):
    """All recognised event types in the system."""

    # Task lifecycle
    TASK_CREATED = "task.created"
    TASK_BIDDING = "task.bidding"
    TASK_ASSIGNED = "task.assigned"
    TASK_STARTED = "task.started"
    TASK_COMPLETED = "task.completed"
    TASK_FAILED = "task.failed"

    # Agent lifecycle
    AGENT_JOINED = "agent.joined"
    AGENT_LEFT = "agent.left"
    AGENT_STATUS_CHANGED = "agent.status_changed"

    # Bids
    BID_SUBMITTED = "bid.submitted"
    AUCTION_CLOSED = "auction.closed"

    # Tools
    TOOL_CALLED = "tool.called"
    TOOL_COMPLETED = "tool.completed"
    TOOL_FAILED = "tool.failed"

    # System
    SYSTEM_ERROR = "system.error"
    SYSTEM_WARNING = "system.warning"
    SYSTEM_INFO = "system.info"

    # Error capture
    ERROR_CAPTURED = "error.captured"
    BUG_REPORT_CREATED = "bug_report.created"

    # Thinking
    TIMMY_THOUGHT = "timmy.thought"


@dataclass
class EventLogEntry:
    """Single event in the log, used by the broadcaster for display."""

    id: str
    event_type: EventType
    source: str
    timestamp: str
    data: dict = field(default_factory=dict)
    task_id: str = ""
    agent_id: str = ""


def _ensure_db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id TEXT PRIMARY KEY,
            event_type TEXT NOT NULL,
            source TEXT DEFAULT '',
            task_id TEXT DEFAULT '',
            agent_id TEXT DEFAULT '',
            data TEXT DEFAULT '{}',
            timestamp TEXT NOT NULL
        )
    """)
    conn.commit()
    return conn


def log_event(
    event_type: EventType,
    source: str = "",
    data: Optional[dict] = None,
    task_id: str = "",
    agent_id: str = "",
) -> EventLogEntry:
    """Record an event and return the entry.

    Also broadcasts to WebSocket clients via the event broadcaster
    (lazy import to avoid circular deps).
    """
    import json

    entry = EventLogEntry(
        id=str(uuid.uuid4()),
        event_type=event_type,
        source=source,
        timestamp=datetime.now(timezone.utc).isoformat(),
        data=data or {},
        task_id=task_id,
        agent_id=agent_id,
    )

    # Persist to SQLite
    try:
        db = _ensure_db()
        try:
            db.execute(
                "INSERT INTO events (id, event_type, source, task_id, agent_id, data, timestamp) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (entry.id, event_type.value, source, task_id, agent_id,
                 json.dumps(data or {}), entry.timestamp),
            )
            db.commit()
        finally:
            db.close()
    except Exception as exc:
        logger.debug("Failed to persist event: %s", exc)

    # Broadcast to WebSocket clients (non-blocking)
    try:
        from infrastructure.events.broadcaster import event_broadcaster
        event_broadcaster.broadcast_sync(entry)
    except Exception:
        pass

    return entry


def get_task_events(task_id: str, limit: int = 50) -> list[EventLogEntry]:
    """Retrieve events for a specific task."""
    import json

    db = _ensure_db()
    try:
        rows = db.execute(
            "SELECT * FROM events WHERE task_id=? ORDER BY timestamp DESC LIMIT ?",
            (task_id, limit),
        ).fetchall()
    finally:
        db.close()

    entries = []
    for r in rows:
        try:
            et = EventType(r["event_type"])
        except ValueError:
            et = EventType.SYSTEM_INFO
        entries.append(EventLogEntry(
            id=r["id"],
            event_type=et,
            source=r["source"],
            timestamp=r["timestamp"],
            data=json.loads(r["data"]) if r["data"] else {},
            task_id=r["task_id"],
            agent_id=r["agent_id"],
        ))
    return entries
