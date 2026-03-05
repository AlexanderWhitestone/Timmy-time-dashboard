"""Tests for ws_manager/handler.py — WebSocket manager."""

import json

import pytest

from infrastructure.ws_manager.handler import WebSocketManager, WSEvent


def test_ws_event_to_json():
    event = WSEvent(event="test", data={"key": "val"}, timestamp="2026-01-01T00:00:00Z")
    j = json.loads(event.to_json())
    assert j["event"] == "test"
    assert j["data"]["key"] == "val"


def test_ws_manager_initial_state():
    mgr = WebSocketManager()
    assert mgr.connection_count == 0
    assert mgr.event_history == []


@pytest.mark.asyncio
async def test_ws_manager_event_history_limit():
    """History is trimmed to maxlen after broadcasts."""
    import collections
    mgr = WebSocketManager()
    mgr._event_history = collections.deque(maxlen=5)
    for i in range(10):
        await mgr.broadcast(f"e{i}", {})
    assert len(mgr.event_history) == 5
    assert mgr.event_history[0].event == "e5"
