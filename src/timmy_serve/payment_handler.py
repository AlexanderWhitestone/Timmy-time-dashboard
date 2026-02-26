"""Lightning invoice creation and payment verification.

This module is now a thin wrapper around the lightning backend interface.
The actual backend (mock or LND) is selected via LIGHTNING_BACKEND env var.

For backward compatibility, the PaymentHandler class and payment_handler
singleton are preserved, but they delegate to the lightning backend.

All transactions are logged to the ledger for audit and accounting.
"""

import logging
from typing import Optional

# Import from the new lightning module
from lightning import get_backend, Invoice
from lightning.base import LightningBackend
from lightning.ledger import (
    create_invoice_entry,
    mark_settled,
    get_balance,
    list_transactions,
)

logger = logging.getLogger(__name__)


class PaymentHandler:
    """Creates and verifies Lightning invoices.
    
    This class is a wrapper around the LightningBackend interface.
    It exists for backward compatibility — new code should use
    the lightning module directly.
    
    Usage:
        from timmy_serve.payment_handler import payment_handler
        
        invoice = payment_handler.create_invoice(100, "API access")
        if payment_handler.check_payment(invoice.payment_hash):
            print("Paid!")
    """

    def __init__(self, backend: Optional[LightningBackend] = None) -> None:
        """Initialize the payment handler.
        
        Args:
            backend: Lightning backend to use. If None, uses get_backend()
                    which reads LIGHTNING_BACKEND env var.
        """
        self._backend = backend or get_backend()
        logger.info("PaymentHandler initialized — backend: %s", self._backend.name)

    def create_invoice(
        self,
        amount_sats: int,
        memo: str = "",
        source: str = "payment_handler",
        task_id: Optional[str] = None,
        agent_id: Optional[str] = None,
    ) -> Invoice:
        """Create a new Lightning invoice.
        
        Args:
            amount_sats: Invoice amount in satoshis
            memo: Payment description
            source: Component creating the invoice
            task_id: Associated task ID
            agent_id: Associated agent ID
        """
        invoice = self._backend.create_invoice(amount_sats, memo)
        logger.info(
            "Invoice created: %d sats — %s (hash: %s…)",
            amount_sats, memo, invoice.payment_hash[:12],
        )
        
        # Log to ledger
        create_invoice_entry(
            payment_hash=invoice.payment_hash,
            amount_sats=amount_sats,
            memo=memo,
            invoice=invoice.bolt11 if hasattr(invoice, 'bolt11') else None,
            source=source,
            task_id=task_id,
            agent_id=agent_id,
        )
        
        return invoice

    def check_payment(self, payment_hash: str) -> bool:
        """Check whether an invoice has been paid.
        
        If paid, updates the ledger entry.
        """
        is_paid = self._backend.check_payment(payment_hash)
        
        if is_paid:
            # Update ledger entry
            mark_settled(payment_hash)
        
        return is_paid

    def settle_invoice(self, payment_hash: str, preimage: str) -> bool:
        """Manually settle an invoice with a preimage (for testing).
        
        Also updates the ledger entry.
        """
        result = self._backend.settle_invoice(payment_hash, preimage)
        
        if result:
            mark_settled(payment_hash, preimage=preimage)
        
        return result

    def get_invoice(self, payment_hash: str) -> Optional[Invoice]:
        """Get invoice details by payment hash."""
        return self._backend.get_invoice(payment_hash)

    def list_invoices(self, settled_only: bool = False) -> list[Invoice]:
        """List recent invoices."""
        return self._backend.list_invoices(settled_only=settled_only)
    
    def health_check(self) -> dict:
        """Check backend health."""
        return self._backend.health_check()
    
    @property
    def backend_name(self) -> str:
        """Get the name of the current backend."""
        return self._backend.name
    
    def get_balance(self) -> dict:
        """Get current balance summary from ledger.
        
        Returns:
            Dict with incoming, outgoing, pending, and available balances
        """
        return get_balance()
    
    def list_transactions(self, limit: int = 100, **filters) -> list:
        """List transactions from ledger.
        
        Args:
            limit: Maximum number of transactions
            **filters: Optional filters (tx_type, status, task_id, agent_id)
        
        Returns:
            List of LedgerEntry objects
        """
        return list_transactions(limit=limit, **filters)


# Module-level singleton
payment_handler = PaymentHandler()
