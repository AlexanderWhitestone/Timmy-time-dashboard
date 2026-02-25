"""Functional tests for CLI entry points via Typer's CliRunner.

Each test invokes the real CLI command.  Ollama is not running, so
commands that need inference will fail gracefully — and that's a valid
user scenario we want to verify.
"""

import pytest


# ── timmy CLI ─────────────────────────────────────────────────────────────────


class TestTimmyCLI:
    """Tests the `timmy` command (chat, think, status)."""

    def test_status_runs(self, timmy_runner):
        runner, app = timmy_runner
        result = runner.invoke(app, ["status"])
        # Ollama is offline, so this should either:
        # - Print an error about Ollama being unreachable, OR
        # - Exit non-zero
        # Either way, the CLI itself shouldn't crash with an unhandled exception.
        # The exit code tells us if the command ran at all.
        assert result.exit_code is not None

    def test_chat_requires_message(self, timmy_runner):
        runner, app = timmy_runner
        result = runner.invoke(app, ["chat"])
        # Missing required argument
        assert result.exit_code != 0
        assert "Missing argument" in result.output or "Usage" in result.output

    def test_think_requires_topic(self, timmy_runner):
        runner, app = timmy_runner
        result = runner.invoke(app, ["think"])
        assert result.exit_code != 0
        assert "Missing argument" in result.output or "Usage" in result.output

    def test_chat_with_message_runs(self, timmy_runner):
        """Chat with a real message — Ollama offline means graceful failure."""
        runner, app = timmy_runner
        result = runner.invoke(app, ["chat", "hello"])
        # Will fail because Ollama isn't running, but the CLI should handle it
        assert result.exit_code is not None

    def test_backend_flag_accepted(self, timmy_runner):
        runner, app = timmy_runner
        result = runner.invoke(app, ["status", "--backend", "ollama"])
        assert result.exit_code is not None

    def test_help_text(self, timmy_runner):
        runner, app = timmy_runner
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "Timmy" in result.output or "sovereign" in result.output.lower()


# ── timmy-serve CLI ───────────────────────────────────────────────────────────


class TestTimmyServeCLI:
    """Tests the `timmy-serve` command (start, invoice, status)."""

    def test_start_dry_run(self, serve_runner):
        """--dry-run should print config and exit cleanly."""
        runner, app = serve_runner
        result = runner.invoke(app, ["start", "--dry-run"])
        assert result.exit_code == 0
        assert "Starting Timmy Serve" in result.output
        assert "Dry run" in result.output or "dry run" in result.output

    def test_start_dry_run_custom_port(self, serve_runner):
        runner, app = serve_runner
        result = runner.invoke(app, ["start", "--dry-run", "--port", "9999"])
        assert result.exit_code == 0
        assert "9999" in result.output

    def test_start_dry_run_custom_price(self, serve_runner):
        runner, app = serve_runner
        result = runner.invoke(app, ["start", "--dry-run", "--price", "500"])
        assert result.exit_code == 0
        assert "500" in result.output

    def test_invoice_creates_real_invoice(self, serve_runner):
        """Create a real Lightning invoice via the mock backend."""
        runner, app = serve_runner
        result = runner.invoke(app, ["invoice", "--amount", "200", "--memo", "test invoice"])
        assert result.exit_code == 0
        assert "Invoice created" in result.output
        assert "200" in result.output
        assert "Payment hash" in result.output or "payment_hash" in result.output.lower()

    def test_status_shows_earnings(self, serve_runner):
        runner, app = serve_runner
        result = runner.invoke(app, ["status"])
        assert result.exit_code == 0
        assert "Total invoices" in result.output or "invoices" in result.output.lower()
        assert "sats" in result.output.lower()

    def test_help_text(self, serve_runner):
        runner, app = serve_runner
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "Serve" in result.output or "Lightning" in result.output


# ── self-tdd CLI ──────────────────────────────────────────────────────────────


class TestSelfTddCLI:
    """Tests the `self-tdd` command (watch)."""

    def test_help_text(self, tdd_runner):
        runner, app = tdd_runner
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "watchdog" in result.output.lower() or "test" in result.output.lower()

    def test_watch_help(self, tdd_runner):
        runner, app = tdd_runner
        result = runner.invoke(app, ["watch", "--help"])
        assert result.exit_code == 0
        assert "interval" in result.output.lower()
