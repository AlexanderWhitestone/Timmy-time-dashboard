"""Tests for the L402 proxy and payment handler."""

import hashlib

import pytest


# ── Payment Handler ──────────────────────────────────────────────────────────

def test_create_invoice():
    from timmy_serve.payment_handler import PaymentHandler
    handler = PaymentHandler()
    invoice = handler.create_invoice(100, "test payment")
    assert invoice.amount_sats == 100
    assert invoice.memo == "test payment"
    assert invoice.payment_hash is not None
    assert invoice.payment_request.startswith("lnbc")


def test_check_payment_mock_auto_settles():
    from timmy_serve.payment_handler import PaymentHandler
    handler = PaymentHandler()
    invoice = handler.create_invoice(50, "auto settle")
    assert handler.check_payment(invoice.payment_hash) is True


def test_check_payment_nonexistent():
    from timmy_serve.payment_handler import PaymentHandler
    handler = PaymentHandler()
    assert handler.check_payment("nonexistent-hash") is False


def test_settle_invoice_with_preimage():
    from timmy_serve.payment_handler import PaymentHandler
    handler = PaymentHandler()
    invoice = handler.create_invoice(75, "preimage test")
    invoice.settled = False  # Reset for manual settlement
    assert handler.settle_invoice(invoice.payment_hash, invoice.preimage) is True
    assert invoice.settled is True


def test_settle_invoice_wrong_preimage():
    from timmy_serve.payment_handler import PaymentHandler
    handler = PaymentHandler()
    invoice = handler.create_invoice(75, "wrong preimage")
    invoice.settled = False
    assert handler.settle_invoice(invoice.payment_hash, "0" * 64) is False


def test_list_invoices():
    from timmy_serve.payment_handler import PaymentHandler
    handler = PaymentHandler()
    handler.create_invoice(10, "a")
    handler.create_invoice(20, "b")
    assert len(handler.list_invoices()) == 2


def test_list_invoices_settled_only():
    from timmy_serve.payment_handler import PaymentHandler
    handler = PaymentHandler()
    inv = handler.create_invoice(10, "settle me")
    handler.check_payment(inv.payment_hash)  # auto-settles in mock
    settled = handler.list_invoices(settled_only=True)
    assert len(settled) >= 1


def test_get_invoice():
    from timmy_serve.payment_handler import PaymentHandler
    handler = PaymentHandler()
    inv = handler.create_invoice(100, "get me")
    found = handler.get_invoice(inv.payment_hash)
    assert found is not None
    assert found.amount_sats == 100


# ── L402 Proxy ───────────────────────────────────────────────────────────────

def test_create_l402_challenge():
    from timmy_serve.l402_proxy import create_l402_challenge
    challenge = create_l402_challenge(100, "API access")
    assert "macaroon" in challenge
    assert "invoice" in challenge
    assert "payment_hash" in challenge


def test_verify_l402_token_valid():
    from timmy_serve.l402_proxy import create_l402_challenge, verify_l402_token
    challenge = create_l402_challenge(50, "verify test")
    # In mock mode, payment auto-settles
    assert verify_l402_token(challenge["macaroon"]) is True


def test_verify_l402_token_invalid_format():
    from timmy_serve.l402_proxy import verify_l402_token
    assert verify_l402_token("not-a-valid-token") is False


def test_macaroon_roundtrip():
    from timmy_serve.l402_proxy import Macaroon
    mac = Macaroon(identifier="test-id", signature="test-sig")
    serialized = mac.serialize()
    restored = Macaroon.deserialize(serialized)
    assert restored is not None
    assert restored.identifier == "test-id"
    assert restored.signature == "test-sig"


def test_macaroon_deserialize_invalid():
    from timmy_serve.l402_proxy import Macaroon
    assert Macaroon.deserialize("garbage") is None
