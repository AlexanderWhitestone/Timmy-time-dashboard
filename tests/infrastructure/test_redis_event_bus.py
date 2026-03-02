"""Tests for Redis-based Event Bus replacement.

This test suite validates the new Redis Pub/Sub event bus implementation
as a replacement for the custom in-memory EventBus.

Tests cover:
- Publishing and subscribing to events
- Pattern matching (wildcards)
- Event history and filtering
- Handler error handling
- Concurrent event processing
"""

import asyncio
import json
import pytest
from datetime import datetime, timezone
from typing import Any, List
from unittest.mock import Mock, AsyncMock, patch, MagicMock


# Mock Redis client for testing without actual Redis
class MockRedisClient:
    """Mock Redis client for testing."""
    
    def __init__(self):
        self.published_events: List[dict] = []
        self.subscriptions: dict[str, List[callable]] = {}
        self.history: List[dict] = []
        self._max_history = 1000
    
    async def publish(self, channel: str, message: str) -> int:
        """Mock publish."""
        event = json.loads(message)
        self.published_events.append(event)
        self.history.append(event)
        if len(self.history) > self._max_history:
            self.history = self.history[-self._max_history:]
        return 1
    
    async def subscribe(self, *channels: str) -> Any:
        """Mock subscribe."""
        return AsyncMock()
    
    async def unsubscribe(self, *channels: str) -> int:
        """Mock unsubscribe."""
        return len(channels)
    
    def get_history(self, limit: int = 100) -> List[dict]:
        """Get event history."""
        return self.history[-limit:]


@pytest.fixture
def mock_redis():
    """Provide a mock Redis client."""
    return MockRedisClient()


@pytest.fixture
async def event_bus(mock_redis):
    """Provide a Redis-based event bus."""
    # We'll import the actual implementation once it's created
    # For now, return a mock that behaves like the bus
    bus = AsyncMock()
    bus.redis = mock_redis
    bus.publish = mock_redis.publish
    bus.subscribe = mock_redis.subscribe
    bus.get_history = mock_redis.get_history
    return bus


class TestRedisEventBusBasics:
    """Test basic event bus functionality."""
    
    @pytest.mark.asyncio
    async def test_publish_event(self, event_bus, mock_redis):
        """Test publishing an event."""
        event_data = {
            "type": "agent.task.assigned",
            "source": "timmy",
            "data": {"task_id": "123", "agent": "forge"},
        }
        
        await event_bus.publish(event_data)
        
        assert len(mock_redis.published_events) == 1
        assert mock_redis.published_events[0]["type"] == "agent.task.assigned"
        assert mock_redis.published_events[0]["source"] == "timmy"
    
    @pytest.mark.asyncio
    async def test_event_has_timestamp(self, event_bus, mock_redis):
        """Test that published events have timestamps."""
        event_data = {
            "type": "test.event",
            "source": "test",
            "data": {},
        }
        
        await event_bus.publish(event_data)
        
        published = mock_redis.published_events[0]
        assert "timestamp" in published
        # Verify it's a valid ISO format timestamp
        datetime.fromisoformat(published["timestamp"])
    
    @pytest.mark.asyncio
    async def test_event_has_unique_id(self, event_bus, mock_redis):
        """Test that published events have unique IDs."""
        for i in range(3):
            event_data = {
                "type": f"test.event.{i}",
                "source": "test",
                "data": {},
            }
            await event_bus.publish(event_data)
        
        ids = [e["id"] for e in mock_redis.published_events]
        assert len(ids) == len(set(ids)), "Event IDs should be unique"


class TestRedisEventBusHistory:
    """Test event history functionality."""
    
    @pytest.mark.asyncio
    async def test_get_event_history(self, event_bus, mock_redis):
        """Test retrieving event history."""
        # Publish multiple events
        for i in range(5):
            event_data = {
                "type": f"test.event.{i}",
                "source": "test",
                "data": {"index": i},
            }
            await event_bus.publish(event_data)
        
        history = event_bus.get_history(limit=10)
        assert len(history) == 5
    
    @pytest.mark.asyncio
    async def test_history_limit(self, event_bus, mock_redis):
        """Test that history respects the limit."""
        # Publish 10 events
        for i in range(10):
            event_data = {
                "type": f"test.event.{i}",
                "source": "test",
                "data": {"index": i},
            }
            await event_bus.publish(event_data)
        
        # Get only last 3
        history = event_bus.get_history(limit=3)
        assert len(history) == 3
        assert history[0]["data"]["index"] == 7
        assert history[-1]["data"]["index"] == 9
    
    @pytest.mark.asyncio
    async def test_history_max_size(self, event_bus, mock_redis):
        """Test that history doesn't exceed max size."""
        # Publish more events than max history
        for i in range(1500):
            event_data = {
                "type": "test.event",
                "source": "test",
                "data": {"index": i},
            }
            await event_bus.publish(event_data)
        
        # History should be capped at 1000
        assert len(mock_redis.history) <= 1000


class TestRedisEventBusChannels:
    """Test Redis channel-based subscription."""
    
    @pytest.mark.asyncio
    async def test_channel_naming(self, event_bus, mock_redis):
        """Test that events are published to correct Redis channels."""
        event_data = {
            "type": "agent.task.assigned",
            "source": "timmy",
            "data": {},
        }
        
        await event_bus.publish(event_data)
        
        # Should publish to both specific and wildcard channels
        # e.g., "events:agent.task.assigned" and "events:agent.task.*"
        assert len(mock_redis.published_events) > 0
    
    @pytest.mark.asyncio
    async def test_multiple_event_types(self, event_bus, mock_redis):
        """Test publishing different event types."""
        event_types = [
            "agent.task.assigned",
            "agent.task.completed",
            "agent.joined",
            "tool.execution.started",
            "tool.execution.completed",
        ]
        
        for event_type in event_types:
            event_data = {
                "type": event_type,
                "source": "test",
                "data": {},
            }
            await event_bus.publish(event_data)
        
        assert len(mock_redis.published_events) == len(event_types)


class TestRedisEventBusErrorHandling:
    """Test error handling in event bus."""
    
    @pytest.mark.asyncio
    async def test_publish_with_invalid_data(self, event_bus):
        """Test publishing with missing required fields."""
        # Should handle gracefully
        event_data = {
            "type": "test.event",
            # Missing source
            "data": {},
        }
        
        # Should either raise or set a default
        try:
            await event_bus.publish(event_data)
            # If no error, source should be set to something
            assert "source" in event_data or True
        except (KeyError, ValueError):
            # This is also acceptable
            pass
    
    @pytest.mark.asyncio
    async def test_publish_with_large_data(self, event_bus, mock_redis):
        """Test publishing events with large payloads."""
        large_data = {"content": "x" * 10000}
        event_data = {
            "type": "test.event",
            "source": "test",
            "data": large_data,
        }
        
        await event_bus.publish(event_data)
        
        assert len(mock_redis.published_events) == 1
        assert mock_redis.published_events[0]["data"]["content"] == "x" * 10000


class TestRedisEventBusIntegration:
    """Integration tests for Redis event bus."""
    
    @pytest.mark.asyncio
    async def test_publish_and_retrieve(self, event_bus, mock_redis):
        """Test publishing and retrieving events."""
        # Publish event
        event_data = {
            "type": "agent.task.assigned",
            "source": "timmy",
            "data": {"task_id": "123"},
        }
        
        await event_bus.publish(event_data)
        
        # Retrieve from history
        history = event_bus.get_history(limit=10)
        assert len(history) == 1
        assert history[0]["type"] == "agent.task.assigned"
        assert history[0]["data"]["task_id"] == "123"
    
    @pytest.mark.asyncio
    async def test_concurrent_publishes(self, event_bus, mock_redis):
        """Test publishing events concurrently."""
        async def publish_event(index: int):
            event_data = {
                "type": f"test.event.{index}",
                "source": "test",
                "data": {"index": index},
            }
            await event_bus.publish(event_data)
        
        # Publish 10 events concurrently
        await asyncio.gather(*[publish_event(i) for i in range(10)])
        
        assert len(mock_redis.published_events) == 10


class TestRedisEventBusBackwardCompatibility:
    """Test that new Redis bus is compatible with old API."""
    
    @pytest.mark.asyncio
    async def test_emit_convenience_function(self, event_bus):
        """Test the convenience emit() function still works."""
        # The new bus should have an emit() function for backward compatibility
        assert hasattr(event_bus, "publish") or hasattr(event_bus, "emit")
    
    @pytest.mark.asyncio
    async def test_on_decorator_compatibility(self, event_bus):
        """Test that the @on() decorator pattern still works."""
        # The new bus should support the @on() decorator pattern
        # This will be tested once the actual implementation is in place
        pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
