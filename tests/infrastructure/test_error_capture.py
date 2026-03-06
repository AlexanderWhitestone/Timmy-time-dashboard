"""Tests for infrastructure.error_capture module."""

import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone

from infrastructure.error_capture import (
    _stack_hash,
    _is_duplicate,
    _get_git_context,
    capture_error,
    _dedup_cache,
)


def _make_exception():
    """Helper that always raises from the same line for stable hashing."""
    raise ValueError("test error")


class TestStackHash:
    """Test _stack_hash produces stable hashes."""

    def test_hash_is_deterministic_for_same_exception(self):
        """Same exception object always produces the same hash."""
        try:
            _make_exception()
        except ValueError as e:
            hash1 = _stack_hash(e)
            hash2 = _stack_hash(e)
        assert hash1 == hash2

    def test_different_exception_types_differ(self):
        try:
            raise ValueError("x")
        except ValueError as e1:
            hash1 = _stack_hash(e1)

        try:
            raise TypeError("x")
        except TypeError as e2:
            hash2 = _stack_hash(e2)

        assert hash1 != hash2

    def test_hash_is_hex_string(self):
        try:
            raise RuntimeError("test")
        except RuntimeError as e:
            h = _stack_hash(e)
        assert len(h) == 16
        assert all(c in "0123456789abcdef" for c in h)


class TestIsDuplicate:
    """Test deduplication logic."""

    def setup_method(self):
        _dedup_cache.clear()

    def test_first_occurrence_not_duplicate(self):
        assert _is_duplicate("hash_abc") is False

    def test_second_occurrence_is_duplicate(self):
        _is_duplicate("hash_dup")
        assert _is_duplicate("hash_dup") is True

    def test_different_hashes_not_duplicates(self):
        _is_duplicate("hash_1")
        assert _is_duplicate("hash_2") is False

    def teardown_method(self):
        _dedup_cache.clear()


class TestGetGitContext:
    """Test _get_git_context."""

    def test_returns_dict_with_branch_and_commit(self):
        """Git context always returns a dict with branch and commit keys."""
        ctx = _get_git_context()
        assert "branch" in ctx
        assert "commit" in ctx
        assert isinstance(ctx["branch"], str)
        assert isinstance(ctx["commit"], str)


class TestCaptureError:
    """Test the main capture_error function."""

    def setup_method(self):
        _dedup_cache.clear()

    def test_duplicate_returns_none(self):
        """Second call with same exception is deduplicated."""
        try:
            _make_exception()
        except ValueError as e:
            # First call
            capture_error(e, source="test")
            # Second call — same hash, within dedup window
            result = capture_error(e, source="test")
            assert result is None

    def test_capture_does_not_crash_on_missing_deps(self):
        """capture_error should never crash even if optional deps are missing."""
        _dedup_cache.clear()

        try:
            raise IOError("graceful test")
        except IOError as e:
            # Should not raise even though swarm/event_log don't exist
            capture_error(e, source="graceful")

    def test_capture_with_context_does_not_crash(self):
        """capture_error with context dict should not crash."""
        _dedup_cache.clear()

        try:
            raise RuntimeError("context test")
        except RuntimeError as e:
            capture_error(e, source="test_module", context={"path": "/api/foo"})

    def teardown_method(self):
        _dedup_cache.clear()
