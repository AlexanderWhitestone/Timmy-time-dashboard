"""Tests for swarm event logging system."""

import pytest
from datetime import datetime, timezone
from swarm.event_log import (
    EventType,
    log_event,
    get_event,
    list_events,
    get_task_events,
    get_agent_events,
    get_recent_events,
    get_event_summary,
    prune_events,
)


class TestEventLog:
    """Test suite for event logging functionality."""

    def test_log_simple_event(self):
        """Test logging a basic event."""
        event = log_event(
            event_type=EventType.SYSTEM_INFO,
            source="test",
            data={"message": "test event"},
        )
        
        assert event.event_type == EventType.SYSTEM_INFO
        assert event.source == "test"
        assert event.data is not None
        
        # Verify we can retrieve it
        retrieved = get_event(event.id)
        assert retrieved is not None
        assert retrieved.source == "test"
    
    def test_log_task_event(self):
        """Test logging a task lifecycle event."""
        task_id = "task-123"
        agent_id = "agent-456"
        
        event = log_event(
            event_type=EventType.TASK_ASSIGNED,
            source="coordinator",
            task_id=task_id,
            agent_id=agent_id,
            data={"bid_sats": 100},
        )
        
        assert event.task_id == task_id
        assert event.agent_id == agent_id
        
        # Verify filtering by task works
        task_events = get_task_events(task_id)
        assert len(task_events) >= 1
        assert any(e.id == event.id for e in task_events)
    
    def test_log_agent_event(self):
        """Test logging agent lifecycle events."""
        agent_id = "agent-test-001"
        
        event = log_event(
            event_type=EventType.AGENT_JOINED,
            source="coordinator",
            agent_id=agent_id,
            data={"persona_id": "forge"},
        )
        
        # Verify filtering by agent works
        agent_events = get_agent_events(agent_id)
        assert len(agent_events) >= 1
        assert any(e.id == event.id for e in agent_events)
    
    def test_list_events_filtering(self):
        """Test filtering events by type."""
        # Create events of different types
        log_event(EventType.TASK_CREATED, source="test")
        log_event(EventType.TASK_COMPLETED, source="test")
        log_event(EventType.SYSTEM_INFO, source="test")
        
        # Filter by type
        task_events = list_events(event_type=EventType.TASK_CREATED, limit=10)
        assert all(e.event_type == EventType.TASK_CREATED for e in task_events)
        
        # Filter by source
        source_events = list_events(source="test", limit=10)
        assert all(e.source == "test" for e in source_events)
    
    def test_get_recent_events(self):
        """Test retrieving recent events."""
        # Log an event
        log_event(EventType.SYSTEM_INFO, source="recent_test")
        
        # Get events from last minute
        recent = get_recent_events(minutes=1)
        assert any(e.source == "recent_test" for e in recent)
    
    def test_event_summary(self):
        """Test event summary statistics."""
        # Create some events
        log_event(EventType.TASK_CREATED, source="summary_test")
        log_event(EventType.TASK_CREATED, source="summary_test")
        log_event(EventType.TASK_COMPLETED, source="summary_test")
        
        # Get summary
        summary = get_event_summary(minutes=1)
        assert "task.created" in summary or "task.completed" in summary
    
    def test_prune_events(self):
        """Test pruning old events."""
        # This test just verifies the function doesn't error
        # (we don't want to delete real data in tests)
        count = prune_events(older_than_days=365)
        # Result depends on database state, just verify no exception
        assert isinstance(count, int)
    
    def test_event_data_serialization(self):
        """Test that complex data is properly serialized."""
        complex_data = {
            "nested": {"key": "value"},
            "list": [1, 2, 3],
            "number": 42.5,
        }
        
        event = log_event(
            EventType.TOOL_CALLED,
            source="test",
            data=complex_data,
        )
        
        retrieved = get_event(event.id)
        # Data should be stored as JSON string
        assert retrieved.data is not None


class TestEventTypes:
    """Test that all event types can be logged."""
    
    @pytest.mark.parametrize("event_type", [
        EventType.TASK_CREATED,
        EventType.TASK_BIDDING,
        EventType.TASK_ASSIGNED,
        EventType.TASK_STARTED,
        EventType.TASK_COMPLETED,
        EventType.TASK_FAILED,
        EventType.AGENT_JOINED,
        EventType.AGENT_LEFT,
        EventType.AGENT_STATUS_CHANGED,
        EventType.BID_SUBMITTED,
        EventType.AUCTION_CLOSED,
        EventType.TOOL_CALLED,
        EventType.TOOL_COMPLETED,
        EventType.TOOL_FAILED,
        EventType.SYSTEM_ERROR,
        EventType.SYSTEM_WARNING,
        EventType.SYSTEM_INFO,
    ])
    def test_all_event_types(self, event_type):
        """Verify all event types can be logged and retrieved."""
        event = log_event(
            event_type=event_type,
            source="type_test",
            data={"test": True},
        )
        
        retrieved = get_event(event.id)
        assert retrieved is not None
        assert retrieved.event_type == event_type
