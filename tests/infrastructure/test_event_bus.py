"""Tests for the async event bus (infrastructure.events.bus)."""

import asyncio
import pytest
from infrastructure.events.bus import EventBus, Event, emit, on, event_bus


class TestEvent:
    """Test Event dataclass."""

    def test_event_defaults(self):
        e = Event(type="test.event", source="unit_test")
        assert e.type == "test.event"
        assert e.source == "unit_test"
        assert e.data == {}
        assert e.timestamp  # auto-generated
        assert e.id.startswith("evt_")

    def test_event_custom_data(self):
        e = Event(type="a.b", source="s", data={"key": "val"}, id="custom-id")
        assert e.data == {"key": "val"}
        assert e.id == "custom-id"


class TestEventBus:
    """Test EventBus subscribe/publish/history."""

    def _fresh_bus(self) -> EventBus:
        return EventBus()

    # ── subscribe + publish ──────────────────────────────────────────────

    async def test_exact_match_subscribe(self):
        bus = self._fresh_bus()
        received = []

        @bus.subscribe("task.created")
        async def handler(event: Event):
            received.append(event)

        count = await bus.publish(Event(type="task.created", source="test"))
        assert count == 1
        assert len(received) == 1
        assert received[0].type == "task.created"

    async def test_wildcard_subscribe(self):
        bus = self._fresh_bus()
        received = []

        @bus.subscribe("agent.*")
        async def handler(event: Event):
            received.append(event)

        await bus.publish(Event(type="agent.joined", source="test"))
        await bus.publish(Event(type="agent.left", source="test"))
        await bus.publish(Event(type="task.created", source="test"))  # should NOT match

        assert len(received) == 2

    async def test_star_subscribes_to_all(self):
        bus = self._fresh_bus()
        received = []

        @bus.subscribe("*")
        async def handler(event: Event):
            received.append(event)

        await bus.publish(Event(type="anything.here", source="test"))
        await bus.publish(Event(type="x", source="test"))

        assert len(received) == 2

    async def test_no_subscribers_returns_zero(self):
        bus = self._fresh_bus()
        count = await bus.publish(Event(type="orphan.event", source="test"))
        assert count == 0

    async def test_multiple_handlers_same_pattern(self):
        bus = self._fresh_bus()
        calls = {"a": 0, "b": 0}

        @bus.subscribe("foo.bar")
        async def handler_a(event):
            calls["a"] += 1

        @bus.subscribe("foo.bar")
        async def handler_b(event):
            calls["b"] += 1

        await bus.publish(Event(type="foo.bar", source="test"))
        assert calls["a"] == 1
        assert calls["b"] == 1

    # ── unsubscribe ──────────────────────────────────────────────────────

    async def test_unsubscribe(self):
        bus = self._fresh_bus()
        received = []

        @bus.subscribe("x.y")
        async def handler(event):
            received.append(event)

        ok = bus.unsubscribe("x.y", handler)
        assert ok is True

        await bus.publish(Event(type="x.y", source="test"))
        assert len(received) == 0

    async def test_unsubscribe_nonexistent_pattern(self):
        bus = self._fresh_bus()

        async def dummy(event):
            pass

        assert bus.unsubscribe("nope", dummy) is False

    async def test_unsubscribe_wrong_handler(self):
        bus = self._fresh_bus()

        @bus.subscribe("a.b")
        async def handler_a(event):
            pass

        async def handler_b(event):
            pass

        assert bus.unsubscribe("a.b", handler_b) is False

    # ── error handling ───────────────────────────────────────────────────

    async def test_handler_error_does_not_break_other_handlers(self):
        bus = self._fresh_bus()
        received = []

        @bus.subscribe("err.test")
        async def bad_handler(event):
            raise ValueError("boom")

        @bus.subscribe("err.test")
        async def good_handler(event):
            received.append(event)

        count = await bus.publish(Event(type="err.test", source="test"))
        assert count == 2  # both were invoked
        assert len(received) == 1  # good_handler still ran

    # ── history ──────────────────────────────────────────────────────────

    async def test_history_stores_events(self):
        bus = self._fresh_bus()
        await bus.publish(Event(type="h.a", source="s"))
        await bus.publish(Event(type="h.b", source="s"))

        history = bus.get_history()
        assert len(history) == 2

    async def test_history_filter_by_type(self):
        bus = self._fresh_bus()
        await bus.publish(Event(type="h.a", source="s"))
        await bus.publish(Event(type="h.b", source="s"))

        assert len(bus.get_history(event_type="h.a")) == 1

    async def test_history_filter_by_source(self):
        bus = self._fresh_bus()
        await bus.publish(Event(type="h.a", source="x"))
        await bus.publish(Event(type="h.b", source="y"))

        assert len(bus.get_history(source="x")) == 1

    async def test_history_limit(self):
        bus = self._fresh_bus()
        for i in range(5):
            await bus.publish(Event(type="h.x", source="s"))

        assert len(bus.get_history(limit=3)) == 3

    async def test_history_max_cap(self):
        bus = self._fresh_bus()
        bus._max_history = 10
        for i in range(15):
            await bus.publish(Event(type="cap", source="s"))

        assert len(bus._history) == 10

    async def test_clear_history(self):
        bus = self._fresh_bus()
        await bus.publish(Event(type="x", source="s"))
        bus.clear_history()
        assert len(bus.get_history()) == 0

    # ── pattern matching ─────────────────────────────────────────────────

    def test_match_exact(self):
        bus = self._fresh_bus()
        assert bus._match_pattern("a.b.c", "a.b.c") is True
        assert bus._match_pattern("a.b.c", "a.b.d") is False

    def test_match_wildcard(self):
        bus = self._fresh_bus()
        assert bus._match_pattern("agent.joined", "agent.*") is True
        assert bus._match_pattern("agent.left", "agent.*") is True
        assert bus._match_pattern("task.created", "agent.*") is False

    def test_match_star(self):
        bus = self._fresh_bus()
        assert bus._match_pattern("anything", "*") is True


class TestConvenienceFunctions:
    """Test module-level emit() and on() helpers."""

    async def test_emit(self):
        # Clear singleton history first
        event_bus.clear_history()
        event_bus._subscribers.clear()

        received = []

        @on("conv.test")
        async def handler(event):
            received.append(event)

        count = await emit("conv.test", "unit", {"foo": "bar"})
        assert count == 1
        assert received[0].data == {"foo": "bar"}

        # Cleanup
        event_bus._subscribers.clear()
        event_bus.clear_history()
