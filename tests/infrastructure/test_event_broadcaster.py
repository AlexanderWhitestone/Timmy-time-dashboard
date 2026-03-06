"""Tests for the event broadcaster (infrastructure.events.broadcaster)."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from dataclasses import dataclass
from enum import Enum

from infrastructure.events.broadcaster import (
    EventBroadcaster,
    event_broadcaster,
    get_event_icon,
    get_event_label,
    format_event_for_display,
    EVENT_ICONS,
    EVENT_LABELS,
)


# ── Fake EventLogEntry for testing ──────────────────────────────────────────

class FakeEventType(Enum):
    TASK_CREATED = "task.created"
    TASK_ASSIGNED = "task.assigned"
    BID_SUBMITTED = "bid.submitted"
    AGENT_JOINED = "agent.joined"
    SYSTEM_INFO = "system.info"


@dataclass
class FakeEventLogEntry:
    id: str = "evt-abc123"
    event_type: FakeEventType = FakeEventType.TASK_CREATED
    source: str = "test"
    task_id: str = "task-1"
    agent_id: str = "agent-1"
    timestamp: str = "2026-03-06T12:00:00Z"
    data: dict = None

    def __post_init__(self):
        if self.data is None:
            self.data = {}


class TestEventBroadcaster:
    """Test EventBroadcaster class."""

    def test_init(self):
        b = EventBroadcaster()
        assert b._ws_manager is None

    async def test_broadcast_no_ws_manager(self):
        b = EventBroadcaster()
        # _get_ws_manager returns None => returns 0
        count = await b.broadcast(FakeEventLogEntry())
        assert count == 0

    async def test_broadcast_with_ws_manager(self):
        b = EventBroadcaster()
        mock_ws = MagicMock()
        mock_ws.broadcast_json = AsyncMock(return_value=3)
        b._ws_manager = mock_ws

        event = FakeEventLogEntry()
        count = await b.broadcast(event)
        assert count == 3
        mock_ws.broadcast_json.assert_awaited_once()

        # Verify payload structure
        payload = mock_ws.broadcast_json.call_args[0][0]
        assert payload["type"] == "event"
        assert payload["payload"]["id"] == "evt-abc123"
        assert payload["payload"]["event_type"] == "task.created"

    async def test_broadcast_ws_error_returns_zero(self):
        b = EventBroadcaster()
        mock_ws = MagicMock()
        mock_ws.broadcast_json = AsyncMock(side_effect=RuntimeError("ws down"))
        b._ws_manager = mock_ws

        count = await b.broadcast(FakeEventLogEntry())
        assert count == 0

    def test_broadcast_sync_no_loop(self):
        """broadcast_sync should not crash when no event loop is running."""
        b = EventBroadcaster()
        # This should silently pass (no event loop)
        b.broadcast_sync(FakeEventLogEntry())


class TestEventIcons:
    """Test icon/label lookup functions."""

    def test_known_icon(self):
        assert get_event_icon("task.created") == "📝"
        assert get_event_icon("agent.joined") == "🟢"

    def test_unknown_icon_returns_bullet(self):
        assert get_event_icon("nonexistent") == "•"

    def test_known_label(self):
        assert get_event_label("task.created") == "New task"
        assert get_event_label("task.failed") == "Task failed"

    def test_unknown_label_returns_type(self):
        assert get_event_label("custom.event") == "custom.event"

    def test_all_icons_have_labels(self):
        """Every icon key should also have a label."""
        for key in EVENT_ICONS:
            assert key in EVENT_LABELS, f"Missing label for icon key: {key}"


class TestFormatEventForDisplay:
    """Test format_event_for_display helper."""

    def test_task_created_truncates_description(self):
        event = FakeEventLogEntry(
            event_type=FakeEventType.TASK_CREATED,
            data={"description": "A" * 100},
        )
        result = format_event_for_display(event)
        assert result["description"].endswith("...")
        assert len(result["description"]) <= 63

    def test_task_created_short_description(self):
        event = FakeEventLogEntry(
            event_type=FakeEventType.TASK_CREATED,
            data={"description": "Short task"},
        )
        result = format_event_for_display(event)
        assert result["description"] == "Short task"

    def test_task_assigned(self):
        event = FakeEventLogEntry(
            event_type=FakeEventType.TASK_ASSIGNED,
            agent_id="agent-12345678-long",
            data={"bid_sats": 500},
        )
        result = format_event_for_display(event)
        assert "agent-12" in result["description"]
        assert "500 sats" in result["description"]

    def test_bid_submitted(self):
        event = FakeEventLogEntry(
            event_type=FakeEventType.BID_SUBMITTED,
            data={"bid_sats": 250},
        )
        result = format_event_for_display(event)
        assert "250 sats" in result["description"]

    def test_agent_joined_with_persona(self):
        event = FakeEventLogEntry(
            event_type=FakeEventType.AGENT_JOINED,
            data={"persona_id": "forge"},
        )
        result = format_event_for_display(event)
        assert "forge" in result["description"]

    def test_agent_joined_no_persona(self):
        event = FakeEventLogEntry(
            event_type=FakeEventType.AGENT_JOINED,
            data={},
        )
        result = format_event_for_display(event)
        assert result["description"] == "New agent"

    def test_generic_event_with_message(self):
        event = FakeEventLogEntry(
            event_type=FakeEventType.SYSTEM_INFO,
            data={"message": "All systems go"},
        )
        result = format_event_for_display(event)
        assert result["description"] == "All systems go"

    def test_generic_event_no_data(self):
        event = FakeEventLogEntry(
            event_type=FakeEventType.SYSTEM_INFO,
            data={},
        )
        result = format_event_for_display(event)
        assert result["description"] == ""

    def test_output_structure(self):
        event = FakeEventLogEntry()
        result = format_event_for_display(event)
        assert "id" in result
        assert "icon" in result
        assert "label" in result
        assert "type" in result
        assert "source" in result
        assert "timestamp" in result
        assert "time_short" in result
        assert result["time_short"] == "12:00:00"
