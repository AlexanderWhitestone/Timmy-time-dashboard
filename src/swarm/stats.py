"""Swarm agent statistics — persistent bid history and earnings.

Stores one row per bid submitted during an auction.  When an auction closes
and a winner is declared, the winning row is flagged.  This lets the
marketplace compute per-agent stats (tasks won, total sats earned) without
modifying the existing tasks / registry tables.

All operations are synchronous SQLite writes, consistent with the existing
swarm.tasks and swarm.registry modules.
"""

import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

DB_PATH = Path("data/swarm.db")


def _get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS bid_history (
            id          TEXT PRIMARY KEY,
            task_id     TEXT NOT NULL,
            agent_id    TEXT NOT NULL,
            bid_sats    INTEGER NOT NULL,
            won         INTEGER NOT NULL DEFAULT 0,
            created_at  TEXT NOT NULL
        )
        """
    )
    conn.commit()
    return conn


def record_bid(
    task_id: str,
    agent_id: str,
    bid_sats: int,
    won: bool = False,
) -> str:
    """Insert a bid record and return its row id."""
    row_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    conn = _get_conn()
    conn.execute(
        """
        INSERT INTO bid_history (id, task_id, agent_id, bid_sats, won, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (row_id, task_id, agent_id, bid_sats, int(won), now),
    )
    conn.commit()
    conn.close()
    return row_id


def mark_winner(task_id: str, agent_id: str) -> int:
    """Mark the winning bid for a task.  Returns the number of rows updated."""
    conn = _get_conn()
    cursor = conn.execute(
        """
        UPDATE bid_history
        SET won = 1
        WHERE task_id = ? AND agent_id = ?
        """,
        (task_id, agent_id),
    )
    conn.commit()
    updated = cursor.rowcount
    conn.close()
    return updated


def get_agent_stats(agent_id: str) -> dict:
    """Return tasks_won, total_earned, and total_bids for an agent."""
    conn = _get_conn()
    row = conn.execute(
        """
        SELECT
            COUNT(*)           AS total_bids,
            SUM(won)           AS tasks_won,
            SUM(CASE WHEN won = 1 THEN bid_sats ELSE 0 END) AS total_earned
        FROM bid_history
        WHERE agent_id = ?
        """,
        (agent_id,),
    ).fetchone()
    conn.close()
    return {
        "total_bids": row["total_bids"] or 0,
        "tasks_won": row["tasks_won"] or 0,
        "total_earned": row["total_earned"] or 0,
    }


def get_all_agent_stats() -> dict[str, dict]:
    """Return stats keyed by agent_id for all agents that have bid."""
    conn = _get_conn()
    rows = conn.execute(
        """
        SELECT
            agent_id,
            COUNT(*)           AS total_bids,
            SUM(won)           AS tasks_won,
            SUM(CASE WHEN won = 1 THEN bid_sats ELSE 0 END) AS total_earned
        FROM bid_history
        GROUP BY agent_id
        """
    ).fetchall()
    conn.close()
    return {
        r["agent_id"]: {
            "total_bids": r["total_bids"] or 0,
            "tasks_won": r["tasks_won"] or 0,
            "total_earned": r["total_earned"] or 0,
        }
        for r in rows
    }


def list_bids(task_id: Optional[str] = None) -> list[dict]:
    """Return raw bid rows, optionally filtered to a single task."""
    conn = _get_conn()
    if task_id:
        rows = conn.execute(
            "SELECT * FROM bid_history WHERE task_id = ? ORDER BY created_at",
            (task_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM bid_history ORDER BY created_at DESC"
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
