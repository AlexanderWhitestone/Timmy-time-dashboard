"""SQLite-backed agent registry for the swarm.

Each agent that joins the swarm registers here with its ID, name, and
capabilities.  The registry is the source of truth for which agents are
available to bid on tasks.
"""

import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

DB_PATH = Path("data/swarm.db")


def _get_conn() -> sqlite3.Connection:
    """Get a SQLite connection."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS agents (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'idle',
            capabilities TEXT DEFAULT '',
            registered_at TEXT NOT NULL,
            last_seen TEXT NOT NULL
        )
        """
    )
    conn.commit()
    return conn


@dataclass
class AgentRecord:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    status: str = "idle"  # idle | busy | offline
    capabilities: str = ""  # comma-separated tags
    registered_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    last_seen: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


def _row_to_record(row: sqlite3.Row) -> AgentRecord:
    return AgentRecord(
        id=row["id"],
        name=row["name"],
        status=row["status"],
        capabilities=row["capabilities"],
        registered_at=row["registered_at"],
        last_seen=row["last_seen"],
    )


def register(name: str, capabilities: str = "", agent_id: Optional[str] = None) -> AgentRecord:
    record = AgentRecord(
        id=agent_id or str(uuid.uuid4()),
        name=name,
        capabilities=capabilities,
    )
    conn = _get_conn()
    try:
        conn.execute(
            """
            INSERT OR REPLACE INTO agents (id, name, status, capabilities, registered_at, last_seen)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (record.id, record.name, record.status, record.capabilities,
             record.registered_at, record.last_seen),
        )
        conn.commit()
    finally:
        conn.close()
    return record


def unregister(agent_id: str) -> bool:
    conn = _get_conn()
    try:
        cursor = conn.execute("DELETE FROM agents WHERE id = ?", (agent_id,))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def get_agent(agent_id: str) -> Optional[AgentRecord]:
    conn = _get_conn()
    try:
        row = conn.execute("SELECT * FROM agents WHERE id = ?", (agent_id,)).fetchone()
        return _row_to_record(row) if row else None
    finally:
        conn.close()


def list_agents(status: Optional[str] = None) -> list[AgentRecord]:
    conn = _get_conn()
    try:
        if status:
            rows = conn.execute(
                "SELECT * FROM agents WHERE status = ? ORDER BY registered_at DESC",
                (status,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM agents ORDER BY registered_at DESC"
            ).fetchall()
        return [_row_to_record(r) for r in rows]
    finally:
        conn.close()


def update_status(agent_id: str, status: str) -> Optional[AgentRecord]:
    now = datetime.now(timezone.utc).isoformat()
    conn = _get_conn()
    try:
        conn.execute(
            "UPDATE agents SET status = ?, last_seen = ? WHERE id = ?",
            (status, now, agent_id),
        )
        conn.commit()
        return get_agent(agent_id)
    finally:
        conn.close()


def heartbeat(agent_id: str) -> Optional[AgentRecord]:
    """Update last_seen timestamp for a registered agent."""
    now = datetime.now(timezone.utc).isoformat()
    conn = _get_conn()
    try:
        conn.execute(
            "UPDATE agents SET last_seen = ? WHERE id = ?",
            (now, agent_id),
        )
        conn.commit()
        return get_agent(agent_id)
    finally:
        conn.close()
