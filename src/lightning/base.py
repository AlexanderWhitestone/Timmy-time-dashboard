"""Abstract base class for Lightning Network backends.

Defines the contract that all Lightning implementations must fulfill.
This abstraction allows the rest of the system to work identically
whether using mock invoices or real LND gRPC calls.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional
import time


@dataclass
class Invoice:
    """Lightning invoice data structure.
    
    This is backend-agnostic — the same structure is used for
    mock invoices and real LND invoices.
    """
    payment_hash: str
    payment_request: str  # bolt11 invoice string
    amount_sats: int
    memo: str = ""
    created_at: float = field(default_factory=time.time)
    settled: bool = False
    settled_at: Optional[float] = None
    preimage: Optional[str] = None
    
    @property
    def is_expired(self, expiry_seconds: int = 3600) -> bool:
        """Check if invoice has expired (default 1 hour)."""
        return time.time() > self.created_at + expiry_seconds


@dataclass
class PaymentReceipt:
    """Proof of payment for a settled invoice."""
    payment_hash: str
    preimage: str
    amount_sats: int
    settled_at: float


class LightningBackend(ABC):
    """Abstract interface for Lightning Network operations.
    
    Implementations:
    - MockBackend: In-memory invoices for development/testing
    - LndBackend: Real LND node via gRPC
    - ClnBackend: Core Lightning via Unix socket (future)
    
    All methods are synchronous. Async wrappers can be added at
    the application layer if needed.
    """
    
    name: str = "abstract"
    
    @abstractmethod
    def create_invoice(
        self, 
        amount_sats: int, 
        memo: str = "", 
        expiry_seconds: int = 3600
    ) -> Invoice:
        """Create a new Lightning invoice.
        
        Args:
            amount_sats: Amount in satoshis
            memo: Description shown in wallet
            expiry_seconds: How long until invoice expires
            
        Returns:
            Invoice object with payment_request (bolt11 string)
            
        Raises:
            LightningError: If invoice creation fails
        """
        pass
    
    @abstractmethod
    def check_payment(self, payment_hash: str) -> bool:
        """Check whether an invoice has been paid.
        
        Args:
            payment_hash: The invoice to check
            
        Returns:
            True if paid/settled, False otherwise
            
        Note:
            In mock mode this may auto-settle. In production this
            queries the Lightning node for the invoice state.
        """
        pass
    
    @abstractmethod
    def get_invoice(self, payment_hash: str) -> Optional[Invoice]:
        """Get full invoice details by payment hash.
        
        Args:
            payment_hash: The invoice to retrieve
            
        Returns:
            Invoice object or None if not found
        """
        pass
    
    @abstractmethod
    def settle_invoice(self, payment_hash: str, preimage: str) -> bool:
        """Manually settle an invoice with a preimage.
        
        This is primarily used for testing or when receiving
        payments through a separate channel.
        
        Args:
            payment_hash: The invoice to settle
            preimage: The payment preimage (proof of payment)
            
        Returns:
            True if settlement succeeded
            
        Raises:
            ValueError: If preimage doesn't match payment_hash
        """
        pass
    
    @abstractmethod
    def list_invoices(
        self, 
        settled_only: bool = False,
        limit: int = 100
    ) -> list[Invoice]:
        """List recent invoices.
        
        Args:
            settled_only: Only return paid invoices
            limit: Maximum number to return (newest first)
            
        Returns:
            List of Invoice objects
        """
        pass
    
    @abstractmethod
    def get_balance_sats(self) -> int:
        """Get the node's available balance in satoshis.
        
        Returns:
            Spendable on-chain + off-chain balance
            
        Note:
            Mock backends may return a fake value.
        """
        pass
    
    @abstractmethod
    def health_check(self) -> dict:
        """Check backend health and connectivity.
        
        Returns:
            Dict with:
                - ok: bool
                - error: str or None
                - block_height: int (if available)
                - synced: bool (if available)
        """
        pass


class LightningError(Exception):
    """Base exception for Lightning backend errors."""
    pass


class InvoiceNotFoundError(LightningError):
    """Raised when an invoice doesn't exist."""
    pass


class PaymentFailedError(LightningError):
    """Raised when a payment operation fails."""
    pass


class BackendNotAvailableError(LightningError):
    """Raised when the Lightning node is unreachable."""
    pass
