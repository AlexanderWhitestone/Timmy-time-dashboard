"""Event logging for swarm system.

All agent actions, task lifecycle events, and system events are logged
to SQLite for audit, debugging, and analytics.
"""

import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional

DB_PATH = Path("data/swarm.db")


class EventType(str, Enum):
    """Types of events logged."""
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
    
    # Bidding
    BID_SUBMITTED = "bid.submitted"
    AUCTION_CLOSED = "auction.closed"
    
    # Tool execution
    TOOL_CALLED = "tool.called"
    TOOL_COMPLETED = "tool.completed"
    TOOL_FAILED = "tool.failed"
    
    # Thinking
    TIMMY_THOUGHT = "timmy.thought"

    # System
    SYSTEM_ERROR = "system.error"
    SYSTEM_WARNING = "system.warning"
    SYSTEM_INFO = "system.info"

    # Error feedback loop
    ERROR_CAPTURED = "error.captured"
    BUG_REPORT_CREATED = "bug_report.created"


@dataclass
class EventLogEntry:
    """A logged event."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    event_type: EventType = EventType.SYSTEM_INFO
    source: str = ""  # Agent or component that emitted the event
    task_id: Optional[str] = None
    agent_id: Optional[str] = None
    data: Optional[str] = None  # JSON string of additional data
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


def _get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS event_log (
            id TEXT PRIMARY KEY,
            event_type TEXT NOT NULL,
            source TEXT NOT NULL,
            task_id TEXT,
            agent_id TEXT,
            data TEXT,
            timestamp TEXT NOT NULL
        )
        """
    )
    # Create indexes for common queries
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_event_log_task ON event_log(task_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_event_log_agent ON event_log(agent_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_event_log_type ON event_log(event_type)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_event_log_time ON event_log(timestamp)"
    )
    conn.commit()
    return conn


def log_event(
    event_type: EventType,
    source: str,
    task_id: Optional[str] = None,
    agent_id: Optional[str] = None,
    data: Optional[dict] = None,
) -> EventLogEntry:
    """Log an event to the database.
    
    Args:
        event_type: Type of event
        source: Component or agent that emitted the event
        task_id: Optional associated task ID
        agent_id: Optional associated agent ID
        data: Optional dictionary of additional data (will be JSON serialized)
    
    Returns:
        The created EventLogEntry
    """
    import json
    
    entry = EventLogEntry(
        event_type=event_type,
        source=source,
        task_id=task_id,
        agent_id=agent_id,
        data=json.dumps(data) if data else None,
    )
    
    conn = _get_conn()
    conn.execute(
        """
        INSERT INTO event_log (id, event_type, source, task_id, agent_id, data, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            entry.id,
            entry.event_type.value,
            entry.source,
            entry.task_id,
            entry.agent_id,
            entry.data,
            entry.timestamp,
        ),
    )
    conn.commit()
    conn.close()
    
    # Broadcast to WebSocket clients for real-time activity feed
    try:
        from infrastructure.events.broadcaster import event_broadcaster
        event_broadcaster.broadcast_sync(entry)
    except Exception:
        # Don't fail if broadcaster unavailable
        pass
    
    return entry


def get_event(event_id: str) -> Optional[EventLogEntry]:
    """Get a single event by ID."""
    conn = _get_conn()
    row = conn.execute(
        "SELECT * FROM event_log WHERE id = ?", (event_id,)
    ).fetchone()
    conn.close()
    
    if row is None:
        return None
    
    return EventLogEntry(
        id=row["id"],
        event_type=EventType(row["event_type"]),
        source=row["source"],
        task_id=row["task_id"],
        agent_id=row["agent_id"],
        data=row["data"],
        timestamp=row["timestamp"],
    )


def list_events(
    event_type: Optional[EventType] = None,
    task_id: Optional[str] = None,
    agent_id: Optional[str] = None,
    source: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> list[EventLogEntry]:
    """List events with optional filtering.
    
    Args:
        event_type: Filter by event type
        task_id: Filter by associated task
        agent_id: Filter by associated agent
        source: Filter by source component
        limit: Maximum number of events to return
        offset: Number of events to skip (for pagination)
    
    Returns:
        List of EventLogEntry objects, newest first
    """
    conn = _get_conn()
    
    conditions = []
    params = []
    
    if event_type:
        conditions.append("event_type = ?")
        params.append(event_type.value)
    if task_id:
        conditions.append("task_id = ?")
        params.append(task_id)
    if agent_id:
        conditions.append("agent_id = ?")
        params.append(agent_id)
    if source:
        conditions.append("source = ?")
        params.append(source)
    
    where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
    
    query = f"""
        SELECT * FROM event_log
        {where_clause}
        ORDER BY timestamp DESC
        LIMIT ? OFFSET ?
    """
    params.extend([limit, offset])
    
    rows = conn.execute(query, params).fetchall()
    conn.close()
    
    return [
        EventLogEntry(
            id=r["id"],
            event_type=EventType(r["event_type"]),
            source=r["source"],
            task_id=r["task_id"],
            agent_id=r["agent_id"],
            data=r["data"],
            timestamp=r["timestamp"],
        )
        for r in rows
    ]


def get_task_events(task_id: str) -> list[EventLogEntry]:
    """Get all events for a specific task."""
    return list_events(task_id=task_id, limit=1000)


def get_agent_events(agent_id: str) -> list[EventLogEntry]:
    """Get all events for a specific agent."""
    return list_events(agent_id=agent_id, limit=1000)


def get_recent_events(minutes: int = 60) -> list[EventLogEntry]:
    """Get events from the last N minutes."""
    conn = _get_conn()
    
    from datetime import timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()
    
    rows = conn.execute(
        """
        SELECT * FROM event_log
        WHERE timestamp > ?
        ORDER BY timestamp DESC
        """,
        (cutoff,),
    ).fetchall()
    conn.close()
    
    return [
        EventLogEntry(
            id=r["id"],
            event_type=EventType(r["event_type"]),
            source=r["source"],
            task_id=r["task_id"],
            agent_id=r["agent_id"],
            data=r["data"],
            timestamp=r["timestamp"],
        )
        for r in rows
    ]


def get_event_summary(minutes: int = 60) -> dict:
    """Get a summary of recent events by type.
    
    Returns:
        Dict mapping event types to counts
    """
    conn = _get_conn()
    
    from datetime import timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()
    
    rows = conn.execute(
        """
        SELECT event_type, COUNT(*) as count
        FROM event_log
        WHERE timestamp > ?
        GROUP BY event_type
        ORDER BY count DESC
        """,
        (cutoff,),
    ).fetchall()
    conn.close()
    
    return {r["event_type"]: r["count"] for r in rows}


def prune_events(older_than_days: int = 30) -> int:
    """Delete events older than specified days.
    
    Returns:
        Number of events deleted
    """
    conn = _get_conn()
    
    from datetime import timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(days=older_than_days)).isoformat()
    
    cursor = conn.execute(
        "DELETE FROM event_log WHERE timestamp < ?",
        (cutoff,),
    )
    deleted = cursor.rowcount
    conn.commit()
    conn.close()
    
    return deleted
