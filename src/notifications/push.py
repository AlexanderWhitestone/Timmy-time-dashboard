"""Push notification system for swarm events.

Collects notifications from swarm events (task completed, agent joined,
auction won, etc.) and makes them available to the dashboard via polling
or WebSocket.  On macOS, can optionally trigger native notifications
via osascript.

No cloud push services — everything stays local.
"""

import logging
import subprocess
import platform
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class Notification:
    id: int
    title: str
    message: str
    category: str  # swarm | task | agent | system | payment
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    read: bool = False


class PushNotifier:
    """Local push notification manager."""

    def __init__(self, max_history: int = 200, native_enabled: bool = True) -> None:
        self._notifications: deque[Notification] = deque(maxlen=max_history)
        self._counter = 0
        self._native_enabled = native_enabled and platform.system() == "Darwin"
        self._listeners: list = []

    def notify(
        self,
        title: str,
        message: str,
        category: str = "system",
        native: bool = False,
    ) -> Notification:
        """Create and store a notification."""
        self._counter += 1
        notif = Notification(
            id=self._counter,
            title=title,
            message=message,
            category=category,
        )
        self._notifications.appendleft(notif)
        logger.info("Notification [%s]: %s — %s", category, title, message[:60])

        # Trigger native macOS notification if requested
        if native and self._native_enabled:
            self._native_notify(title, message)

        # Notify listeners (for WebSocket push)
        for listener in self._listeners:
            try:
                listener(notif)
            except Exception as exc:
                logger.error("Notification listener error: %s", exc)

        return notif

    def _native_notify(self, title: str, message: str) -> None:
        """Send a native macOS notification via osascript."""
        try:
            script = (
                f'display notification "{message}" '
                f'with title "Timmy Time" subtitle "{title}"'
            )
            subprocess.Popen(
                ["osascript", "-e", script],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception as exc:
            logger.debug("Native notification failed: %s", exc)

    def recent(self, limit: int = 20, category: Optional[str] = None) -> list[Notification]:
        """Get recent notifications, optionally filtered by category."""
        notifs = list(self._notifications)
        if category:
            notifs = [n for n in notifs if n.category == category]
        return notifs[:limit]

    def unread_count(self) -> int:
        return sum(1 for n in self._notifications if not n.read)

    def mark_read(self, notification_id: int) -> bool:
        for n in self._notifications:
            if n.id == notification_id:
                n.read = True
                return True
        return False

    def mark_all_read(self) -> int:
        count = 0
        for n in self._notifications:
            if not n.read:
                n.read = True
                count += 1
        return count

    def clear(self) -> None:
        self._notifications.clear()

    def add_listener(self, callback) -> None:
        """Register a callback for real-time notification delivery."""
        self._listeners.append(callback)


# Module-level singleton
notifier = PushNotifier()


async def notify_briefing_ready(briefing) -> None:
    """Placeholder: notify the owner that a new morning briefing is ready.

    Logs to console now.  Wire to real push (APNs/Pushover) later.

    Args:
        briefing: A timmy.briefing.Briefing instance.
    """
    n_approvals = len(briefing.approval_items) if briefing.approval_items else 0
    message = (
        f"Your morning briefing is ready. "
        f"{n_approvals} item(s) await your approval."
    )
    notifier.notify(
        title="Morning Briefing Ready",
        message=message,
        category="briefing",
        native=True,
    )
    logger.info("Briefing push notification dispatched (%d approval(s))", n_approvals)
