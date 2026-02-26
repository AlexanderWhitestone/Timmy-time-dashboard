# ADR 018: Lightning Network Transaction Ledger

## Status
Accepted

## Context
The system needed to track all Lightning Network payments (incoming and outgoing) for accounting, dashboard display, and audit purposes. The existing payment handler created invoices but didn't persist transaction history.

## Decision
Implement a SQLite-based ledger (`ledger` table) that tracks all Lightning transactions with their lifecycle status.

## Transaction Types

| Type | Description |
|------|-------------|
| `incoming` | Invoice created (we're receiving payment) |
| `outgoing` | Payment sent (we're paying someone) |

## Transaction Status

| Status | Description |
|--------|-------------|
| `pending` | Awaiting settlement |
| `settled` | Payment completed |
| `failed` | Payment failed |
| `expired` | Invoice expired |

## Schema
```sql
CREATE TABLE ledger (
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
);
```

## Usage

```python
from lightning.ledger import (
    create_invoice_entry,
    mark_settled,
    get_balance,
)

# Create invoice record
entry = create_invoice_entry(
    payment_hash=invoice.payment_hash,
    amount_sats=1000,
    memo="API access",
    source="payment_handler",
    task_id=task.id,
)

# Mark as paid
mark_settled(payment_hash, preimage="secret")

# Get balance
balance = get_balance()
print(f"Net: {balance['net_sats']} sats")
```

## Integration
The `PaymentHandler` automatically:
- Creates ledger entries when invoices are created
- Updates status when payments are checked/settled
- Tracks fees for outgoing payments

## Balance Calculation
```python
{
    "incoming_total_sats": total_received,
    "outgoing_total_sats": total_sent,
    "fees_paid_sats": total_fees,
    "net_sats": incoming - outgoing - fees,
    "pending_incoming_sats": pending_received,
    "pending_outgoing_sats": pending_sent,
    "available_sats": net - pending_outgoing,
}
```

## Consequences
- **Positive**: Complete payment history, balance tracking, audit trail
- **Negative**: Additional DB writes, must keep in sync with actual Lightning node

## Future Work
- Reconciliation job to sync with LND node
- Export to accounting formats (CSV, QIF)
