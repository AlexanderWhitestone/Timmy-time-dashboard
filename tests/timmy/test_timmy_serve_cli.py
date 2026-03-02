"""Tests for timmy_serve/cli.py — Serve-mode CLI commands."""

from typer.testing import CliRunner

from timmy_serve.cli import app

runner = CliRunner()


class TestStartCommand:
    def test_start_default_port(self):
        result = runner.invoke(app, ["start", "--dry-run"])
        assert result.exit_code == 0
        assert "8402" in result.output

    def test_start_custom_port(self):
        result = runner.invoke(app, ["start", "--port", "9000", "--dry-run"])
        assert result.exit_code == 0
        assert "9000" in result.output

    def test_start_custom_host(self):
        result = runner.invoke(app, ["start", "--host", "127.0.0.1", "--dry-run"])
        assert result.exit_code == 0
        assert "127.0.0.1" in result.output


class TestStatusCommand:
    def test_status_runs_successfully(self):
        result = runner.invoke(app, ["status"])
        assert result.exit_code == 0
        assert "Timmy Serve" in result.output
