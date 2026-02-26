"""Database models for Self-Upgrade Approval Queue."""

import json
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional

DB_PATH = Path("data/swarm.db")


class UpgradeStatus(str, Enum):
    """Status of an upgrade proposal."""
    PROPOSED = "proposed"
    APPROVED = "approved"
    REJECTED = "rejected"
    APPLIED = "applied"
    FAILED = "failed"
    EXPIRED = "expired"


@dataclass
class Upgrade:
    """A self-modification upgrade proposal."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    status: UpgradeStatus = UpgradeStatus.PROPOSED
    
    # Timestamps
    proposed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    approved_at: Optional[str] = None
    applied_at: Optional[str] = None
    rejected_at: Optional[str] = None
    
    # Proposal details
    branch_name: str = ""
    description: str = ""
    files_changed: list[str] = field(default_factory=list)
    diff_preview: str = ""
    
    # Test results
    test_passed: bool = False
    test_output: str = ""
    
    # Execution results
    error_message: Optional[str] = None
    approved_by: Optional[str] = None


def _get_conn() -> sqlite3.Connection:
    """Get database connection with schema initialized."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS upgrades (
            id TEXT PRIMARY KEY,
            status TEXT NOT NULL DEFAULT 'proposed',
            proposed_at TEXT NOT NULL,
            approved_at TEXT,
            applied_at TEXT,
            rejected_at TEXT,
            branch_name TEXT NOT NULL,
            description TEXT NOT NULL,
            files_changed TEXT,  -- JSON array
            diff_preview TEXT,
            test_passed INTEGER DEFAULT 0,
            test_output TEXT,
            error_message TEXT,
            approved_by TEXT
        )
        """
    )
    
    # Indexes
    conn.execute("CREATE INDEX IF NOT EXISTS idx_upgrades_status ON upgrades(status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_upgrades_proposed ON upgrades(proposed_at)")
    
    conn.commit()
    return conn


def create_upgrade(
    branch_name: str,
    description: str,
    files_changed: list[str],
    diff_preview: str,
    test_passed: bool = False,
    test_output: str = "",
) -> Upgrade:
    """Create a new upgrade proposal.
    
    Args:
        branch_name: Git branch name for the upgrade
        description: Human-readable description
        files_changed: List of files that would be modified
        diff_preview: Short diff preview for review
        test_passed: Whether tests passed on the branch
        test_output: Test output text
    
    Returns:
        The created Upgrade
    """
    upgrade = Upgrade(
        branch_name=branch_name,
        description=description,
        files_changed=files_changed,
        diff_preview=diff_preview,
        test_passed=test_passed,
        test_output=test_output,
    )
    
    conn = _get_conn()
    conn.execute(
        """
        INSERT INTO upgrades (id, status, proposed_at, branch_name, description,
                            files_changed, diff_preview, test_passed, test_output)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            upgrade.id,
            upgrade.status.value,
            upgrade.proposed_at,
            upgrade.branch_name,
            upgrade.description,
            json.dumps(files_changed),
            upgrade.diff_preview,
            int(test_passed),
            test_output,
        ),
    )
    conn.commit()
    conn.close()
    
    return upgrade


def get_upgrade(upgrade_id: str) -> Optional[Upgrade]:
    """Get upgrade by ID."""
    conn = _get_conn()
    row = conn.execute(
        "SELECT * FROM upgrades WHERE id = ?", (upgrade_id,)
    ).fetchone()
    conn.close()
    
    if not row:
        return None
    
    return Upgrade(
        id=row["id"],
        status=UpgradeStatus(row["status"]),
        proposed_at=row["proposed_at"],
        approved_at=row["approved_at"],
        applied_at=row["applied_at"],
        rejected_at=row["rejected_at"],
        branch_name=row["branch_name"],
        description=row["description"],
        files_changed=json.loads(row["files_changed"]) if row["files_changed"] else [],
        diff_preview=row["diff_preview"] or "",
        test_passed=bool(row["test_passed"]),
        test_output=row["test_output"] or "",
        error_message=row["error_message"],
        approved_by=row["approved_by"],
    )


def list_upgrades(
    status: Optional[UpgradeStatus] = None,
    limit: int = 100,
) -> list[Upgrade]:
    """List upgrades, optionally filtered by status."""
    conn = _get_conn()
    
    if status:
        rows = conn.execute(
            "SELECT * FROM upgrades WHERE status = ? ORDER BY proposed_at DESC LIMIT ?",
            (status.value, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM upgrades ORDER BY proposed_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    
    conn.close()
    
    return [
        Upgrade(
            id=r["id"],
            status=UpgradeStatus(r["status"]),
            proposed_at=r["proposed_at"],
            approved_at=r["approved_at"],
            applied_at=r["applied_at"],
            rejected_at=r["rejected_at"],
            branch_name=r["branch_name"],
            description=r["description"],
            files_changed=json.loads(r["files_changed"]) if r["files_changed"] else [],
            diff_preview=r["diff_preview"] or "",
            test_passed=bool(r["test_passed"]),
            test_output=r["test_output"] or "",
            error_message=r["error_message"],
            approved_by=r["approved_by"],
        )
        for r in rows
    ]


def approve_upgrade(upgrade_id: str, approved_by: str = "dashboard") -> Optional[Upgrade]:
    """Approve an upgrade proposal."""
    now = datetime.now(timezone.utc).isoformat()
    
    conn = _get_conn()
    cursor = conn.execute(
        """
        UPDATE upgrades 
        SET status = ?, approved_at = ?, approved_by = ?
        WHERE id = ? AND status = ?
        """,
        (UpgradeStatus.APPROVED.value, now, approved_by, upgrade_id, UpgradeStatus.PROPOSED.value),
    )
    conn.commit()
    updated = cursor.rowcount > 0
    conn.close()
    
    if not updated:
        return None
    
    return get_upgrade(upgrade_id)


def reject_upgrade(upgrade_id: str) -> Optional[Upgrade]:
    """Reject an upgrade proposal."""
    now = datetime.now(timezone.utc).isoformat()
    
    conn = _get_conn()
    cursor = conn.execute(
        """
        UPDATE upgrades 
        SET status = ?, rejected_at = ?
        WHERE id = ? AND status = ?
        """,
        (UpgradeStatus.REJECTED.value, now, upgrade_id, UpgradeStatus.PROPOSED.value),
    )
    conn.commit()
    updated = cursor.rowcount > 0
    conn.close()
    
    if not updated:
        return None
    
    return get_upgrade(upgrade_id)


def mark_applied(upgrade_id: str) -> Optional[Upgrade]:
    """Mark upgrade as successfully applied."""
    now = datetime.now(timezone.utc).isoformat()
    
    conn = _get_conn()
    cursor = conn.execute(
        """
        UPDATE upgrades 
        SET status = ?, applied_at = ?
        WHERE id = ? AND status = ?
        """,
        (UpgradeStatus.APPLIED.value, now, upgrade_id, UpgradeStatus.APPROVED.value),
    )
    conn.commit()
    updated = cursor.rowcount > 0
    conn.close()
    
    if not updated:
        return None
    
    return get_upgrade(upgrade_id)


def mark_failed(upgrade_id: str, error_message: str) -> Optional[Upgrade]:
    """Mark upgrade as failed."""
    conn = _get_conn()
    cursor = conn.execute(
        """
        UPDATE upgrades 
        SET status = ?, error_message = ?
        WHERE id = ? AND status = ?
        """,
        (UpgradeStatus.FAILED.value, error_message, upgrade_id, UpgradeStatus.APPROVED.value),
    )
    conn.commit()
    updated = cursor.rowcount > 0
    conn.close()
    
    if not updated:
        return None
    
    return get_upgrade(upgrade_id)


def get_pending_count() -> int:
    """Get count of pending (proposed) upgrades."""
    conn = _get_conn()
    row = conn.execute(
        "SELECT COUNT(*) as count FROM upgrades WHERE status = ?",
        (UpgradeStatus.PROPOSED.value,),
    ).fetchone()
    conn.close()
    return row["count"]


def prune_old_upgrades(older_than_days: int = 30) -> int:
    """Delete old completed upgrades."""
    from datetime import timedelta
    
    cutoff = (datetime.now(timezone.utc) - timedelta(days=older_than_days)).isoformat()
    
    conn = _get_conn()
    cursor = conn.execute(
        """
        DELETE FROM upgrades 
        WHERE proposed_at < ? AND status IN ('applied', 'rejected', 'failed')
        """,
        (cutoff,),
    )
    deleted = cursor.rowcount
    conn.commit()
    conn.close()
    
    return deleted
