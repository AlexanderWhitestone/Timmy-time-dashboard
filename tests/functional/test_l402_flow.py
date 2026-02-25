"""Functional test for the full L402 payment flow.

Uses the real mock-lightning backend (LIGHTNING_BACKEND=mock) — no patching.
This exercises the entire payment lifecycle a real client would go through:

1. Hit protected endpoint → get 402 + invoice + macaroon
2. "Pay" the invoice (settle via mock backend)
3. Present macaroon:preimage → get access
"""

import pytest


class TestL402PaymentFlow:
    """End-to-end L402 payment lifecycle."""

    def test_unprotected_endpoints_work(self, serve_client):
        """Status and health don't require payment."""
        resp = serve_client.get("/serve/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "active"
        assert data["price_sats"] == 100

        health = serve_client.get("/health")
        assert health.status_code == 200

    def test_chat_without_payment_returns_402(self, serve_client):
        """Hitting /serve/chat without an L402 token gives 402."""
        resp = serve_client.post(
            "/serve/chat",
            json={"message": "hello"},
        )
        assert resp.status_code == 402
        data = resp.json()
        assert data["error"] == "Payment Required"
        assert data["code"] == "L402"
        assert "macaroon" in data
        assert "invoice" in data
        assert "payment_hash" in data
        assert data["amount_sats"] == 100

        # WWW-Authenticate header should be present
        assert "WWW-Authenticate" in resp.headers
        assert "L402" in resp.headers["WWW-Authenticate"]

    def test_chat_with_garbage_token_returns_402(self, serve_client):
        resp = serve_client.post(
            "/serve/chat",
            json={"message": "hello"},
            headers={"Authorization": "L402 garbage:token"},
        )
        assert resp.status_code == 402

    def test_full_payment_lifecycle(self, serve_client):
        """Complete flow: get challenge → pay → access."""
        from timmy_serve.payment_handler import payment_handler

        # Step 1: Hit protected endpoint, get 402 challenge
        challenge_resp = serve_client.post(
            "/serve/chat",
            json={"message": "hello"},
        )
        assert challenge_resp.status_code == 402
        challenge = challenge_resp.json()
        macaroon = challenge["macaroon"]
        payment_hash = challenge["payment_hash"]

        # Step 2: "Pay" the invoice via the mock backend's auto-settle
        # The mock backend settles invoices when you provide the correct preimage.
        # Get the preimage from the mock backend's internal state.
        invoice = payment_handler.get_invoice(payment_hash)
        assert invoice is not None
        preimage = invoice.preimage  # mock backend exposes this

        # Step 3: Present macaroon:preimage to access the endpoint
        resp = serve_client.post(
            "/serve/chat",
            json={"message": "hello after paying"},
            headers={"Authorization": f"L402 {macaroon}:{preimage}"},
        )
        # The chat will fail because Ollama isn't running, but the
        # L402 middleware should let us through (status != 402).
        # We accept 200 (success) or 500 (Ollama offline) — NOT 402.
        assert resp.status_code != 402

    def test_create_invoice_via_api(self, serve_client):
        """POST /serve/invoice creates a real invoice."""
        resp = serve_client.post(
            "/serve/invoice",
            json={"amount_sats": 500, "memo": "premium access"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["amount_sats"] == 500
        assert data["payment_hash"]
        assert data["payment_request"]

    def test_status_reflects_invoices(self, serve_client):
        """Creating invoices should be reflected in /serve/status."""
        serve_client.post("/serve/invoice", json={"amount_sats": 100, "memo": "test"})
        serve_client.post("/serve/invoice", json={"amount_sats": 200, "memo": "test2"})

        resp = serve_client.get("/serve/status")
        data = resp.json()
        assert data["total_invoices"] >= 2
