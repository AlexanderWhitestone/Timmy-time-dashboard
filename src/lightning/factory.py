"""Lightning backend factory — creates appropriate backend based on config.

Usage:
    from lightning import get_backend
    
    backend = get_backend()  # Reads LIGHTNING_BACKEND env var
    # or
    backend = get_backend("lnd")  # Force specific backend
"""

import logging
import os
from typing import Optional

from config import settings
from lightning.base import LightningBackend

logger = logging.getLogger(__name__)

# Registry of available backends
_BACKENDS: dict[str, type[LightningBackend]] = {}


def _register_backends():
    """Register available backends (lazy import to avoid dependencies)."""
    global _BACKENDS
    
    if _BACKENDS:
        return
    
    # Always register mock backend
    from lightning.mock_backend import MockBackend
    _BACKENDS["mock"] = MockBackend
    
    # Register LND backend if grpc available
    try:
        from lightning.lnd_backend import LndBackend
        _BACKENDS["lnd"] = LndBackend
        logger.debug("LND backend registered (grpc available)")
    except ImportError as e:
        logger.debug("LND backend not available: %s", e)
    
    # Future: Add Core Lightning (CLN) backend here
    # try:
    #     from lightning.cln_backend import ClnBackend
    #     _BACKENDS["cln"] = ClnBackend
    # except ImportError:
    #     pass


def get_backend(name: Optional[str] = None) -> LightningBackend:
    """Get a Lightning backend instance.
    
    Args:
        name: Backend type ('mock', 'lnd'). 
              Defaults to LIGHTNING_BACKEND env var or 'mock'.
    
    Returns:
        Configured LightningBackend instance
    
    Raises:
        ValueError: If backend type is unknown
        LightningError: If backend initialization fails
    
    Examples:
        >>> backend = get_backend()  # Use env var or default
        >>> backend = get_backend("mock")  # Force mock
        >>> backend = get_backend("lnd")   # Use real LND
    """
    _register_backends()
    
    backend_name = (name or settings.lightning_backend).lower()
    
    if backend_name not in _BACKENDS:
        available = ", ".join(_BACKENDS.keys())
        raise ValueError(
            f"Unknown Lightning backend: {backend_name!r}. "
            f"Available: {available}"
        )
    
    backend_class = _BACKENDS[backend_name]
    instance = backend_class()
    
    logger.info("Lightning backend ready: %s", backend_name)
    return instance


def list_backends() -> list[str]:
    """List available backend types.
    
    Returns:
        List of backend names that can be passed to get_backend()
    """
    _register_backends()
    return list(_BACKENDS.keys())


def get_backend_info() -> dict:
    """Get information about the current backend configuration.
    
    Returns:
        Dict with backend info for health/status endpoints
    """
    backend_name = settings.lightning_backend

    return {
        "configured_backend": backend_name,
        "available_backends": list_backends(),
        "env_vars": {
            "LIGHTNING_BACKEND": backend_name,
            "LND_GRPC_HOST": os.environ.get("LND_GRPC_HOST", "not set"),
            "LND_TLS_CERT_PATH": "set" if os.environ.get("LND_TLS_CERT_PATH") else "not set",
            "LND_MACAROON_PATH": "set" if os.environ.get("LND_MACAROON_PATH") else "not set",
        }
    }
