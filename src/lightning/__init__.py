"""Lightning Network payment backend interface.

This module provides a pluggable interface for Lightning Network operations,
allowing seamless switching between mock (development) and real LND backends.

Usage:
    from lightning import get_backend, Invoice
    
    backend = get_backend()  # Uses LIGHTNING_BACKEND env var
    invoice = backend.create_invoice(amount_sats=100, memo="API access")
    paid = backend.check_payment(invoice.payment_hash)

Configuration:
    LIGHTNING_BACKEND=mock   # Default, for development
    LIGHTNING_BACKEND=lnd    # Real LND via gRPC
    
    # LND-specific settings (when backend=lnd)
    LND_GRPC_HOST=localhost:10009
    LND_TLS_CERT_PATH=/path/to/tls.cert
    LND_MACAROON_PATH=/path/to/admin.macaroon
"""

from lightning.base import Invoice, LightningBackend
from lightning.factory import get_backend

__all__ = ["Invoice", "LightningBackend", "get_backend"]
