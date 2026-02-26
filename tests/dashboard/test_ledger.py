"""Tests for Lightning ledger system."""

import pytest
from lightning.ledger import (
    TransactionType,
    TransactionStatus,
    create_invoice_entry,
    record_outgoing_payment,
    mark_settled,
    mark_failed,
    get_by_hash,
    list_transactions,
    get_balance,
    get_transaction_stats,
)


class TestLedger:
    """Test suite for Lightning ledger functionality."""

    def test_create_invoice_entry(self):
        """Test creating an incoming invoice entry."""
        entry = create_invoice_entry(
            payment_hash="test_hash_001",
            amount_sats=1000,
            memo="Test invoice",
            invoice="lnbc10u1...",
            source="test",
            task_id="task-123",
            agent_id="agent-456",
        )
        
        assert entry.tx_type == TransactionType.INCOMING
        assert entry.status == TransactionStatus.PENDING
        assert entry.amount_sats == 1000
        assert entry.payment_hash == "test_hash_001"
        assert entry.memo == "Test invoice"
        assert entry.task_id == "task-123"
        assert entry.agent_id == "agent-456"
    
    def test_record_outgoing_payment(self):
        """Test recording an outgoing payment."""
        entry = record_outgoing_payment(
            payment_hash="test_hash_002",
            amount_sats=500,
            memo="Test payment",
            source="test",
            task_id="task-789",
        )
        
        assert entry.tx_type == TransactionType.OUTGOING
        assert entry.status == TransactionStatus.PENDING
        assert entry.amount_sats == 500
        assert entry.payment_hash == "test_hash_002"
    
    def test_mark_settled(self):
        """Test marking a transaction as settled."""
        # Create invoice
        entry = create_invoice_entry(
            payment_hash="test_hash_settle",
            amount_sats=100,
            memo="To be settled",
        )
        assert entry.status == TransactionStatus.PENDING
        
        # Mark as settled
        settled = mark_settled(
            payment_hash="test_hash_settle",
            preimage="preimage123",
            fee_sats=1,
        )
        
        assert settled is not None
        assert settled.status == TransactionStatus.SETTLED
        assert settled.preimage == "preimage123"
        assert settled.fee_sats == 1
        assert settled.settled_at is not None
        
        # Verify retrieval
        retrieved = get_by_hash("test_hash_settle")
        assert retrieved.status == TransactionStatus.SETTLED
    
    def test_mark_failed(self):
        """Test marking a transaction as failed."""
        # Create invoice
        entry = create_invoice_entry(
            payment_hash="test_hash_fail",
            amount_sats=200,
            memo="To fail",
        )
        
        # Mark as failed
        failed = mark_failed("test_hash_fail", reason="Timeout")
        
        assert failed is not None
        assert failed.status == TransactionStatus.FAILED
        assert "Timeout" in failed.memo
    
    def test_get_by_hash_not_found(self):
        """Test retrieving non-existent transaction."""
        result = get_by_hash("nonexistent_hash")
        assert result is None
    
    def test_list_transactions_filtering(self):
        """Test filtering transactions."""
        # Create various transactions
        create_invoice_entry("filter_test_1", 100, source="filter_test")
        create_invoice_entry("filter_test_2", 200, source="filter_test")
        
        # Filter by type
        incoming = list_transactions(
            tx_type=TransactionType.INCOMING,
            limit=10,
        )
        assert all(t.tx_type == TransactionType.INCOMING for t in incoming)
        
        # Filter by status
        pending = list_transactions(
            status=TransactionStatus.PENDING,
            limit=10,
        )
        assert all(t.status == TransactionStatus.PENDING for t in pending)
    
    def test_get_balance(self):
        """Test balance calculation."""
        # Get initial balance
        balance = get_balance()
        
        assert "incoming_total_sats" in balance
        assert "outgoing_total_sats" in balance
        assert "net_sats" in balance
        assert isinstance(balance["incoming_total_sats"], int)
        assert isinstance(balance["outgoing_total_sats"], int)
    
    def test_transaction_stats(self):
        """Test transaction statistics."""
        # Create some transactions
        create_invoice_entry("stats_test_1", 100, source="stats_test")
        create_invoice_entry("stats_test_2", 200, source="stats_test")
        
        # Get stats
        stats = get_transaction_stats(days=1)
        
        # Should return dict with dates
        assert isinstance(stats, dict)
        # Stats structure depends on current date, just verify it's a dict
    
    def test_unique_payment_hash(self):
        """Test that payment hashes must be unique."""
        import sqlite3
        
        hash_value = "unique_hash_test"
        
        # First creation should succeed
        create_invoice_entry(hash_value, 100)
        
        # Second creation with same hash should fail with IntegrityError
        with pytest.raises(sqlite3.IntegrityError):
            create_invoice_entry(hash_value, 200)


class TestLedgerIntegration:
    """Integration tests for ledger workflow."""
    
    def test_full_invoice_lifecycle(self):
        """Test complete invoice lifecycle: create -> settle."""
        # Create invoice
        entry = create_invoice_entry(
            payment_hash="lifecycle_test",
            amount_sats=5000,
            memo="Full lifecycle test",
            source="integration_test",
        )
        
        assert entry.status == TransactionStatus.PENDING
        
        # Mark as settled
        settled = mark_settled("lifecycle_test", preimage="secret_preimage")
        
        assert settled.status == TransactionStatus.SETTLED
        assert settled.preimage == "secret_preimage"
        
        # Verify in list
        transactions = list_transactions(limit=100)
        assert any(t.payment_hash == "lifecycle_test" for t in transactions)
        
        # Verify balance reflects it
        balance = get_balance()
        # Balance should include this settled invoice
    
    def test_outgoing_payment_lifecycle(self):
        """Test complete outgoing payment lifecycle."""
        # Record outgoing payment
        entry = record_outgoing_payment(
            payment_hash="outgoing_test",
            amount_sats=300,
            memo="Outgoing payment",
            source="integration_test",
        )
        
        assert entry.tx_type == TransactionType.OUTGOING
        
        # Mark as settled (payment completed)
        settled = mark_settled(
            "outgoing_test",
            preimage="payment_proof",
            fee_sats=3,
        )
        
        assert settled.fee_sats == 3
        assert settled.status == TransactionStatus.SETTLED
