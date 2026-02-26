"""Lightning Network transaction ledger.

Tracks all Lightning payments in SQLite for audit, accounting, and dashboard display.
"""

import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional

DB_PATH = Path("data/swarm.db")


class TransactionType(str, Enum):
    """Types of Lightning transactions."""
    INCOMING = "incoming"  # Invoice created (we're receiving)
    OUTGOING = "outgoing"  # Payment sent (we're paying)


class TransactionStatus(str, Enum):
    """Status of a transaction."""
    PENDING = "pending"
    SETTLED = "settled"
    FAILED = "failed"
    EXPIRED = "expired"


@dataclass
class LedgerEntry:
    """A Lightning transaction record."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    tx_type: TransactionType = TransactionType.INCOMING
    status: TransactionStatus = TransactionStatus.PENDING
    payment_hash: str = ""  # Lightning payment hash
    amount_sats: int = 0
    memo: str = ""  # Description/purpose
    invoice: Optional[str] = None  # BOLT11 invoice string
    preimage: Optional[str] = None  # Payment preimage (proof of payment)
    source: str = ""  # Component that created the transaction
    task_id: Optional[str] = None  # Associated task, if any
    agent_id: Optional[str] = None  # Associated agent, if any
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    settled_at: Optional[str] = None
    fee_sats: int = 0  # Routing fee paid


def _get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS ledger (
            id TEXT PRIMARY KEY,
            tx_type TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            payment_hash TEXT UNIQUE NOT NULL,
            amount_sats INTEGER NOT NULL,
            memo TEXT,
            invoice TEXT,
            preimage TEXT,
            source TEXT NOT NULL,
            task_id TEXT,
            agent_id TEXT,
            created_at TEXT NOT NULL,
            settled_at TEXT,
            fee_sats INTEGER DEFAULT 0
        )
        """
    )
    # Create indexes for common queries
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_ledger_status ON ledger(status)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_ledger_hash ON ledger(payment_hash)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_ledger_task ON ledger(task_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_ledger_agent ON ledger(agent_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_ledger_created ON ledger(created_at)"
    )
    conn.commit()
    return conn


def create_invoice_entry(
    payment_hash: str,
    amount_sats: int,
    memo: str = "",
    invoice: Optional[str] = None,
    source: str = "system",
    task_id: Optional[str] = None,
    agent_id: Optional[str] = None,
) -> LedgerEntry:
    """Record a new incoming invoice (we're receiving payment).
    
    Args:
        payment_hash: Lightning payment hash
        amount_sats: Invoice amount in satoshis
        memo: Payment description
        invoice: Full BOLT11 invoice string
        source: Component that created the invoice
        task_id: Associated task ID
        agent_id: Associated agent ID
    
    Returns:
        The created LedgerEntry
    """
    entry = LedgerEntry(
        tx_type=TransactionType.INCOMING,
        status=TransactionStatus.PENDING,
        payment_hash=payment_hash,
        amount_sats=amount_sats,
        memo=memo,
        invoice=invoice,
        source=source,
        task_id=task_id,
        agent_id=agent_id,
    )
    
    conn = _get_conn()
    conn.execute(
        """
        INSERT INTO ledger (id, tx_type, status, payment_hash, amount_sats,
                          memo, invoice, source, task_id, agent_id, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            entry.id,
            entry.tx_type.value,
            entry.status.value,
            entry.payment_hash,
            entry.amount_sats,
            entry.memo,
            entry.invoice,
            entry.source,
            entry.task_id,
            entry.agent_id,
            entry.created_at,
        ),
    )
    conn.commit()
    conn.close()
    return entry


def record_outgoing_payment(
    payment_hash: str,
    amount_sats: int,
    memo: str = "",
    invoice: Optional[str] = None,
    source: str = "system",
    task_id: Optional[str] = None,
    agent_id: Optional[str] = None,
) -> LedgerEntry:
    """Record an outgoing payment (we're paying someone).
    
    Args:
        payment_hash: Lightning payment hash
        amount_sats: Payment amount in satoshis
        memo: Payment description
        invoice: BOLT11 invoice we paid
        source: Component that initiated payment
        task_id: Associated task ID
        agent_id: Associated agent ID
    
    Returns:
        The created LedgerEntry
    """
    entry = LedgerEntry(
        tx_type=TransactionType.OUTGOING,
        status=TransactionStatus.PENDING,
        payment_hash=payment_hash,
        amount_sats=amount_sats,
        memo=memo,
        invoice=invoice,
        source=source,
        task_id=task_id,
        agent_id=agent_id,
    )
    
    conn = _get_conn()
    conn.execute(
        """
        INSERT INTO ledger (id, tx_type, status, payment_hash, amount_sats,
                          memo, invoice, source, task_id, agent_id, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            entry.id,
            entry.tx_type.value,
            entry.status.value,
            entry.payment_hash,
            entry.amount_sats,
            entry.memo,
            entry.invoice,
            entry.source,
            entry.task_id,
            entry.agent_id,
            entry.created_at,
        ),
    )
    conn.commit()
    conn.close()
    return entry


def mark_settled(
    payment_hash: str,
    preimage: Optional[str] = None,
    fee_sats: int = 0,
) -> Optional[LedgerEntry]:
    """Mark a transaction as settled (payment received or sent successfully).
    
    Args:
        payment_hash: Lightning payment hash
        preimage: Payment preimage (proof of payment)
        fee_sats: Routing fee paid (for outgoing payments)
    
    Returns:
        Updated LedgerEntry or None if not found
    """
    settled_at = datetime.now(timezone.utc).isoformat()
    
    conn = _get_conn()
    cursor = conn.execute(
        """
        UPDATE ledger
        SET status = ?, preimage = ?, settled_at = ?, fee_sats = ?
        WHERE payment_hash = ?
        """,
        (TransactionStatus.SETTLED.value, preimage, settled_at, fee_sats, payment_hash),
    )
    conn.commit()
    
    if cursor.rowcount == 0:
        conn.close()
        return None
    
    # Fetch and return updated entry
    entry = get_by_hash(payment_hash)
    conn.close()
    return entry


def mark_failed(payment_hash: str, reason: str = "") -> Optional[LedgerEntry]:
    """Mark a transaction as failed.
    
    Args:
        payment_hash: Lightning payment hash
        reason: Failure reason (stored in memo)
    
    Returns:
        Updated LedgerEntry or None if not found
    """
    conn = _get_conn()
    cursor = conn.execute(
        """
        UPDATE ledger
        SET status = ?, memo = memo || ' [FAILED: ' || ? || ']'
        WHERE payment_hash = ?
        """,
        (TransactionStatus.FAILED.value, reason, payment_hash),
    )
    conn.commit()
    
    if cursor.rowcount == 0:
        conn.close()
        return None
    
    entry = get_by_hash(payment_hash)
    conn.close()
    return entry


def get_by_hash(payment_hash: str) -> Optional[LedgerEntry]:
    """Get a transaction by payment hash."""
    conn = _get_conn()
    row = conn.execute(
        "SELECT * FROM ledger WHERE payment_hash = ?", (payment_hash,)
    ).fetchone()
    conn.close()
    
    if row is None:
        return None
    
    return LedgerEntry(
        id=row["id"],
        tx_type=TransactionType(row["tx_type"]),
        status=TransactionStatus(row["status"]),
        payment_hash=row["payment_hash"],
        amount_sats=row["amount_sats"],
        memo=row["memo"],
        invoice=row["invoice"],
        preimage=row["preimage"],
        source=row["source"],
        task_id=row["task_id"],
        agent_id=row["agent_id"],
        created_at=row["created_at"],
        settled_at=row["settled_at"],
        fee_sats=row["fee_sats"],
    )


def list_transactions(
    tx_type: Optional[TransactionType] = None,
    status: Optional[TransactionStatus] = None,
    task_id: Optional[str] = None,
    agent_id: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> list[LedgerEntry]:
    """List transactions with optional filtering.
    
    Returns:
        List of LedgerEntry objects, newest first
    """
    conn = _get_conn()
    
    conditions = []
    params = []
    
    if tx_type:
        conditions.append("tx_type = ?")
        params.append(tx_type.value)
    if status:
        conditions.append("status = ?")
        params.append(status.value)
    if task_id:
        conditions.append("task_id = ?")
        params.append(task_id)
    if agent_id:
        conditions.append("agent_id = ?")
        params.append(agent_id)
    
    where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
    
    query = f"""
        SELECT * FROM ledger
        {where_clause}
        ORDER BY created_at DESC
        LIMIT ? OFFSET ?
    """
    params.extend([limit, offset])
    
    rows = conn.execute(query, params).fetchall()
    conn.close()
    
    return [
        LedgerEntry(
            id=r["id"],
            tx_type=TransactionType(r["tx_type"]),
            status=TransactionStatus(r["status"]),
            payment_hash=r["payment_hash"],
            amount_sats=r["amount_sats"],
            memo=r["memo"],
            invoice=r["invoice"],
            preimage=r["preimage"],
            source=r["source"],
            task_id=r["task_id"],
            agent_id=r["agent_id"],
            created_at=r["created_at"],
            settled_at=r["settled_at"],
            fee_sats=r["fee_sats"],
        )
        for r in rows
    ]


def get_balance() -> dict:
    """Get current balance summary.
    
    Returns:
        Dict with incoming, outgoing, pending, and available balances
    """
    conn = _get_conn()
    
    # Incoming (invoices we created that are settled)
    incoming = conn.execute(
        """
        SELECT COALESCE(SUM(amount_sats), 0) as total
        FROM ledger
        WHERE tx_type = ? AND status = ?
        """,
        (TransactionType.INCOMING.value, TransactionStatus.SETTLED.value),
    ).fetchone()["total"]
    
    # Outgoing (payments we sent that are settled)
    outgoing_result = conn.execute(
        """
        SELECT COALESCE(SUM(amount_sats), 0) as total,
               COALESCE(SUM(fee_sats), 0) as fees
        FROM ledger
        WHERE tx_type = ? AND status = ?
        """,
        (TransactionType.OUTGOING.value, TransactionStatus.SETTLED.value),
    ).fetchone()
    outgoing = outgoing_result["total"]
    fees = outgoing_result["fees"]
    
    # Pending incoming
    pending_incoming = conn.execute(
        """
        SELECT COALESCE(SUM(amount_sats), 0) as total
        FROM ledger
        WHERE tx_type = ? AND status = ?
        """,
        (TransactionType.INCOMING.value, TransactionStatus.PENDING.value),
    ).fetchone()["total"]
    
    # Pending outgoing
    pending_outgoing = conn.execute(
        """
        SELECT COALESCE(SUM(amount_sats), 0) as total
        FROM ledger
        WHERE tx_type = ? AND status = ?
        """,
        (TransactionType.OUTGOING.value, TransactionStatus.PENDING.value),
    ).fetchone()["total"]
    
    conn.close()
    
    return {
        "incoming_total_sats": incoming,
        "outgoing_total_sats": outgoing,
        "fees_paid_sats": fees,
        "net_sats": incoming - outgoing - fees,
        "pending_incoming_sats": pending_incoming,
        "pending_outgoing_sats": pending_outgoing,
        "available_sats": incoming - outgoing - fees - pending_outgoing,
    }


def get_transaction_stats(days: int = 30) -> dict:
    """Get transaction statistics for the last N days.
    
    Returns:
        Dict with daily transaction counts and volumes
    """
    conn = _get_conn()
    
    from datetime import timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    
    rows = conn.execute(
        """
        SELECT 
            date(created_at) as date,
            tx_type,
            status,
            COUNT(*) as count,
            SUM(amount_sats) as volume
        FROM ledger
        WHERE created_at > ?
        GROUP BY date(created_at), tx_type, status
        ORDER BY date DESC
        """,
        (cutoff,),
    ).fetchall()
    
    conn.close()
    
    stats = {}
    for r in rows:
        date = r["date"]
        if date not in stats:
            stats[date] = {"incoming": {"count": 0, "volume": 0}, 
                          "outgoing": {"count": 0, "volume": 0}}
        
        tx_type = r["tx_type"]
        if tx_type == TransactionType.INCOMING.value:
            stats[date]["incoming"]["count"] += r["count"]
            stats[date]["incoming"]["volume"] += r["volume"]
        else:
            stats[date]["outgoing"]["count"] += r["count"]
            stats[date]["outgoing"]["volume"] += r["volume"]
    
    return stats
