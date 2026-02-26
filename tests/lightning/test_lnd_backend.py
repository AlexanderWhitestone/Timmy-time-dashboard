"""Functional tests for lightning.lnd_backend — LND gRPC backend.

gRPC is stubbed via sys.modules; tests verify initialization, error
handling, and the placeholder method behavior.
"""

import importlib
import os
import sys
from unittest.mock import patch, MagicMock

import pytest

from lightning.base import (
    BackendNotAvailableError,
    Invoice,
    LightningError,
)


def _make_grpc_mock():
    """Create a mock grpc module with required attributes."""
    mock_grpc = MagicMock()
    mock_grpc.StatusCode.NOT_FOUND = "NOT_FOUND"
    mock_grpc.RpcError = type("RpcError", (Exception,), {
        "code": lambda self: "NOT_FOUND",
        "details": lambda self: "mocked error",
    })
    return mock_grpc


@pytest.fixture
def lnd_module():
    """Reload lnd_backend with grpc stubbed so GRPC_AVAILABLE=True."""
    grpc_mock = _make_grpc_mock()
    old = sys.modules.get("grpc")
    sys.modules["grpc"] = grpc_mock
    try:
        import lightning.lnd_backend as mod
        importlib.reload(mod)
        yield mod
    finally:
        if old is not None:
            sys.modules["grpc"] = old
        else:
            sys.modules.pop("grpc", None)
        # Reload to restore original state
        import lightning.lnd_backend as mod2
        importlib.reload(mod2)


class TestLndBackendInit:
    def test_init_with_explicit_params(self, lnd_module):
        backend = lnd_module.LndBackend(
            host="localhost:10009",
            tls_cert_path="/fake/tls.cert",
            macaroon_path="/fake/admin.macaroon",
            verify_ssl=True,
        )
        assert backend._host == "localhost:10009"
        assert backend._tls_cert_path == "/fake/tls.cert"
        assert backend._macaroon_path == "/fake/admin.macaroon"
        assert backend._verify_ssl is True

    def test_init_from_env_vars(self, lnd_module):
        env = {
            "LND_GRPC_HOST": "remote:9999",
            "LND_TLS_CERT_PATH": "/env/tls.cert",
            "LND_MACAROON_PATH": "/env/macaroon",
            "LND_VERIFY_SSL": "false",
        }
        with patch.dict(os.environ, env):
            backend = lnd_module.LndBackend()
            assert backend._host == "remote:9999"
            assert backend._verify_ssl is False

    def test_init_raises_without_grpc(self):
        from lightning.lnd_backend import LndBackend
        with pytest.raises(LightningError, match="grpcio not installed"):
            LndBackend()

    def test_name_is_lnd(self, lnd_module):
        assert lnd_module.LndBackend.name == "lnd"

    def test_grpc_available_true_after_reload(self, lnd_module):
        assert lnd_module.GRPC_AVAILABLE is True


class TestLndBackendMethods:
    @pytest.fixture
    def backend(self, lnd_module):
        return lnd_module.LndBackend(
            host="localhost:10009",
            macaroon_path="/fake/path",
        )

    def test_check_stub_raises_not_available(self, backend):
        """_check_stub should raise BackendNotAvailableError when stub is None."""
        with pytest.raises(BackendNotAvailableError, match="not fully implemented"):
            backend._check_stub()

    def test_create_invoice_raises_not_available(self, backend):
        with pytest.raises(BackendNotAvailableError):
            backend.create_invoice(1000, memo="test")

    def test_check_payment_raises_not_available(self, backend):
        with pytest.raises(BackendNotAvailableError):
            backend.check_payment("abc123")

    def test_get_invoice_raises_not_available(self, backend):
        with pytest.raises(BackendNotAvailableError):
            backend.get_invoice("abc123")

    def test_settle_invoice_returns_false(self, backend):
        """LND auto-settles, so manual settle always returns False."""
        result = backend.settle_invoice("hash", "preimage")
        assert result is False

    def test_list_invoices_raises_not_available(self, backend):
        with pytest.raises(BackendNotAvailableError):
            backend.list_invoices()

    def test_get_balance_raises_not_available(self, backend):
        with pytest.raises(BackendNotAvailableError):
            backend.get_balance_sats()

    def test_health_check_raises_not_available(self, backend):
        with pytest.raises(BackendNotAvailableError):
            backend.health_check()
