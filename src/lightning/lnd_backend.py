"""LND Lightning backend — real Bitcoin payments via gRPC.

Connects to a local LND instance for production use.
Handles invoice creation, payment verification, and node health.

Requirements:
    pip install grpcio protobuf

LND Setup:
    1. Run LND with --tlsextradomain if accessing remotely
    2. Copy tls.cert and admin.macaroon to accessible paths
    3. Set environment variables (see below)

Environment:
    LIGHTNING_BACKEND=lnd
    LND_GRPC_HOST=localhost:10009
    LND_TLS_CERT_PATH=/path/to/tls.cert
    LND_MACAROON_PATH=/path/to/admin.macaroon
    LND_VERIFY_SSL=true  # Set to false only for development

Example LND gRPC calls:
    AddInvoice - Create new invoice
    LookupInvoice - Check payment status
    ListChannels - Get channel balances
    GetInfo - Node health and sync status
"""

import hashlib
import logging
import os
import ssl
import time
from typing import Optional

from lightning.base import (
    Invoice,
    LightningBackend,
    BackendNotAvailableError,
    InvoiceNotFoundError,
    LightningError,
)

logger = logging.getLogger(__name__)

# Optional import — graceful degradation if grpc not installed
try:
    import grpc
    GRPC_AVAILABLE = True
except ImportError:
    GRPC_AVAILABLE = False
    logger.warning("grpcio not installed — LND backend unavailable")


class LndBackend(LightningBackend):
    """Real Lightning backend via LND gRPC.
    
    This backend creates real invoices that require real sats to pay.
    Only use in production with proper LND setup.
    
    Connection is lazy — gRPC channel created on first use.
    """
    
    name = "lnd"
    
    def __init__(
        self,
        host: Optional[str] = None,
        tls_cert_path: Optional[str] = None,
        macaroon_path: Optional[str] = None,
        verify_ssl: Optional[bool] = None,
    ) -> None:
        """Initialize LND backend.
        
        Args:
            host: LND gRPC host:port (default: LND_GRPC_HOST env var)
            tls_cert_path: Path to tls.cert (default: LND_TLS_CERT_PATH env var)
            macaroon_path: Path to admin.macaroon (default: LND_MACAROON_PATH env var)
            verify_ssl: Verify TLS certificate (default: LND_VERIFY_SSL env var)
        """
        if not GRPC_AVAILABLE:
            raise LightningError(
                "grpcio not installed. Run: pip install grpcio protobuf"
            )
        
        self._host = host or os.environ.get("LND_GRPC_HOST", "localhost:10009")
        self._tls_cert_path = tls_cert_path or os.environ.get("LND_TLS_CERT_PATH")
        self._macaroon_path = macaroon_path or os.environ.get("LND_MACAROON_PATH")
        self._verify_ssl = verify_ssl
        if self._verify_ssl is None:
            self._verify_ssl = os.environ.get("LND_VERIFY_SSL", "true").lower() == "true"
        
        self._channel: Optional[grpc.Channel] = None
        self._stub: Optional[object] = None  # lnrpc.LightningStub
        
        logger.info(
            "LndBackend initialized — host: %s, tls: %s, macaroon: %s",
            self._host,
            "configured" if self._tls_cert_path else "default",
            "configured" if self._macaroon_path else "missing",
        )
        
        # Warn if config looks incomplete
        if not self._macaroon_path or not os.path.exists(self._macaroon_path):
            logger.warning(
                "LND macaroon not found at %s — payments will fail",
                self._macaroon_path
            )
    
    def _get_stub(self):
        """Lazy initialization of gRPC stub."""
        if self._stub is not None:
            return self._stub
        
        # Build channel credentials
        if self._tls_cert_path and os.path.exists(self._tls_cert_path):
            with open(self._tls_cert_path, "rb") as f:
                tls_cert = f.read()
            credentials = grpc.ssl_channel_credentials(tls_cert)
        else:
            # Use system root certificates
            credentials = grpc.ssl_channel_credentials()
        
        # Build macaroon credentials
        call_credentials = None
        if self._macaroon_path and os.path.exists(self._macaroon_path):
            with open(self._macaroon_path, "rb") as f:
                macaroon = f.read().hex()
            
            def metadata_callback(context, callback):
                callback([("macaroon", macaroon)], None)
            
            call_credentials = grpc.metadata_call_credentials(metadata_callback)
        
        # Combine credentials
        if call_credentials:
            composite = grpc.composite_channel_credentials(
                credentials,
                call_credentials
            )
        else:
            composite = credentials
        
        # Create channel
        self._channel = grpc.secure_channel(self._host, composite)
        
        # Import and create stub
        try:
            # lnd/grpc imports would go here
            # from lnd import lightning_pb2, lightning_pb2_grpc
            # self._stub = lightning_pb2_grpc.LightningStub(self._channel)
            
            # For now, stub is None — real implementation needs LND protos
            logger.warning("LND gRPC stubs not yet implemented — using placeholder")
            self._stub = None
            
        except ImportError as e:
            raise BackendNotAvailableError(
                f"LND gRPC stubs not available: {e}. "
                "Generate from LND proto files or install lndgrpc package."
            )
        
        return self._stub
    
    def _check_stub(self):
        """Ensure stub is available or raise appropriate error."""
        stub = self._get_stub()
        if stub is None:
            raise BackendNotAvailableError(
                "LND gRPC not fully implemented. "
                "This is a stub — implement gRPC calls to use real LND."
            )
        return stub
    
    def create_invoice(
        self,
        amount_sats: int,
        memo: str = "",
        expiry_seconds: int = 3600
    ) -> Invoice:
        """Create a real Lightning invoice via LND."""
        stub = self._check_stub()
        
        try:
            # Real implementation:
            # request = lightning_pb2.Invoice(
            #     value=amount_sats,
            #     memo=memo,
            #     expiry=expiry_seconds,
            # )
            # response = stub.AddInvoice(request)
            # 
            # return Invoice(
            #     payment_hash=response.r_hash.hex(),
            #     payment_request=response.payment_request,
            #     amount_sats=amount_sats,
            #     memo=memo,
            # )
            
            raise NotImplementedError(
                "LND gRPC integration incomplete. "
                "Generate protobuf stubs from LND source and implement AddInvoice."
            )
            
        except grpc.RpcError as e:
            logger.error("LND AddInvoice failed: %s", e)
            raise LightningError(f"Invoice creation failed: {e.details()}") from e
    
    def check_payment(self, payment_hash: str) -> bool:
        """Check if invoice is paid via LND LookupInvoice."""
        stub = self._check_stub()
        
        try:
            # Real implementation:
            # request = lightning_pb2.PaymentHash(
            #     r_hash=bytes.fromhex(payment_hash)
            # )
            # response = stub.LookupInvoice(request)
            # return response.state == lightning_pb2.Invoice.SETTLED
            
            raise NotImplementedError("LND LookupInvoice not implemented")
            
        except grpc.RpcError as e:
            if e.code() == grpc.StatusCode.NOT_FOUND:
                return False
            logger.error("LND LookupInvoice failed: %s", e)
            raise LightningError(f"Payment check failed: {e.details()}") from e
    
    def get_invoice(self, payment_hash: str) -> Optional[Invoice]:
        """Get invoice details from LND."""
        stub = self._check_stub()
        
        try:
            # request = lightning_pb2.PaymentHash(
            #     r_hash=bytes.fromhex(payment_hash)
            # )
            # response = stub.LookupInvoice(request)
            # 
            # return Invoice(
            #     payment_hash=response.r_hash.hex(),
            #     payment_request=response.payment_request,
            #     amount_sats=response.value,
            #     memo=response.memo,
            #     created_at=response.creation_date,
            #     settled=response.state == lightning_pb2.Invoice.SETTLED,
            #     settled_at=response.settle_date if response.settled else None,
            # )
            
            raise NotImplementedError("LND LookupInvoice not implemented")
            
        except grpc.RpcError as e:
            if e.code() == grpc.StatusCode.NOT_FOUND:
                return None
            raise LightningError(f"Invoice lookup failed: {e.details()}") from e
    
    def settle_invoice(self, payment_hash: str, preimage: str) -> bool:
        """Manually settle is not typically supported by LND.
        
        LND handles settlement automatically when payment arrives.
        This method exists for interface compatibility but raises
        an error in production.
        """
        logger.warning(
            "Manual invoice settlement not supported by LND — "
            "invoices settle automatically when paid"
        )
        return False
    
    def list_invoices(
        self,
        settled_only: bool = False,
        limit: int = 100
    ) -> list[Invoice]:
        """List recent invoices from LND."""
        stub = self._check_stub()
        
        try:
            # request = lightning_pb2.ListInvoiceRequest(
            #     num_max_invoices=limit,
            #     reversed=True,  # Newest first
            # )
            # response = stub.ListInvoices(request)
            # 
            # invoices = []
            # for inv in response.invoices:
            #     if settled_only and inv.state != lightning_pb2.Invoice.SETTLED:
            #         continue
            #     invoices.append(self._grpc_invoice_to_model(inv))
            # return invoices
            
            raise NotImplementedError("LND ListInvoices not implemented")
            
        except grpc.RpcError as e:
            raise LightningError(f"List invoices failed: {e.details()}") from e
    
    def get_balance_sats(self) -> int:
        """Get total balance from LND."""
        stub = self._check_stub()
        
        try:
            # response = stub.WalletBalance(request)
            # return response.total_balance
            
            # For now, return 0 to indicate "real value not available"
            logger.warning("LND WalletBalance not implemented — returning 0")
            return 0
            
        except grpc.RpcError as e:
            raise LightningError(f"Balance check failed: {e.details()}") from e
    
    def health_check(self) -> dict:
        """Check LND node health and sync status."""
        stub = self._check_stub()
        
        try:
            # response = stub.GetInfo(request)
            # return {
            #     "ok": response.synced_to_chain and response.synced_to_graph,
            #     "error": None,
            #     "block_height": response.block_height,
            #     "synced": response.synced_to_chain,
            #     "backend": "lnd",
            #     "version": response.version,
            #     "alias": response.alias,
            # }
            
            # Return degraded status if stub not available
            return {
                "ok": False,
                "error": "LND gRPC not fully implemented — see documentation",
                "block_height": 0,
                "synced": False,
                "backend": "lnd-stub",
            }
            
        except grpc.RpcError as e:
            return {
                "ok": False,
                "error": str(e.details()),
                "block_height": 0,
                "synced": False,
                "backend": "lnd",
            }


def generate_lnd_protos():
    """Documentation for generating LND protobuf stubs.
    
    To use real LND, you need to generate Python gRPC stubs from
    the LND proto files.
    
    Steps:
        1. Clone LND repository:
           git clone https://github.com/lightningnetwork/lnd.git
           
        2. Install protoc and grpc tools:
           pip install grpcio grpcio-tools
           
        3. Generate Python stubs:
           python -m grpc_tools.protoc \
               --proto_path=lnd/lnrpc \
               --python_out=src/lightning/protos \
               --grpc_python_out=src/lightning/protos \
               lnd/lnrpc/lightning.proto
        
        4. Import and use the generated stubs in LndBackend
    
    Alternative:
        Use the 'lndgrpc' or 'pylnd' packages from PyPI if available.
    """
    print(generate_lnd_protos.__doc__)
