"""Event Broadcaster - bridges event_log to WebSocket clients.

When events are logged, they are broadcast to all connected dashboard clients
via WebSocket for real-time activity feed updates.
"""

import asyncio
import json
import logging
from typing import Optional

from swarm.event_log import EventLogEntry

logger = logging.getLogger(__name__)


class EventBroadcaster:
    """Broadcasts events to WebSocket clients.
    
    Usage:
        from infrastructure.events.broadcaster import event_broadcaster
        event_broadcaster.broadcast(event)
    """
    
    def __init__(self) -> None:
        self._ws_manager: Optional = None
    
    def _get_ws_manager(self):
        """Lazy import to avoid circular deps."""
        if self._ws_manager is None:
            try:
                from infrastructure.ws_manager.handler import ws_manager
                self._ws_manager = ws_manager
            except Exception as exc:
                logger.debug("WebSocket manager not available: %s", exc)
        return self._ws_manager
    
    async def broadcast(self, event: EventLogEntry) -> int:
        """Broadcast an event to all connected WebSocket clients.
        
        Args:
            event: The event to broadcast
            
        Returns:
            Number of clients notified
        """
        ws_manager = self._get_ws_manager()
        if not ws_manager:
            return 0
        
        # Build message payload
        payload = {
            "type": "event",
            "payload": {
                "id": event.id,
                "event_type": event.event_type.value,
                "source": event.source,
                "task_id": event.task_id,
                "agent_id": event.agent_id,
                "timestamp": event.timestamp,
                "data": event.data,
            }
        }
        
        try:
            # Broadcast to all connected clients
            count = await ws_manager.broadcast_json(payload)
            logger.debug("Broadcasted event %s to %d clients", event.id[:8], count)
            return count
        except Exception as exc:
            logger.error("Failed to broadcast event: %s", exc)
            return 0
    
    def broadcast_sync(self, event: EventLogEntry) -> None:
        """Synchronous wrapper for broadcast.
        
        Use this from synchronous code - it schedules the async broadcast
        in the event loop if one is running.
        """
        try:
            loop = asyncio.get_running_loop()
            # Schedule in background, don't wait
            asyncio.create_task(self.broadcast(event))
        except RuntimeError:
            # No event loop running, skip broadcast
            pass


# Global singleton
event_broadcaster = EventBroadcaster()


# Event type to icon/emoji mapping
EVENT_ICONS = {
    "task.created": "📝",
    "task.bidding": "⏳",
    "task.assigned": "👤",
    "task.started": "▶️",
    "task.completed": "✅",
    "task.failed": "❌",
    "agent.joined": "🟢",
    "agent.left": "🔴",
    "agent.status_changed": "🔄",
    "bid.submitted": "💰",
    "auction.closed": "🏁",
    "tool.called": "🔧",
    "tool.completed": "⚙️",
    "tool.failed": "💥",
    "system.error": "⚠️",
    "system.warning": "🔶",
    "system.info": "ℹ️",
    "error.captured": "🐛",
    "bug_report.created": "📋",
}

EVENT_LABELS = {
    "task.created": "New task",
    "task.bidding": "Bidding open",
    "task.assigned": "Task assigned",
    "task.started": "Task started",
    "task.completed": "Task completed",
    "task.failed": "Task failed",
    "agent.joined": "Agent joined",
    "agent.left": "Agent left",
    "agent.status_changed": "Status changed",
    "bid.submitted": "Bid submitted",
    "auction.closed": "Auction closed",
    "tool.called": "Tool called",
    "tool.completed": "Tool completed",
    "tool.failed": "Tool failed",
    "system.error": "Error",
    "system.warning": "Warning",
    "system.info": "Info",
    "error.captured": "Error captured",
    "bug_report.created": "Bug report filed",
}


def get_event_icon(event_type: str) -> str:
    """Get emoji icon for event type."""
    return EVENT_ICONS.get(event_type, "•")


def get_event_label(event_type: str) -> str:
    """Get human-readable label for event type."""
    return EVENT_LABELS.get(event_type, event_type)


def format_event_for_display(event: EventLogEntry) -> dict:
    """Format event for display in activity feed.
    
    Returns dict with display-friendly fields.
    """
    data = event.data or {}
    
    # Build description based on event type
    description = ""
    if event.event_type.value == "task.created":
        desc = data.get("description", "")
        description = desc[:60] + "..." if len(desc) > 60 else desc
    elif event.event_type.value == "task.assigned":
        agent = event.agent_id[:8] if event.agent_id else "unknown"
        bid = data.get("bid_sats", "?")
        description = f"to {agent} ({bid} sats)"
    elif event.event_type.value == "bid.submitted":
        bid = data.get("bid_sats", "?")
        description = f"{bid} sats"
    elif event.event_type.value == "agent.joined":
        persona = data.get("persona_id", "")
        description = f"Persona: {persona}" if persona else "New agent"
    else:
        # Generic: use any string data
        for key in ["message", "reason", "description"]:
            if key in data:
                val = str(data[key])
                description = val[:60] + "..." if len(val) > 60 else val
                break
    
    return {
        "id": event.id,
        "icon": get_event_icon(event.event_type.value),
        "label": get_event_label(event.event_type.value),
        "type": event.event_type.value,
        "source": event.source,
        "description": description,
        "timestamp": event.timestamp,
        "time_short": event.timestamp[11:19] if event.timestamp else "",
        "task_id": event.task_id,
        "agent_id": event.agent_id,
    }
