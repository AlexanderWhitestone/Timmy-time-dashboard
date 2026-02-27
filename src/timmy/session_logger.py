"""Session logging for Timmy - captures interactions, errors, and decisions.

Timmy requested: "I'd love to see a detailed log of all my interactions,
including any mistakes or errors that occur during the session."
"""

import json
import logging
from datetime import datetime, date
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class SessionLogger:
    """Logs Timmy's interactions to a session file."""

    def __init__(self, logs_dir: str | Path | None = None):
        """Initialize session logger.

        Args:
            logs_dir: Directory for log files. Defaults to /logs in repo root.
        """
        from config import settings

        if logs_dir is None:
            self.logs_dir = Path(settings.repo_root) / "logs"
        else:
            self.logs_dir = Path(logs_dir)

        # Create logs directory if it doesn't exist
        self.logs_dir.mkdir(parents=True, exist_ok=True)

        # Session file path
        self.session_file = self.logs_dir / f"session_{date.today().isoformat()}.jsonl"

        # In-memory buffer
        self._buffer: list[dict] = []

    def record_message(self, role: str, content: str) -> None:
        """Record a user message.

        Args:
            role: "user" or "timmy"
            content: The message content
        """
        self._buffer.append(
            {
                "type": "message",
                "role": role,
                "content": content,
                "timestamp": datetime.now().isoformat(),
            }
        )

    def record_tool_call(self, tool_name: str, args: dict, result: str) -> None:
        """Record a tool call.

        Args:
            tool_name: Name of the tool called
            args: Arguments passed to the tool
            result: Result from the tool
        """
        # Truncate long results
        result_preview = result[:500] if isinstance(result, str) else str(result)[:500]

        self._buffer.append(
            {
                "type": "tool_call",
                "tool": tool_name,
                "args": args,
                "result": result_preview,
                "timestamp": datetime.now().isoformat(),
            }
        )

    def record_error(self, error: str, context: str | None = None) -> None:
        """Record an error.

        Args:
            error: Error message
            context: Optional context about what was happening
        """
        self._buffer.append(
            {
                "type": "error",
                "error": error,
                "context": context,
                "timestamp": datetime.now().isoformat(),
            }
        )

    def record_decision(self, decision: str, rationale: str | None = None) -> None:
        """Record a decision Timmy made.

        Args:
            decision: What was decided
            rationale: Why that decision was made
        """
        self._buffer.append(
            {
                "type": "decision",
                "decision": decision,
                "rationale": rationale,
                "timestamp": datetime.now().isoformat(),
            }
        )

    def flush(self) -> Path:
        """Flush buffer to disk.

        Returns:
            Path to the session file
        """
        if not self._buffer:
            return self.session_file

        with open(self.session_file, "a") as f:
            for entry in self._buffer:
                f.write(json.dumps(entry) + "\n")

        logger.info("Flushed %d entries to %s", len(self._buffer), self.session_file)
        self._buffer.clear()

        return self.session_file

    def get_session_summary(self) -> dict[str, Any]:
        """Get a summary of the current session.

        Returns:
            Dict with session statistics
        """
        if not self.session_file.exists():
            return {
                "exists": False,
                "entries": 0,
            }

        entries = []
        with open(self.session_file) as f:
            for line in f:
                if line.strip():
                    entries.append(json.loads(line))

        return {
            "exists": True,
            "file": str(self.session_file),
            "entries": len(entries),
            "messages": sum(1 for e in entries if e.get("type") == "message"),
            "tool_calls": sum(1 for e in entries if e.get("type") == "tool_call"),
            "errors": sum(1 for e in entries if e.get("type") == "error"),
            "decisions": sum(1 for e in entries if e.get("type") == "decision"),
        }


# Global session logger instance
_session_logger: SessionLogger | None = None


def get_session_logger() -> SessionLogger:
    """Get or create the global session logger."""
    global _session_logger
    if _session_logger is None:
        _session_logger = SessionLogger()
    return _session_logger


def get_session_summary() -> dict[str, Any]:
    """Get summary of current session logs.

    Returns:
        Dict with session statistics (entries, messages, errors, etc.)
    """
    logger = get_session_logger()
    return logger.get_session_summary()


def flush_session_logs() -> str:
    """Flush current session logs to disk.

    Returns:
        Path to the log file
    """
    logger = get_session_logger()
    path = logger.flush()
    return str(path)
