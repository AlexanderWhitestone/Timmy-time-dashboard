"""Spark memory — SQLite-backed event capture and memory consolidation.

Captures swarm events (tasks posted, bids, assignments, completions,
failures) and distills them into higher-level memories with importance
scoring.  This is the persistence layer for Spark Intelligence.

Tables
------
spark_events   — raw event log (every swarm event)
spark_memories — consolidated insights extracted from event patterns
"""

import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

DB_PATH = Path("data/spark.db")

# Importance thresholds
IMPORTANCE_LOW = 0.3
IMPORTANCE_MEDIUM = 0.6
IMPORTANCE_HIGH = 0.8


@dataclass
class SparkEvent:
    """A single captured swarm event."""
    id: str
    event_type: str          # task_posted, bid, assignment, completion, failure
    agent_id: Optional[str]
    task_id: Optional[str]
    description: str
    data: str                # JSON payload
    importance: float        # 0.0–1.0
    created_at: str


@dataclass
class SparkMemory:
    """A consolidated memory distilled from event patterns."""
    id: str
    memory_type: str         # pattern, insight, anomaly
    subject: str             # agent_id or "system"
    content: str             # Human-readable insight
    confidence: float        # 0.0–1.0
    source_events: int       # How many events contributed
    created_at: str
    expires_at: Optional[str]


def _get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS spark_events (
            id          TEXT PRIMARY KEY,
            event_type  TEXT NOT NULL,
            agent_id    TEXT,
            task_id     TEXT,
            description TEXT NOT NULL DEFAULT '',
            data        TEXT NOT NULL DEFAULT '{}',
            importance  REAL NOT NULL DEFAULT 0.5,
            created_at  TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS spark_memories (
            id              TEXT PRIMARY KEY,
            memory_type     TEXT NOT NULL,
            subject         TEXT NOT NULL DEFAULT 'system',
            content         TEXT NOT NULL,
            confidence      REAL NOT NULL DEFAULT 0.5,
            source_events   INTEGER NOT NULL DEFAULT 0,
            created_at      TEXT NOT NULL,
            expires_at      TEXT
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_events_type ON spark_events(event_type)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_events_agent ON spark_events(agent_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_events_task ON spark_events(task_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_memories_subject ON spark_memories(subject)"
    )
    conn.commit()
    return conn


# ── Importance scoring ──────────────────────────────────────────────────────

def score_importance(event_type: str, data: dict) -> float:
    """Compute importance score for an event (0.0–1.0).

    High-importance events: failures, large bids, first-time patterns.
    Low-importance events: routine bids, repeated successful completions.
    """
    base_scores = {
        "task_posted": 0.4,
        "bid_submitted": 0.2,
        "task_assigned": 0.5,
        "task_completed": 0.6,
        "task_failed": 0.9,
        "agent_joined": 0.5,
        "prediction_result": 0.7,
    }
    score = base_scores.get(event_type, 0.5)

    # Boost for failures (always important to learn from)
    if event_type == "task_failed":
        score = min(1.0, score + 0.1)

    # Boost for high-value bids
    bid_sats = data.get("bid_sats", 0)
    if bid_sats and bid_sats > 80:
        score = min(1.0, score + 0.15)

    return round(score, 2)


# ── Event recording ─────────────────────────────────────────────────────────

def record_event(
    event_type: str,
    description: str,
    agent_id: Optional[str] = None,
    task_id: Optional[str] = None,
    data: str = "{}",
    importance: Optional[float] = None,
) -> str:
    """Record a swarm event.  Returns the event id."""
    import json
    event_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    if importance is None:
        try:
            parsed = json.loads(data) if isinstance(data, str) else data
        except (json.JSONDecodeError, TypeError):
            parsed = {}
        importance = score_importance(event_type, parsed)

    conn = _get_conn()
    conn.execute(
        """
        INSERT INTO spark_events
            (id, event_type, agent_id, task_id, description, data, importance, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (event_id, event_type, agent_id, task_id, description, data, importance, now),
    )
    conn.commit()
    conn.close()
    return event_id


def get_events(
    event_type: Optional[str] = None,
    agent_id: Optional[str] = None,
    task_id: Optional[str] = None,
    limit: int = 100,
    min_importance: float = 0.0,
) -> list[SparkEvent]:
    """Query events with optional filters."""
    conn = _get_conn()
    query = "SELECT * FROM spark_events WHERE importance >= ?"
    params: list = [min_importance]

    if event_type:
        query += " AND event_type = ?"
        params.append(event_type)
    if agent_id:
        query += " AND agent_id = ?"
        params.append(agent_id)
    if task_id:
        query += " AND task_id = ?"
        params.append(task_id)

    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)

    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [
        SparkEvent(
            id=r["id"],
            event_type=r["event_type"],
            agent_id=r["agent_id"],
            task_id=r["task_id"],
            description=r["description"],
            data=r["data"],
            importance=r["importance"],
            created_at=r["created_at"],
        )
        for r in rows
    ]


def count_events(event_type: Optional[str] = None) -> int:
    """Count events, optionally filtered by type."""
    conn = _get_conn()
    if event_type:
        row = conn.execute(
            "SELECT COUNT(*) FROM spark_events WHERE event_type = ?",
            (event_type,),
        ).fetchone()
    else:
        row = conn.execute("SELECT COUNT(*) FROM spark_events").fetchone()
    conn.close()
    return row[0]


# ── Memory consolidation ───────────────────────────────────────────────────

def store_memory(
    memory_type: str,
    subject: str,
    content: str,
    confidence: float = 0.5,
    source_events: int = 0,
    expires_at: Optional[str] = None,
) -> str:
    """Store a consolidated memory.  Returns the memory id."""
    mem_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    conn = _get_conn()
    conn.execute(
        """
        INSERT INTO spark_memories
            (id, memory_type, subject, content, confidence, source_events, created_at, expires_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (mem_id, memory_type, subject, content, confidence, source_events, now, expires_at),
    )
    conn.commit()
    conn.close()
    return mem_id


def get_memories(
    memory_type: Optional[str] = None,
    subject: Optional[str] = None,
    min_confidence: float = 0.0,
    limit: int = 50,
) -> list[SparkMemory]:
    """Query memories with optional filters."""
    conn = _get_conn()
    query = "SELECT * FROM spark_memories WHERE confidence >= ?"
    params: list = [min_confidence]

    if memory_type:
        query += " AND memory_type = ?"
        params.append(memory_type)
    if subject:
        query += " AND subject = ?"
        params.append(subject)

    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)

    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [
        SparkMemory(
            id=r["id"],
            memory_type=r["memory_type"],
            subject=r["subject"],
            content=r["content"],
            confidence=r["confidence"],
            source_events=r["source_events"],
            created_at=r["created_at"],
            expires_at=r["expires_at"],
        )
        for r in rows
    ]


def count_memories(memory_type: Optional[str] = None) -> int:
    """Count memories, optionally filtered by type."""
    conn = _get_conn()
    if memory_type:
        row = conn.execute(
            "SELECT COUNT(*) FROM spark_memories WHERE memory_type = ?",
            (memory_type,),
        ).fetchone()
    else:
        row = conn.execute("SELECT COUNT(*) FROM spark_memories").fetchone()
    conn.close()
    return row[0]
