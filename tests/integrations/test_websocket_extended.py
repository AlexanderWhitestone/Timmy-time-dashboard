"""Extended tests for ws_manager/handler.py — broadcast, disconnect, convenience."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from infrastructure.ws_manager.handler import WebSocketManager, WSEvent


class TestWSEventSerialization:
    def test_to_json_roundtrip(self):
        event = WSEvent(event="task_posted", data={"id": "abc"}, timestamp="2026-01-01T00:00:00Z")
        raw = event.to_json()
        parsed = json.loads(raw)
        assert parsed["event"] == "task_posted"
        assert parsed["data"]["id"] == "abc"
        assert parsed["timestamp"] == "2026-01-01T00:00:00Z"

    def test_to_json_empty_data(self):
        event = WSEvent(event="ping", data={}, timestamp="t")
        parsed = json.loads(event.to_json())
        assert parsed["data"] == {}


class TestWebSocketManagerBroadcast:
    @pytest.mark.asyncio
    async def test_broadcast_sends_to_all_connections(self):
        mgr = WebSocketManager()
        ws1 = AsyncMock()
        ws2 = AsyncMock()
        mgr._connections = [ws1, ws2]

        await mgr.broadcast("test_event", {"key": "val"})

        ws1.send_text.assert_called_once()
        ws2.send_text.assert_called_once()
        # Both should receive the same message
        msg1 = json.loads(ws1.send_text.call_args[0][0])
        msg2 = json.loads(ws2.send_text.call_args[0][0])
        assert msg1["event"] == "test_event"
        assert msg2["event"] == "test_event"

    @pytest.mark.asyncio
    async def test_broadcast_removes_dead_connections(self):
        mgr = WebSocketManager()
        ws_alive = AsyncMock()
        ws_dead = AsyncMock()
        ws_dead.send_text.side_effect = RuntimeError("connection closed")
        mgr._connections = [ws_alive, ws_dead]

        await mgr.broadcast("ping", {})

        assert ws_dead not in mgr._connections
        assert ws_alive in mgr._connections

    @pytest.mark.asyncio
    async def test_broadcast_appends_to_history(self):
        mgr = WebSocketManager()
        await mgr.broadcast("evt1", {"a": 1})
        await mgr.broadcast("evt2", {"b": 2})

        assert len(mgr.event_history) == 2
        assert mgr.event_history[0].event == "evt1"
        assert mgr.event_history[1].event == "evt2"

    @pytest.mark.asyncio
    async def test_broadcast_trims_history(self):
        mgr = WebSocketManager()
        mgr._max_history = 3
        for i in range(5):
            await mgr.broadcast(f"e{i}", {})
        assert len(mgr.event_history) == 3
        assert mgr.event_history[0].event == "e2"


class TestWebSocketManagerConnect:
    @pytest.mark.asyncio
    async def test_connect_accepts_websocket(self):
        mgr = WebSocketManager()
        ws = AsyncMock()
        await mgr.connect(ws)
        ws.accept.assert_called_once()
        assert mgr.connection_count == 1

    @pytest.mark.asyncio
    async def test_connect_sends_recent_history(self):
        mgr = WebSocketManager()
        # Pre-populate history
        for i in range(3):
            mgr._event_history.append(
                WSEvent(event=f"e{i}", data={}, timestamp="t")
            )
        ws = AsyncMock()
        await mgr.connect(ws)
        # Should have sent 3 history events
        assert ws.send_text.call_count == 3


class TestWebSocketManagerDisconnect:
    def test_disconnect_removes_connection(self):
        mgr = WebSocketManager()
        ws = MagicMock()
        mgr._connections = [ws]
        mgr.disconnect(ws)
        assert mgr.connection_count == 0

    def test_disconnect_nonexistent_is_safe(self):
        mgr = WebSocketManager()
        ws = MagicMock()
        mgr.disconnect(ws)  # Should not raise
        assert mgr.connection_count == 0


class TestConvenienceBroadcasts:
    @pytest.mark.asyncio
    async def test_broadcast_agent_joined(self):
        mgr = WebSocketManager()
        ws = AsyncMock()
        mgr._connections = [ws]
        await mgr.broadcast_agent_joined("a1", "Echo")
        msg = json.loads(ws.send_text.call_args[0][0])
        assert msg["event"] == "agent_joined"
        assert msg["data"]["agent_id"] == "a1"
        assert msg["data"]["name"] == "Echo"

    @pytest.mark.asyncio
    async def test_broadcast_task_posted(self):
        mgr = WebSocketManager()
        ws = AsyncMock()
        mgr._connections = [ws]
        await mgr.broadcast_task_posted("t1", "Research BTC")
        msg = json.loads(ws.send_text.call_args[0][0])
        assert msg["event"] == "task_posted"
        assert msg["data"]["task_id"] == "t1"

    @pytest.mark.asyncio
    async def test_broadcast_bid_submitted(self):
        mgr = WebSocketManager()
        ws = AsyncMock()
        mgr._connections = [ws]
        await mgr.broadcast_bid_submitted("t1", "a1", 42)
        msg = json.loads(ws.send_text.call_args[0][0])
        assert msg["event"] == "bid_submitted"
        assert msg["data"]["bid_sats"] == 42

    @pytest.mark.asyncio
    async def test_broadcast_task_assigned(self):
        mgr = WebSocketManager()
        ws = AsyncMock()
        mgr._connections = [ws]
        await mgr.broadcast_task_assigned("t1", "a1")
        msg = json.loads(ws.send_text.call_args[0][0])
        assert msg["event"] == "task_assigned"

    @pytest.mark.asyncio
    async def test_broadcast_task_completed(self):
        mgr = WebSocketManager()
        ws = AsyncMock()
        mgr._connections = [ws]
        await mgr.broadcast_task_completed("t1", "a1", "Done!")
        msg = json.loads(ws.send_text.call_args[0][0])
        assert msg["event"] == "task_completed"
        assert msg["data"]["result"] == "Done!"

    @pytest.mark.asyncio
    async def test_broadcast_agent_left(self):
        mgr = WebSocketManager()
        ws = AsyncMock()
        mgr._connections = [ws]
        await mgr.broadcast_agent_left("a1", "Echo")
        msg = json.loads(ws.send_text.call_args[0][0])
        assert msg["event"] == "agent_left"
