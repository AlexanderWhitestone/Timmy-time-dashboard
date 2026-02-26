"""Tests for the Lightning backend interface.

Covers:
- Mock backend functionality
- Backend factory
- Invoice lifecycle
- Error handling
"""

import os
import pytest

from lightning import get_backend, Invoice
from lightning.base import LightningError
from lightning.mock_backend import MockBackend


class TestMockBackend:
    """Tests for the mock Lightning backend."""
    
    def test_create_invoice(self):
        """Mock backend creates invoices with valid structure."""
        backend = MockBackend()
        invoice = backend.create_invoice(100, "Test invoice")
        
        assert invoice.amount_sats == 100
        assert invoice.memo == "Test invoice"
        assert invoice.payment_hash is not None
        assert len(invoice.payment_hash) == 64  # SHA256 hex
        assert invoice.payment_request.startswith("lnbc100n1mock")
        assert invoice.preimage is not None
        
    def test_invoice_auto_settle(self):
        """Mock invoices auto-settle by default."""
        backend = MockBackend()
        invoice = backend.create_invoice(100)
        
        assert invoice.settled is True
        assert invoice.settled_at is not None
        assert backend.check_payment(invoice.payment_hash) is True
        
    def test_invoice_no_auto_settle(self):
        """Mock invoices don't auto-settle when disabled."""
        os.environ["MOCK_AUTO_SETTLE"] = "false"
        backend = MockBackend()
        
        invoice = backend.create_invoice(100)
        assert invoice.settled is False
        
        # Manual settle works
        assert backend.settle_invoice(invoice.payment_hash, invoice.preimage)
        assert backend.check_payment(invoice.payment_hash) is True
        
        # Cleanup
        os.environ["MOCK_AUTO_SETTLE"] = "true"
        
    def test_settle_wrong_preimage(self):
        """Settling with wrong preimage fails."""
        backend = MockBackend()
        invoice = backend.create_invoice(100)
        
        wrong_preimage = "00" * 32
        assert backend.settle_invoice(invoice.payment_hash, wrong_preimage) is False
        
    def test_check_payment_nonexistent(self):
        """Checking unknown payment hash returns False."""
        backend = MockBackend()
        assert backend.check_payment("nonexistent") is False
        
    def test_get_invoice(self):
        """Can retrieve created invoice."""
        backend = MockBackend()
        created = backend.create_invoice(100, "Test")
        
        retrieved = backend.get_invoice(created.payment_hash)
        assert retrieved is not None
        assert retrieved.payment_hash == created.payment_hash
        assert retrieved.amount_sats == 100
        
    def test_get_invoice_nonexistent(self):
        """Retrieving unknown invoice returns None."""
        backend = MockBackend()
        assert backend.get_invoice("nonexistent") is None
        
    def test_list_invoices(self):
        """Can list all invoices."""
        backend = MockBackend()
        
        inv1 = backend.create_invoice(100, "First")
        inv2 = backend.create_invoice(200, "Second")
        
        invoices = backend.list_invoices()
        hashes = {i.payment_hash for i in invoices}
        
        assert inv1.payment_hash in hashes
        assert inv2.payment_hash in hashes
        
    def test_list_invoices_settled_only(self):
        """Can filter to settled invoices only."""
        os.environ["MOCK_AUTO_SETTLE"] = "false"
        backend = MockBackend()
        
        unsettled = backend.create_invoice(100, "Unsettled")
        
        # Settle it manually
        backend.settle_invoice(unsettled.payment_hash, unsettled.preimage)
        
        settled = backend.list_invoices(settled_only=True)
        assert len(settled) == 1
        assert settled[0].payment_hash == unsettled.payment_hash
        
        os.environ["MOCK_AUTO_SETTLE"] = "true"
        
    def test_list_invoices_limit(self):
        """List respects limit parameter."""
        backend = MockBackend()
        
        for i in range(5):
            backend.create_invoice(i + 1)
            
        invoices = backend.list_invoices(limit=3)
        assert len(invoices) == 3
        
    def test_get_balance(self):
        """Mock returns reasonable fake balance."""
        backend = MockBackend()
        balance = backend.get_balance_sats()
        assert balance == 1_000_000  # 1M sats
        
    def test_health_check(self):
        """Mock health check always passes."""
        backend = MockBackend()
        health = backend.health_check()
        
        assert health["ok"] is True
        assert health["error"] is None
        assert health["synced"] is True
        assert health["backend"] == "mock"
        
    def test_invoice_expiry(self):
        """Invoice expiry detection works."""
        backend = MockBackend()
        invoice = backend.create_invoice(100, expiry_seconds=3600)
        
        # Just created, not expired with 1 hour window
        assert invoice.is_expired is False
        
        # Expire manually by changing created_at
        import time
        invoice.created_at = time.time() - 7200  # 2 hours ago
        assert invoice.is_expired is True  # Beyond 1 hour default


class TestBackendFactory:
    """Tests for backend factory."""
    
    def test_get_backend_mock(self):
        """Factory returns mock backend by default."""
        backend = get_backend("mock")
        assert backend.name == "mock"
        assert isinstance(backend, MockBackend)
        
    def test_get_backend_default(self):
        """Factory uses LIGHTNING_BACKEND env var."""
        old_backend = os.environ.get("LIGHTNING_BACKEND")
        os.environ["LIGHTNING_BACKEND"] = "mock"
        
        backend = get_backend()
        assert backend.name == "mock"
        
        if old_backend:
            os.environ["LIGHTNING_BACKEND"] = old_backend
            
    def test_get_backend_unknown(self):
        """Unknown backend raises error."""
        with pytest.raises(ValueError) as exc:
            get_backend("unknown")
        assert "Unknown Lightning backend" in str(exc.value)
        
    def test_list_backends(self):
        """Can list available backends."""
        from lightning.factory import list_backends
        backends = list_backends()
        
        assert "mock" in backends
        # lnd only if grpc available
        

class TestInvoiceModel:
    """Tests for Invoice dataclass."""
    
    def test_invoice_creation(self):
        """Invoice can be created with required fields."""
        import time
        now = time.time()
        
        invoice = Invoice(
            payment_hash="abcd" * 16,
            payment_request="lnbc100n1mock",
            amount_sats=100,
            memo="Test",
            created_at=now,
        )
        
        assert invoice.payment_hash == "abcd" * 16
        assert invoice.amount_sats == 100
        assert invoice.settled is False
        
    def test_invoice_is_expired(self):
        """Invoice expiry calculation is correct."""
        import time
        
        invoice = Invoice(
            payment_hash="abcd" * 16,
            payment_request="lnbc100n1mock",
            amount_sats=100,
            created_at=time.time() - 7200,  # 2 hours ago
        )
        
        # is_expired is a property with default 1 hour expiry
        assert invoice.is_expired is True  # 2 hours > 1 hour default
