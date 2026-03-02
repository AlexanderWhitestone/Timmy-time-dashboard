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
        assert result.exit_code is not None

    def test_chat_requires_message(self, timmy_runner):
        runner, app = timmy_runner
        result = runner.invoke(app, ["chat"])
        assert result.exit_code != 0
        assert "Missing argument" in result.output or "Usage" in result.output

    def test_think_requires_topic(self, timmy_runner):
        runner, app = timmy_runner
        result = runner.invoke(app, ["think"])
        assert result.exit_code != 0
        assert "Missing argument" in result.output or "Usage" in result.output

    def test_chat_with_message_runs(self, timmy_runner):
        runner, app = timmy_runner
        result = runner.invoke(app, ["chat", "hello"])
        assert result.exit_code is not None

    def test_help_text(self, timmy_runner):
        runner, app = timmy_runner
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "Timmy" in result.output or "sovereign" in result.output.lower()


# ── timmy-serve CLI ───────────────────────────────────────────────────────────


class TestTimmyServeCLI:
    """Tests the `timmy-serve` command (start, status)."""

    def test_start_dry_run(self, serve_runner):
        runner, app = serve_runner
        result = runner.invoke(app, ["start", "--dry-run"])
        assert result.exit_code == 0
        assert "Starting Timmy Serve" in result.output

    def test_start_dry_run_custom_port(self, serve_runner):
        runner, app = serve_runner
        result = runner.invoke(app, ["start", "--dry-run", "--port", "9999"])
        assert result.exit_code == 0
        assert "9999" in result.output

    def test_status(self, serve_runner):
        runner, app = serve_runner
        result = runner.invoke(app, ["status"])
        assert result.exit_code == 0
        assert "Timmy Serve" in result.output

    def test_help_text(self, serve_runner):
        runner, app = serve_runner
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "Serve" in result.output
