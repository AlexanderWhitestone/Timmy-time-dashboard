"""Approval item management — the governance layer for autonomous Timmy actions.

The GOLDEN_TIMMY constant is the single source of truth for whether Timmy
may act autonomously.  All features that want to take action must:

  1. Create an ApprovalItem
  2. Check GOLDEN_TIMMY
  3. If True  → wait for owner approval before executing
  4. If False → log the action and proceed (Dark Timmy mode)

Default is always True. The owner changes this intentionally.
"""

import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# GOLDEN TIMMY RULE
# ---------------------------------------------------------------------------
GOLDEN_TIMMY = True
# When True:  no autonomous action executes without an approved ApprovalItem.
# When False: Dark Timmy mode — Timmy may act on his own judgment.
# Default is always True. Owner changes this intentionally.

# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------
_DEFAULT_DB = Path.home() / ".timmy" / "approvals.db"
_EXPIRY_DAYS = 7


@dataclass
class ApprovalItem:
    id: str
    title: str
    description: str
    proposed_action: str   # what Timmy wants to do
    impact: str            # "low" | "medium" | "high"
    created_at: datetime
    status: str            # "pending" | "approved" | "rejected"


def _get_conn(db_path: Path = _DEFAULT_DB) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS approval_items (
            id              TEXT PRIMARY KEY,
            title           TEXT NOT NULL,
            description     TEXT NOT NULL,
            proposed_action TEXT NOT NULL,
            impact          TEXT NOT NULL DEFAULT 'low',
            created_at      TEXT NOT NULL,
            status          TEXT NOT NULL DEFAULT 'pending'
        )
        """
    )
    conn.commit()
    return conn


def _row_to_item(row: sqlite3.Row) -> ApprovalItem:
    return ApprovalItem(
        id=row["id"],
        title=row["title"],
        description=row["description"],
        proposed_action=row["proposed_action"],
        impact=row["impact"],
        created_at=datetime.fromisoformat(row["created_at"]),
        status=row["status"],
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def create_item(
    title: str,
    description: str,
    proposed_action: str,
    impact: str = "low",
    db_path: Path = _DEFAULT_DB,
) -> ApprovalItem:
    """Create and persist a new approval item."""
    item = ApprovalItem(
        id=str(uuid.uuid4()),
        title=title,
        description=description,
        proposed_action=proposed_action,
        impact=impact,
        created_at=datetime.now(timezone.utc),
        status="pending",
    )
    conn = _get_conn(db_path)
    conn.execute(
        """
        INSERT INTO approval_items
            (id, title, description, proposed_action, impact, created_at, status)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            item.id,
            item.title,
            item.description,
            item.proposed_action,
            item.impact,
            item.created_at.isoformat(),
            item.status,
        ),
    )
    conn.commit()
    conn.close()
    return item


def list_pending(db_path: Path = _DEFAULT_DB) -> list[ApprovalItem]:
    """Return all pending approval items, newest first."""
    conn = _get_conn(db_path)
    rows = conn.execute(
        "SELECT * FROM approval_items WHERE status = 'pending' ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    return [_row_to_item(r) for r in rows]


def list_all(db_path: Path = _DEFAULT_DB) -> list[ApprovalItem]:
    """Return all approval items regardless of status, newest first."""
    conn = _get_conn(db_path)
    rows = conn.execute(
        "SELECT * FROM approval_items ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    return [_row_to_item(r) for r in rows]


def get_item(item_id: str, db_path: Path = _DEFAULT_DB) -> Optional[ApprovalItem]:
    conn = _get_conn(db_path)
    row = conn.execute(
        "SELECT * FROM approval_items WHERE id = ?", (item_id,)
    ).fetchone()
    conn.close()
    return _row_to_item(row) if row else None


def approve(item_id: str, db_path: Path = _DEFAULT_DB) -> Optional[ApprovalItem]:
    """Mark an approval item as approved."""
    conn = _get_conn(db_path)
    conn.execute(
        "UPDATE approval_items SET status = 'approved' WHERE id = ?", (item_id,)
    )
    conn.commit()
    conn.close()
    return get_item(item_id, db_path)


def reject(item_id: str, db_path: Path = _DEFAULT_DB) -> Optional[ApprovalItem]:
    """Mark an approval item as rejected."""
    conn = _get_conn(db_path)
    conn.execute(
        "UPDATE approval_items SET status = 'rejected' WHERE id = ?", (item_id,)
    )
    conn.commit()
    conn.close()
    return get_item(item_id, db_path)


def expire_old(db_path: Path = _DEFAULT_DB) -> int:
    """Auto-expire pending items older than EXPIRY_DAYS. Returns count removed."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=_EXPIRY_DAYS)).isoformat()
    conn = _get_conn(db_path)
    cursor = conn.execute(
        "DELETE FROM approval_items WHERE status = 'pending' AND created_at < ?",
        (cutoff,),
    )
    conn.commit()
    count = cursor.rowcount
    conn.close()
    return count
