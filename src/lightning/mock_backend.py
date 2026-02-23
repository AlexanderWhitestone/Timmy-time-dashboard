"""Mock Lightning backend for development and testing.

Provides in-memory invoice tracking without requiring a real
Lightning node. Invoices auto-settle for easy testing.
"""

import hashlib
import hmac
import logging
import os
import secrets
import time
from typing import Optional

from lightning.base import Invoice, LightningBackend, LightningError

logger = logging.getLogger(__name__)

# Secret for HMAC-based invoice verification (mock mode)
_HMAC_SECRET_DEFAULT = "timmy-sovereign-sats"
_HMAC_SECRET_RAW = os.environ.get("L402_HMAC_SECRET", _HMAC_SECRET_DEFAULT)
_HMAC_SECRET = _HMAC_SECRET_RAW.encode()

if _HMAC_SECRET_RAW == _HMAC_SECRET_DEFAULT:
    logger.warning(
        "SEC: L402_HMAC_SECRET is using the default value — set a unique "
        "secret in .env before deploying to production."
    )


class MockBackend(LightningBackend):
    """In-memory Lightning backend for development.
    
    Creates fake invoices that auto-settle. No real sats are moved.
    Useful for:
    - Local development without LND setup
    - Integration tests
    - CI/CD pipelines
    
    Environment:
        LIGHTNING_BACKEND=mock
        L402_HMAC_SECRET=your-secret  # Optional
        MOCK_AUTO_SETTLE=true         # Auto-settle invoices (default: true)
    """
    
    name = "mock"
    
    def __init__(self) -> None:
        self._invoices: dict[str, Invoice] = {}
        self._auto_settle = os.environ.get("MOCK_AUTO_SETTLE", "true").lower() == "true"
        logger.info("MockBackend initialized — auto_settle: %s", self._auto_settle)
    
    def create_invoice(
        self,
        amount_sats: int,
        memo: str = "",
        expiry_seconds: int = 3600
    ) -> Invoice:
        """Create a mock invoice with fake bolt11 string."""
        preimage = secrets.token_hex(32)
        payment_hash = hashlib.sha256(bytes.fromhex(preimage)).hexdigest()
        
        # Generate mock bolt11 — deterministic based on secret
        signature = hmac.new(
            _HMAC_SECRET, 
            payment_hash.encode(), 
            hashlib.sha256
        ).hexdigest()[:20]
        
        payment_request = f"lnbc{amount_sats}n1mock{signature}"
        
        invoice = Invoice(
            payment_hash=payment_hash,
            payment_request=payment_request,
            amount_sats=amount_sats,
            memo=memo,
            preimage=preimage,
        )
        
        self._invoices[payment_hash] = invoice
        
        logger.info(
            "Mock invoice: %d sats — %s (hash: %s…)",
            amount_sats, memo, payment_hash[:12]
        )
        
        if self._auto_settle:
            # Mark as settled immediately for seamless dev experience
            invoice.settled = True
            invoice.settled_at = time.time()
            logger.debug("Auto-settled invoice %s…", payment_hash[:12])
        
        return invoice
    
    def check_payment(self, payment_hash: str) -> bool:
        """Check invoice status — auto-settles in mock mode."""
        invoice = self._invoices.get(payment_hash)
        if invoice is None:
            return False
        
        if self._auto_settle and not invoice.settled:
            invoice.settled = True
            invoice.settled_at = time.time()
        
        return invoice.settled
    
    def get_invoice(self, payment_hash: str) -> Optional[Invoice]:
        """Retrieve invoice by payment hash."""
        invoice = self._invoices.get(payment_hash)
        if invoice:
            # Update settled status
            self.check_payment(payment_hash)
        return invoice
    
    def settle_invoice(self, payment_hash: str, preimage: str) -> bool:
        """Manually settle an invoice with preimage verification."""
        invoice = self._invoices.get(payment_hash)
        if invoice is None:
            raise LightningError(f"Invoice not found: {payment_hash}")
        
        # Verify preimage matches payment_hash
        expected_hash = hashlib.sha256(bytes.fromhex(preimage)).hexdigest()
        if expected_hash != payment_hash:
            logger.warning(
                "Preimage mismatch for %s… — expected %s…, got %s…",
                payment_hash[:12],
                expected_hash[:12],
                hashlib.sha256(bytes.fromhex(preimage)).hexdigest()[:12]
            )
            return False
        
        invoice.settled = True
        invoice.settled_at = time.time()
        invoice.preimage = preimage
        
        logger.info("Settled invoice %s…", payment_hash[:12])
        return True
    
    def list_invoices(
        self,
        settled_only: bool = False,
        limit: int = 100
    ) -> list[Invoice]:
        """List recent invoices, newest first."""
        invoices = sorted(
            self._invoices.values(),
            key=lambda i: i.created_at,
            reverse=True
        )
        
        if settled_only:
            invoices = [i for i in invoices if i.settled]
        
        return invoices[:limit]
    
    def get_balance_sats(self) -> int:
        """Return fake balance for mock mode."""
        # Return a reasonable-looking number for UI testing
        return 1_000_000  # 1M sats
    
    def health_check(self) -> dict:
        """Always healthy in mock mode."""
        return {
            "ok": True,
            "error": None,
            "block_height": 800_000,
            "synced": True,
            "backend": "mock",
            "auto_settle": self._auto_settle,
        }
