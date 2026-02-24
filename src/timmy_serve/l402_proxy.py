"""L402 payment proxy — HMAC macaroon-based access control.

Implements the L402 protocol (formerly LSAT) for gating API access
behind Lightning payments.  A client that hasn't paid receives a
402 Payment Required response with a macaroon and invoice.  After
paying, the client presents the macaroon + preimage to gain access.

This is the economic layer that gives Timmy real agency — agents pay
each other in sats, not API keys.
"""

import base64
import hashlib
import hmac
import logging
import os
import time
from dataclasses import dataclass
from typing import Optional

from timmy_serve.payment_handler import payment_handler

logger = logging.getLogger(__name__)

_MACAROON_SECRET_DEFAULT = "timmy-macaroon-secret"
_MACAROON_SECRET_RAW = os.environ.get("L402_MACAROON_SECRET", _MACAROON_SECRET_DEFAULT)
_MACAROON_SECRET = _MACAROON_SECRET_RAW.encode()

_HMAC_SECRET_DEFAULT = "timmy-hmac-secret"
_HMAC_SECRET_RAW = os.environ.get("L402_HMAC_SECRET", _HMAC_SECRET_DEFAULT)
_HMAC_SECRET = _HMAC_SECRET_RAW.encode()

if _MACAROON_SECRET_RAW == _MACAROON_SECRET_DEFAULT or _HMAC_SECRET_RAW == _HMAC_SECRET_DEFAULT:
    logger.warning(
        "SEC: L402 secrets are using default values — set L402_MACAROON_SECRET "
        "and L402_HMAC_SECRET in .env before deploying to production."
    )


@dataclass
class Macaroon:
    """Simplified HMAC-based macaroon for L402 authentication."""
    identifier: str  # payment_hash
    signature: str   # HMAC signature
    location: str = "timmy-time"
    version: int = 1
    hmac_secret: str = ""  # Added for multi-key support

    def serialize(self) -> str:
        """Encode the macaroon as a base64 string."""
        raw = f"{self.version}:{self.location}:{self.identifier}:{self.signature}:{self.hmac_secret}"
        return base64.urlsafe_b64encode(raw.encode()).decode()

    @classmethod
    def deserialize(cls, token: str) -> Optional["Macaroon"]:
        """Decode a base64 macaroon string."""
        try:
            raw = base64.urlsafe_b64decode(token.encode()).decode()
            parts = raw.split(":")
            if len(parts) < 4:
                return None
            return cls(
                version=int(parts[0]),
                location=parts[1],
                identifier=parts[2],
                signature=parts[3],
                hmac_secret=parts[4] if len(parts) > 4 else "",
            )
        except Exception:
            return None


def _sign(identifier: str, hmac_secret: Optional[str] = None) -> str:
    """Create an HMAC signature for a macaroon identifier using two-key derivation.
    
    The base macaroon secret is used to derive a key-specific secret from the
    hmac_secret, which is then used to sign the identifier. This prevents
    macaroon forgery if the hmac_secret is known but the base secret is not.
    """
    key = hmac.new(
        _MACAROON_SECRET, 
        (hmac_secret or _HMAC_SECRET_RAW).encode(), 
        hashlib.sha256
    ).digest()
    return hmac.new(key, identifier.encode(), hashlib.sha256).hexdigest()


def create_l402_challenge(amount_sats: int, memo: str = "API access") -> dict:
    """Create an L402 challenge: invoice + macaroon.

    Returns a dict with:
      - macaroon: serialized macaroon token
      - invoice: bolt11 payment request
      - payment_hash: for tracking payment status
    """
    invoice = payment_handler.create_invoice(amount_sats, memo)
    hmac_secret = _HMAC_SECRET_RAW
    signature = _sign(invoice.payment_hash, hmac_secret)
    macaroon = Macaroon(
        identifier=invoice.payment_hash,
        signature=signature,
        hmac_secret=hmac_secret,
    )
    logger.info("L402 challenge created: %d sats — %s", amount_sats, memo)
    return {
        "macaroon": macaroon.serialize(),
        "invoice": invoice.payment_request,
        "payment_hash": invoice.payment_hash,
    }


def verify_l402_token(token: str, preimage: Optional[str] = None) -> bool:
    """Verify an L402 token (macaroon + optional preimage).

    Verification checks:
    1. Macaroon signature is valid (HMAC matches)
    2. The corresponding invoice has been paid
    """
    macaroon = Macaroon.deserialize(token)
    if macaroon is None:
        logger.warning("L402: invalid macaroon format")
        return False

    # Check HMAC signature
    expected_sig = _sign(macaroon.identifier, macaroon.hmac_secret)
    if not hmac.compare_digest(macaroon.signature, expected_sig):
        logger.warning("L402: signature mismatch")
        return False

    # If preimage provided, settle the invoice
    if preimage:
        payment_handler.settle_invoice(macaroon.identifier, preimage)

    # Check payment status
    if not payment_handler.check_payment(macaroon.identifier):
        logger.info("L402: invoice not yet paid — %s…", macaroon.identifier[:12])
        return False

    logger.info("L402: access granted — %s…", macaroon.identifier[:12])
    return True
