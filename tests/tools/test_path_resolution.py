"""Tests for path resolution in file operations."""

import pytest
from pathlib import Path


def test_resolve_path_expands_tilde():
    """Path resolution should expand ~ to home directory."""
    from creative.tools.file_ops import _resolve_path

    result = _resolve_path("~/test")

    # Should expand to current user's home directory
    assert result.as_posix() == (Path.home() / "test").as_posix()


def test_resolve_path_relative_to_repo():
    """Relative paths should resolve to repo root."""
    from creative.tools.file_ops import _resolve_path

    result = _resolve_path("src/config.py")

    # In Docker the repo root is /app; locally it contains Timmy-time-dashboard
    assert result.name == "config.py"
    assert "src" in str(result)


def test_resolve_path_absolute():
    """Absolute paths should work as-is."""
    from creative.tools.file_ops import _resolve_path

    result = _resolve_path("/etc/hosts")

    assert result.name == "hosts"


def test_resolve_path_with_custom_base():
    """Custom base_dir should override repo root."""
    from creative.tools.file_ops import _resolve_path

    result = _resolve_path("test.py", base_dir="/tmp")

    # Handle macOS /private/tmp vs /tmp
    assert result.name == "test.py"
    assert "tmp" in result.as_posix()
