"""Tests for session logging."""

import pytest
import tempfile
import json
from pathlib import Path


def test_session_logger_records_message():
    """Should record a user message."""
    from timmy.session_logger import SessionLogger

    with tempfile.TemporaryDirectory() as tmpdir:
        logger = SessionLogger(logs_dir=tmpdir)

        logger.record_message("user", "Hello Timmy")
        logger.record_message("timmy", "Hello user")

        log_file = logger.flush()

        assert log_file.exists()
        content = log_file.read_text()
        assert "Hello Timmy" in content
        assert "message" in content


def test_session_logger_records_tool_call():
    """Should record a tool call."""
    from timmy.session_logger import SessionLogger

    with tempfile.TemporaryDirectory() as tmpdir:
        logger = SessionLogger(logs_dir=tmpdir)

        logger.record_tool_call("read_file", {"path": "test.py"}, "file content")

        log_file = logger.flush()

        assert log_file.exists()
        content = log_file.read_text()
        assert "read_file" in content
        assert "tool_call" in content


def test_session_logger_records_error():
    """Should record an error."""
    from timmy.session_logger import SessionLogger

    with tempfile.TemporaryDirectory() as tmpdir:
        logger = SessionLogger(logs_dir=tmpdir)

        logger.record_error("File not found", "Reading config")

        log_file = logger.flush()

        assert log_file.exists()
        content = log_file.read_text()
        assert "File not found" in content
        assert "error" in content


def test_session_logger_records_decision():
    """Should record a decision."""
    from timmy.session_logger import SessionLogger

    with tempfile.TemporaryDirectory() as tmpdir:
        logger = SessionLogger(logs_dir=tmpdir)

        logger.record_decision("Use OOP pattern", "More maintainable")

        log_file = logger.flush()

        assert log_file.exists()
        content = log_file.read_text()
        assert "Use OOP pattern" in content
        assert "decision" in content


def test_session_summary():
    """Should provide session summary."""
    from timmy.session_logger import SessionLogger

    with tempfile.TemporaryDirectory() as tmpdir:
        logger = SessionLogger(logs_dir=tmpdir)

        logger.record_message("user", "Hello")
        logger.record_message("timmy", "Hi")
        logger.record_error("Test error")

        # Flush to create the session file
        logger.flush()

        summary = logger.get_session_summary()

        assert summary["exists"] is True
        assert summary["entries"] >= 3
