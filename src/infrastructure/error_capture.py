"""Centralized error capture with automatic bug report creation.

Catches errors from anywhere in the system, deduplicates them, logs them
to the event log, and creates bug report tasks in the task queue.

Usage:
    from infrastructure.error_capture import capture_error

    try:
        risky_operation()
    except Exception as exc:
        capture_error(exc, source="my_module", context={"request": "/api/foo"})
"""

import hashlib
import logging
import traceback
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# In-memory dedup cache: hash -> last_seen timestamp
_dedup_cache: dict[str, datetime] = {}


def _stack_hash(exc: Exception) -> str:
    """Create a stable hash of the exception type + traceback locations.

    Only hashes the file/line/function info from the traceback, not
    variable values, so the same bug produces the same hash even if
    runtime data differs.
    """
    tb_lines = traceback.format_exception(type(exc), exc, exc.__traceback__)
    # Extract only "File ..., line ..., in ..." lines for stable hashing
    stable_parts = [type(exc).__name__]
    for line in tb_lines:
        stripped = line.strip()
        if stripped.startswith("File "):
            stable_parts.append(stripped)
    return hashlib.sha256("\n".join(stable_parts).encode()).hexdigest()[:16]


def _is_duplicate(error_hash: str) -> bool:
    """Check if this error was seen recently (within dedup window)."""
    from config import settings

    now = datetime.now(timezone.utc)
    window = timedelta(seconds=settings.error_dedup_window_seconds)

    if error_hash in _dedup_cache:
        last_seen = _dedup_cache[error_hash]
        if now - last_seen < window:
            return True

    _dedup_cache[error_hash] = now

    # Prune old entries
    cutoff = now - window * 2
    expired = [k for k, v in _dedup_cache.items() if v < cutoff]
    for k in expired:
        del _dedup_cache[k]

    return False


def _get_git_context() -> dict:
    """Get current git branch and commit for the bug report."""
    try:
        import subprocess

        from config import settings

        branch = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=settings.repo_root,
        ).stdout.strip()

        commit = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=settings.repo_root,
        ).stdout.strip()

        return {"branch": branch, "commit": commit}
    except Exception:
        return {"branch": "unknown", "commit": "unknown"}


def capture_error(
    exc: Exception,
    source: str = "unknown",
    context: Optional[dict] = None,
) -> Optional[str]:
    """Capture an error and optionally create a bug report.

    Args:
        exc: The exception to capture
        source: Module/component where the error occurred
        context: Optional dict of extra context (request path, etc.)

    Returns:
        Task ID of the created bug report, or None if deduplicated/disabled
    """
    from config import settings

    if not settings.error_feedback_enabled:
        return None

    error_hash = _stack_hash(exc)

    if _is_duplicate(error_hash):
        logger.debug("Duplicate error suppressed: %s (hash=%s)", exc, error_hash)
        return None

    # Format the stack trace
    tb_str = "".join(
        traceback.format_exception(type(exc), exc, exc.__traceback__)
    )

    # Extract file/line from traceback
    tb_obj = exc.__traceback__
    affected_file = "unknown"
    affected_line = 0
    while tb_obj and tb_obj.tb_next:
        tb_obj = tb_obj.tb_next
    if tb_obj:
        affected_file = tb_obj.tb_frame.f_code.co_filename
        affected_line = tb_obj.tb_lineno

    git_ctx = _get_git_context()

    # 1. Log to event_log
    try:
        from swarm.event_log import EventType, log_event

        log_event(
            EventType.ERROR_CAPTURED,
            source=source,
            data={
                "error_type": type(exc).__name__,
                "message": str(exc)[:500],
                "hash": error_hash,
                "file": affected_file,
                "line": affected_line,
                "git_branch": git_ctx.get("branch", ""),
                "git_commit": git_ctx.get("commit", ""),
            },
        )
    except Exception as log_exc:
        logger.debug("Failed to log error event: %s", log_exc)

    # 2. Create bug report task
    task_id = None
    try:
        from swarm.task_queue.models import create_task

        title = f"[BUG] {type(exc).__name__}: {str(exc)[:80]}"

        description_parts = [
            f"**Error:** {type(exc).__name__}: {str(exc)}",
            f"**Source:** {source}",
            f"**File:** {affected_file}:{affected_line}",
            f"**Git:** {git_ctx.get('branch', '?')} @ {git_ctx.get('commit', '?')}",
            f"**Time:** {datetime.now(timezone.utc).isoformat()}",
            f"**Hash:** {error_hash}",
        ]

        if context:
            ctx_str = ", ".join(f"{k}={v}" for k, v in context.items())
            description_parts.append(f"**Context:** {ctx_str}")

        description_parts.append(f"\n**Stack Trace:**\n```\n{tb_str[:2000]}\n```")

        task = create_task(
            title=title,
            description="\n".join(description_parts),
            assigned_to="default",
            created_by="system",
            priority="normal",
            requires_approval=False,
            auto_approve=True,
            task_type="bug_report",
        )
        task_id = task.id

        # Log the creation event
        try:
            from swarm.event_log import EventType, log_event

            log_event(
                EventType.BUG_REPORT_CREATED,
                source=source,
                task_id=task_id,
                data={
                    "error_hash": error_hash,
                    "title": title[:100],
                },
            )
        except Exception:
            pass

    except Exception as task_exc:
        logger.debug("Failed to create bug report task: %s", task_exc)

    # 3. Send notification
    try:
        from infrastructure.notifications.push import notifier

        notifier.notify(
            title="Bug Report Filed",
            message=f"{type(exc).__name__} in {source}: {str(exc)[:80]}",
            category="system",
        )
    except Exception:
        pass

    # 4. Record in session logger
    try:
        from timmy.session_logger import get_session_logger

        session_logger = get_session_logger()
        session_logger.record_error(
            error=f"{type(exc).__name__}: {str(exc)}",
            context=source,
        )
    except Exception:
        pass

    return task_id
