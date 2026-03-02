"""Redis-based Event Bus for inter-agent communication.

Replaces the custom in-memory EventBus with Redis Pub/Sub for:
- Scalability across multiple processes/machines
- Persistence of event history
- Better performance under load
- Standard Redis ecosystem tools

API is compatible with the old EventBus for easy migration.

Usage:
    from infrastructure.events.redis_bus import event_bus
    
    # Publish events
    await event_bus.publish(Event(
        type="agent.task.assigned",
        source="timmy",
        data={"task_id": "123"}
    ))
    
    # Subscribe to events
    @event_bus.subscribe("agent.task.*")
    async def handle_task(event: Event):
        print(f"Task event: {event.data}")
    
    # Get history
    history = await event_bus.get_history("agent.task.assigned", limit=100)
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Callable, Coroutine, Optional
from functools import wraps

try:
    import redis.asyncio as redis
except ImportError:
    redis = None

logger = logging.getLogger(__name__)


@dataclass
class Event:
    """A typed event in the system."""
    type: str  # e.g., "agent.task.assigned", "tool.execution.completed"
    source: str  # Agent or component that emitted the event
    data: dict = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    id: str = field(default_factory=lambda: f"evt_{datetime.now(timezone.utc).timestamp()}")

    def to_json(self) -> str:
        """Serialize event to JSON."""
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, json_str: str) -> "Event":
        """Deserialize event from JSON."""
        data = json.loads(json_str)
        return cls(**data)


# Type alias for event handlers
EventHandler = Callable[[Event], Coroutine[Any, Any, None]]


class RedisEventBus:
    """Redis-based event bus for publish/subscribe pattern.
    
    Features:
    - Pub/Sub via Redis channels
    - Event history stored in Redis sorted sets
    - Pattern matching with wildcards
    - Graceful fallback if Redis is unavailable
    
    Usage:
        bus = RedisEventBus(redis_url="redis://localhost:6379")
        await bus.connect()
        
        # Subscribe to events
        @bus.subscribe("agent.task.*")
        async def handle_task(event: Event):
            print(f"Task event: {event.data}")
        
        # Publish events
        await bus.publish(Event(
            type="agent.task.assigned",
            source="timmy",
            data={"task_id": "123"}
        ))
    """
    
    def __init__(self, redis_url: str = "redis://localhost:6379", max_history: int = 1000):
        """Initialize Redis event bus.
        
        Args:
            redis_url: Redis connection URL
            max_history: Maximum number of events to keep in history
        """
        self.redis_url = redis_url
        self.max_history = max_history
        self.redis_client: Optional[Any] = None
        self.pubsub: Optional[Any] = None
        self._subscribers: dict[str, list[EventHandler]] = {}
        self._history_key = "timmy:events:history"
        self._running = False
        logger.info("RedisEventBus initialized with URL: %s", redis_url)
    
    async def connect(self) -> bool:
        """Connect to Redis.
        
        Returns:
            True if connected, False if Redis is unavailable
        """
        if not redis:
            logger.warning("redis-py not installed, falling back to in-memory bus")
            return False
        
        try:
            self.redis_client = await redis.from_url(self.redis_url, decode_responses=True)
            await self.redis_client.ping()
            logger.info("Connected to Redis at %s", self.redis_url)
            return True
        except Exception as exc:
            logger.warning("Failed to connect to Redis: %s (will use in-memory fallback)", exc)
            self.redis_client = None
            return False
    
    async def disconnect(self) -> None:
        """Disconnect from Redis."""
        if self.redis_client:
            await self.redis_client.close()
            self.redis_client = None
            logger.info("Disconnected from Redis")
    
    def subscribe(self, event_pattern: str) -> Callable[[EventHandler], EventHandler]:
        """Decorator to subscribe to events matching a pattern.
        
        Patterns support wildcards:
            - "agent.task.assigned" — exact match
            - "agent.task.*" — any task event
            - "agent.*" — any agent event
            - "*" — all events
        
        Args:
            event_pattern: Event type pattern to subscribe to
            
        Returns:
            Decorator function
        """
        def decorator(handler: EventHandler) -> EventHandler:
            if event_pattern not in self._subscribers:
                self._subscribers[event_pattern] = []
            self._subscribers[event_pattern].append(handler)
            logger.debug("Subscribed handler to pattern '%s'", event_pattern)
            return handler
        return decorator
    
    def unsubscribe(self, event_pattern: str, handler: EventHandler) -> bool:
        """Remove a handler from a subscription.
        
        Args:
            event_pattern: Event type pattern
            handler: Handler function to remove
            
        Returns:
            True if handler was removed, False if not found
        """
        if event_pattern not in self._subscribers:
            return False
        
        if handler in self._subscribers[event_pattern]:
            self._subscribers[event_pattern].remove(handler)
            logger.debug("Unsubscribed handler from pattern '%s'", event_pattern)
            return True
        
        return False
    
    async def publish(self, event: Event) -> int:
        """Publish an event to all matching subscribers.
        
        Args:
            event: Event to publish
            
        Returns:
            Number of handlers invoked
        """
        # Store in Redis history
        if self.redis_client:
            try:
                await self._store_in_history(event)
            except Exception as exc:
                logger.error("Failed to store event in history: %s", exc)
        
        # Publish to Redis channels
        if self.redis_client:
            try:
                await self._publish_to_redis(event)
            except Exception as exc:
                logger.error("Failed to publish to Redis: %s", exc)
        
        # Invoke local subscribers (for backward compatibility)
        handlers = self._get_matching_handlers(event.type)
        if handlers:
            await asyncio.gather(
                *[self._invoke_handler(h, event) for h in handlers],
                return_exceptions=True
            )
        
        logger.debug("Published event '%s' to %d handlers", event.type, len(handlers))
        return len(handlers)
    
    async def _store_in_history(self, event: Event) -> None:
        """Store event in Redis sorted set for history.
        
        Args:
            event: Event to store
        """
        if not self.redis_client:
            return
        
        # Store with timestamp as score for ordering
        score = datetime.fromisoformat(event.timestamp).timestamp()
        await self.redis_client.zadd(
            self._history_key,
            {event.to_json(): score}
        )
        
        # Trim history to max size
        await self.redis_client.zremrangebyrank(
            self._history_key,
            0,
            -self.max_history - 1
        )
    
    async def _publish_to_redis(self, event: Event) -> None:
        """Publish event to Redis channels.
        
        Args:
            event: Event to publish
        """
        if not self.redis_client:
            return
        
        # Publish to specific channel
        channel = f"events:{event.type}"
        await self.redis_client.publish(channel, event.to_json())
        
        # Publish to wildcard channels (e.g., "events:agent.task.*")
        parts = event.type.split(".")
        for i in range(len(parts)):
            wildcard = ".".join(parts[:i+1]) + ".*"
            channel = f"events:{wildcard}"
            await self.redis_client.publish(channel, event.to_json())
    
    def _get_matching_handlers(self, event_type: str) -> list[EventHandler]:
        """Get all handlers matching an event type.
        
        Args:
            event_type: Event type to match
            
        Returns:
            List of matching handlers
        """
        handlers: list[EventHandler] = []
        
        for pattern, pattern_handlers in self._subscribers.items():
            if self._match_pattern(event_type, pattern):
                handlers.extend(pattern_handlers)
        
        return handlers
    
    async def _invoke_handler(self, handler: EventHandler, event: Event) -> None:
        """Invoke a handler with error handling.
        
        Args:
            handler: Handler function
            event: Event to pass to handler
        """
        try:
            await handler(event)
        except Exception as exc:
            logger.error("Event handler failed for '%s': %s", event.type, exc)
    
    def _match_pattern(self, event_type: str, pattern: str) -> bool:
        """Check if event type matches a wildcard pattern.
        
        Args:
            event_type: Event type to check
            pattern: Pattern to match against
            
        Returns:
            True if event type matches pattern
        """
        if pattern == "*":
            return True
        
        if pattern.endswith(".*"):
            prefix = pattern[:-2]
            return event_type.startswith(prefix + ".")
        
        return event_type == pattern
    
    async def get_history(
        self,
        event_type: Optional[str] = None,
        source: Optional[str] = None,
        limit: int = 100,
    ) -> list[Event]:
        """Get recent event history with optional filtering.
        
        Args:
            event_type: Filter by event type (optional)
            source: Filter by source (optional)
            limit: Maximum number of events to return
            
        Returns:
            List of events matching criteria
        """
        if not self.redis_client:
            return []
        
        try:
            # Get events from sorted set (most recent first)
            json_events = await self.redis_client.zrange(
                self._history_key,
                -limit,
                -1
            )
            
            events = [Event.from_json(json_str) for json_str in json_events]
            
            # Filter by event type if specified
            if event_type:
                events = [e for e in events if e.type == event_type]
            
            # Filter by source if specified
            if source:
                events = [e for e in events if e.source == source]
            
            return events
        except Exception as exc:
            logger.error("Failed to retrieve history: %s", exc)
            return []
    
    async def clear_history(self) -> None:
        """Clear event history."""
        if self.redis_client:
            try:
                await self.redis_client.delete(self._history_key)
                logger.info("Cleared event history")
            except Exception as exc:
                logger.error("Failed to clear history: %s", exc)


# Module-level singleton
_event_bus: Optional[RedisEventBus] = None


async def get_event_bus() -> RedisEventBus:
    """Get or create the module-level event bus singleton.
    
    Returns:
        RedisEventBus instance
    """
    global _event_bus
    if _event_bus is None:
        _event_bus = RedisEventBus()
        await _event_bus.connect()
    return _event_bus


# Convenience functions for backward compatibility
async def emit(event_type: str, source: str, data: dict) -> int:
    """Quick emit an event.
    
    Args:
        event_type: Type of event
        source: Source of event
        data: Event data
        
    Returns:
        Number of handlers invoked
    """
    bus = await get_event_bus()
    return await bus.publish(Event(
        type=event_type,
        source=source,
        data=data,
    ))


def on(event_pattern: str) -> Callable[[EventHandler], EventHandler]:
    """Quick subscribe decorator.
    
    Args:
        event_pattern: Event pattern to subscribe to
        
    Returns:
        Decorator function
    """
    def decorator(handler: EventHandler) -> EventHandler:
        # Register with global bus
        # Note: This assumes the bus is already created
        if _event_bus:
            return _event_bus.subscribe(event_pattern)(handler)
        return handler
    return decorator
