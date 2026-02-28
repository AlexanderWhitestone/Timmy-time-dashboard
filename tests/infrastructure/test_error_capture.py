"""Tests for the error capture and bug report feedback loop."""

from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def _isolate_db(tmp_path, monkeypatch):
    """Point task_queue and event_log SQLite to a temp directory."""
    db = tmp_path / "swarm.db"
    monkeypatch.setattr("swarm.task_queue.models.DB_PATH", db)
    monkeypatch.setattr("swarm.event_log.DB_PATH", db)


@pytest.fixture(autouse=True)
def _clear_dedup():
    """Clear the dedup cache between tests."""
    from infrastructure.error_capture import _dedup_cache

    _dedup_cache.clear()
    yield
    _dedup_cache.clear()


def _raise_value_error():
    """Helper — always raises from the same file:line so hash is stable."""
    raise ValueError("test error")


def _raise_type_error():
    """Helper — always raises from the same file:line so hash is stable."""
    raise TypeError("type error")


class TestStackHash:
    def test_same_exception_deterministic(self):
        """Hash is deterministic for the same exception object."""
        from infrastructure.error_capture import _stack_hash

        try:
            _raise_value_error()
        except ValueError as exc:
            hash1 = _stack_hash(exc)
            hash2 = _stack_hash(exc)

        assert hash1 == hash2

    def test_different_exception_types_different_hash(self):
        from infrastructure.error_capture import _stack_hash

        try:
            _raise_value_error()
        except ValueError as exc1:
            hash1 = _stack_hash(exc1)

        try:
            _raise_type_error()
        except TypeError as exc2:
            hash2 = _stack_hash(exc2)

        assert hash1 != hash2

    def test_hash_is_16_chars(self):
        from infrastructure.error_capture import _stack_hash

        try:
            raise RuntimeError("hash length test")
        except RuntimeError as exc:
            h = _stack_hash(exc)

        assert len(h) == 16


class TestDeduplication:
    def test_first_error_not_duplicate(self):
        from infrastructure.error_capture import _is_duplicate

        assert _is_duplicate("test-hash-001") is False

    def test_same_hash_is_duplicate(self):
        from infrastructure.error_capture import _is_duplicate

        _is_duplicate("test-hash-002")  # First time
        assert _is_duplicate("test-hash-002") is True

    def test_different_hashes_not_duplicate(self):
        from infrastructure.error_capture import _is_duplicate

        _is_duplicate("hash-aaa")
        assert _is_duplicate("hash-bbb") is False


class TestCaptureError:
    def test_capture_creates_bug_report_task(self):
        from infrastructure.error_capture import capture_error

        try:
            raise RuntimeError("test capture error")
        except RuntimeError as exc:
            task_id = capture_error(exc, source="test_module")

        assert task_id is not None

        from swarm.task_queue.models import get_task

        task = get_task(task_id)
        assert task is not None
        assert task.task_type == "bug_report"
        assert "RuntimeError" in task.title
        assert task.created_by == "system"

    def test_capture_deduplicates(self):
        """Capturing the same exception twice suppresses the second report."""
        from infrastructure.error_capture import capture_error, _dedup_cache, _stack_hash

        try:
            _raise_value_error()
        except ValueError as exc:
            # Capture first time
            id1 = capture_error(exc, source="test")
            # Manually insert hash as if it was just seen (capture already did this)
            # Now capture again with the same exc object — should be deduped
            id2 = capture_error(exc, source="test")

        assert id1 is not None
        assert id2 is None  # Deduplicated

    def test_capture_disabled(self, monkeypatch):
        monkeypatch.setattr("config.settings.error_feedback_enabled", False)
        from infrastructure.error_capture import capture_error

        try:
            raise RuntimeError("disabled test")
        except RuntimeError as exc:
            result = capture_error(exc, source="test")

        assert result is None

    def test_capture_includes_context(self):
        from infrastructure.error_capture import capture_error

        try:
            raise IOError("context test")
        except IOError as exc:
            task_id = capture_error(
                exc, source="http", context={"path": "/api/test"}
            )

        from swarm.task_queue.models import get_task

        task = get_task(task_id)
        assert "/api/test" in task.description

    def test_capture_includes_stack_trace(self):
        from infrastructure.error_capture import capture_error

        try:
            raise KeyError("stack trace test")
        except KeyError as exc:
            task_id = capture_error(exc, source="test")

        from swarm.task_queue.models import get_task

        task = get_task(task_id)
        assert "Stack Trace" in task.description
        assert "KeyError" in task.description

    def test_bug_report_is_auto_approved(self):
        from infrastructure.error_capture import capture_error

        try:
            raise RuntimeError("auto-approve test")
        except RuntimeError as exc:
            task_id = capture_error(exc, source="test")

        from swarm.task_queue.models import get_task

        task = get_task(task_id)
        assert task.status.value == "approved"
