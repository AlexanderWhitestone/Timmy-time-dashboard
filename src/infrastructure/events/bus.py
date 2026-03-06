"""Async Event Bus for inter-agent communication.

Agents publish and subscribe to events for loose coupling.
Events are typed and carry structured data.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Coroutine

logger = logging.getLogger(__name__)


@dataclass
class Event:
    """A typed event in the system."""
    type: str  # e.g., "agent.task.assigned", "tool.execution.completed"
    source: str  # Agent or component that emitted the event
    data: dict = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    id: str = field(default_factory=lambda: f"evt_{datetime.now(timezone.utc).timestamp()}")


# Type alias for event handlers
EventHandler = Callable[[Event], Coroutine[Any, Any, None]]


class EventBus:
    """Async event bus for publish/subscribe pattern.
    
    Usage:
        bus = EventBus()
        
        # Subscribe to events
        @bus.subscribe("agent.task.*")
        async def handle_task(event: Event):
            print(f"Task event: {event.data}")
        
        # Publish events
        await bus.publish(Event(
            type="agent.task.assigned",
            source="default",
            data={"task_id": "123", "agent": "forge"}
        ))
    """
    
    def __init__(self) -> None:
        self._subscribers: dict[str, list[EventHandler]] = {}
        self._history: list[Event] = []
        self._max_history = 1000
        logger.info("EventBus initialized")
    
    def subscribe(self, event_pattern: str) -> Callable[[EventHandler], EventHandler]:
        """Decorator to subscribe to events matching a pattern.
        
        Patterns support wildcards:
            - "agent.task.assigned" — exact match
            - "agent.task.*" — any task event
            - "agent.*" — any agent event
            - "*" — all events
        """
        def decorator(handler: EventHandler) -> EventHandler:
            if event_pattern not in self._subscribers:
                self._subscribers[event_pattern] = []
            self._subscribers[event_pattern].append(handler)
            logger.debug("Subscribed handler to '%s'", event_pattern)
            return handler
        return decorator
    
    def unsubscribe(self, event_pattern: str, handler: EventHandler) -> bool:
        """Remove a handler from a subscription."""
        if event_pattern not in self._subscribers:
            return False
        
        if handler in self._subscribers[event_pattern]:
            self._subscribers[event_pattern].remove(handler)
            logger.debug("Unsubscribed handler from '%s'", event_pattern)
            return True
        
        return False
    
    async def publish(self, event: Event) -> int:
        """Publish an event to all matching subscribers.
        
        Returns:
            Number of handlers invoked
        """
        # Store in history
        self._history.append(event)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]
        
        # Find matching handlers
        handlers: list[EventHandler] = []
        
        for pattern, pattern_handlers in self._subscribers.items():
            if self._match_pattern(event.type, pattern):
                handlers.extend(pattern_handlers)
        
        # Invoke handlers concurrently
        if handlers:
            await asyncio.gather(
                *[self._invoke_handler(h, event) for h in handlers],
                return_exceptions=True
            )
        
        logger.debug("Published event '%s' to %d handlers", event.type, len(handlers))
        return len(handlers)
    
    async def _invoke_handler(self, handler: EventHandler, event: Event) -> None:
        """Invoke a handler with error handling."""
        try:
            await handler(event)
        except Exception as exc:
            logger.error("Event handler failed for '%s': %s", event.type, exc)
    
    def _match_pattern(self, event_type: str, pattern: str) -> bool:
        """Check if event type matches a wildcard pattern."""
        if pattern == "*":
            return True
        
        if pattern.endswith(".*"):
            prefix = pattern[:-2]
            return event_type.startswith(prefix + ".")
        
        return event_type == pattern
    
    def get_history(
        self,
        event_type: str | None = None,
        source: str | None = None,
        limit: int = 100,
    ) -> list[Event]:
        """Get recent event history with optional filtering."""
        events = self._history
        
        if event_type:
            events = [e for e in events if e.type == event_type]
        
        if source:
            events = [e for e in events if e.source == source]
        
        return events[-limit:]
    
    def clear_history(self) -> None:
        """Clear event history."""
        self._history.clear()


# Module-level singleton
event_bus = EventBus()


# Convenience functions
async def emit(event_type: str, source: str, data: dict) -> int:
    """Quick emit an event."""
    return await event_bus.publish(Event(
        type=event_type,
        source=source,
        data=data,
    ))


def on(event_pattern: str) -> Callable[[EventHandler], EventHandler]:
    """Quick subscribe decorator."""
    return event_bus.subscribe(event_pattern)
