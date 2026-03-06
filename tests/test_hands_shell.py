"""Tests for the Shell Execution Hand.

Covers:
- Command validation (allow-list and block-list)
- Successful command execution
- Command failure (non-zero exit code)
- Timeout enforcement
- ShellResult dataclass defaults
- Status summary
"""

import asyncio

import pytest


# ---------------------------------------------------------------------------
# Command validation
# ---------------------------------------------------------------------------

def test_validate_allows_safe_commands():
    """Commands matching the allow-list should pass validation."""
    from infrastructure.hands.shell import ShellHand

    hand = ShellHand()
    assert hand._validate_command("make test") is None
    assert hand._validate_command("pytest -q") is None
    assert hand._validate_command("git status") is None
    assert hand._validate_command("python -c 'print(1)'") is None
    assert hand._validate_command("ls -la") is None


def test_validate_blocks_unknown_commands():
    """Commands not in the allow-list should be rejected."""
    from infrastructure.hands.shell import ShellHand

    hand = ShellHand()
    err = hand._validate_command("reboot")
    assert err is not None
    assert "not in allow-list" in err


def test_validate_blocks_dangerous_commands():
    """Explicitly dangerous commands should be blocked."""
    from infrastructure.hands.shell import ShellHand

    hand = ShellHand()
    err = hand._validate_command("rm -rf /")
    assert err is not None
    assert "blocked by safety filter" in err


def test_validate_empty_command():
    """Empty commands should be rejected."""
    from infrastructure.hands.shell import ShellHand

    hand = ShellHand()
    err = hand._validate_command("")
    assert err is not None


def test_validate_strips_path_prefix():
    """Command with a path prefix should still match allow-list."""
    from infrastructure.hands.shell import ShellHand

    hand = ShellHand()
    assert hand._validate_command("/usr/bin/python --version") is None
    assert hand._validate_command("/usr/local/bin/make test") is None


# ---------------------------------------------------------------------------
# Execution — success path
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_echo():
    """A simple echo command should succeed."""
    from infrastructure.hands.shell import ShellHand

    hand = ShellHand()
    result = await hand.run("echo hello world")
    assert result.success is True
    assert result.exit_code == 0
    assert "hello world" in result.stdout
    assert result.latency_ms > 0


@pytest.mark.asyncio
async def test_run_python_expression():
    """Running a python one-liner should succeed."""
    from infrastructure.hands.shell import ShellHand

    hand = ShellHand()
    result = await hand.run("python -c 'print(2 + 2)'")
    assert result.success is True
    assert "4" in result.stdout


# ---------------------------------------------------------------------------
# Execution — failure path
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_blocked_command():
    """Running a blocked command returns success=False without executing."""
    from infrastructure.hands.shell import ShellHand

    hand = ShellHand()
    result = await hand.run("shutdown now")
    assert result.success is False
    assert "not in allow-list" in result.error


@pytest.mark.asyncio
async def test_run_nonzero_exit():
    """A command that exits non-zero should return success=False."""
    from infrastructure.hands.shell import ShellHand

    hand = ShellHand()
    result = await hand.run("python -c 'import sys; sys.exit(1)'")
    assert result.success is False
    assert result.exit_code == 1


# ---------------------------------------------------------------------------
# Timeout
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_timeout():
    """A command exceeding timeout should be killed and return timed_out=True."""
    from unittest.mock import AsyncMock, MagicMock, patch

    from infrastructure.hands.shell import ShellHand

    hand = ShellHand()

    # Mock subprocess that never finishes until killed
    mock_proc = MagicMock()
    mock_proc.kill = MagicMock()
    mock_proc.wait = AsyncMock()
    mock_proc.returncode = -9

    async def slow_communicate():
        await asyncio.sleep(999)

    mock_proc.communicate = slow_communicate

    with patch("asyncio.create_subprocess_shell", return_value=mock_proc):
        result = await hand.run("python -c 'import time; time.sleep(30)'", timeout=1)

    assert result.success is False
    assert result.timed_out is True
    mock_proc.kill.assert_called_once()


# ---------------------------------------------------------------------------
# ShellResult dataclass
# ---------------------------------------------------------------------------

def test_shell_result_defaults():
    """ShellResult should have sensible defaults."""
    from infrastructure.hands.shell import ShellResult

    r = ShellResult(command="echo hi", success=True)
    assert r.exit_code == -1
    assert r.stdout == ""
    assert r.stderr == ""
    assert r.error == ""
    assert r.latency_ms == 0.0
    assert r.timed_out is False
    assert r.metadata == {}


# ---------------------------------------------------------------------------
# Status summary
# ---------------------------------------------------------------------------

def test_status_returns_summary():
    """status() should return a dict with enabled, working_dir, etc."""
    from infrastructure.hands.shell import ShellHand

    hand = ShellHand()
    s = hand.status()
    assert "enabled" in s
    assert "working_dir" in s
    assert "default_timeout" in s
    assert "allowed_prefixes" in s
    assert isinstance(s["allowed_prefixes"], list)
