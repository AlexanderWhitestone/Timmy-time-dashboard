"""Tests for timmy_serve/cli.py — Serve-mode CLI commands."""

from typer.testing import CliRunner

from timmy_serve.cli import app

runner = CliRunner()


class TestStartCommand:
    def test_start_default_port(self):
        result = runner.invoke(app, ["start", "--dry-run"])
        assert result.exit_code == 0
        assert "8402" in result.output
        assert "L402 payment proxy active" in result.output

    def test_start_custom_port(self):
        result = runner.invoke(app, ["start", "--port", "9000", "--dry-run"])
        assert result.exit_code == 0
        assert "9000" in result.output

    def test_start_custom_host(self):
        result = runner.invoke(app, ["start", "--host", "127.0.0.1", "--dry-run"])
        assert result.exit_code == 0
        assert "127.0.0.1" in result.output

    def test_start_shows_endpoints(self):
        result = runner.invoke(app, ["start", "--dry-run"])
        assert "/serve/chat" in result.output
        assert "/serve/invoice" in result.output
        assert "/serve/status" in result.output

    def test_start_custom_price(self):
        result = runner.invoke(app, ["start", "--price", "50", "--dry-run"])
        assert result.exit_code == 0
        assert "50 sats" in result.output


class TestInvoiceCommand:
    def test_invoice_default_amount(self):
        result = runner.invoke(app, ["invoice"])
        assert result.exit_code == 0
        assert "100 sats" in result.output
        assert "API access" in result.output

    def test_invoice_custom_amount(self):
        result = runner.invoke(app, ["invoice", "--amount", "500"])
        assert result.exit_code == 0
        assert "500 sats" in result.output

    def test_invoice_custom_memo(self):
        result = runner.invoke(app, ["invoice", "--memo", "Test payment"])
        assert result.exit_code == 0
        assert "Test payment" in result.output

    def test_invoice_shows_payment_hash(self):
        result = runner.invoke(app, ["invoice"])
        assert "Payment hash:" in result.output
        assert "Pay request:" in result.output


class TestStatusCommand:
    def test_status_runs_successfully(self):
        result = runner.invoke(app, ["status"])
        assert result.exit_code == 0
        assert "Timmy Serve" in result.output
        assert "Total invoices:" in result.output
        assert "Settled:" in result.output
        assert "Total earned:" in result.output
        assert "sats" in result.output
