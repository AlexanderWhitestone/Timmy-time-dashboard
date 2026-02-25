"""WebSocket manager for the live swarm dashboard.

Manages WebSocket connections and broadcasts swarm events to all
connected clients in real time.  Used by the /swarm/live route
to provide a live feed of agent activity, task auctions, and
system events.
"""

import asyncio
import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


@dataclass
class WSEvent:
    """A WebSocket event to broadcast to connected clients."""
    event: str
    data: dict
    timestamp: str

    def to_json(self) -> str:
        return json.dumps(asdict(self))


class WebSocketManager:
    """Manages WebSocket connections and event broadcasting."""

    def __init__(self) -> None:
        self._connections: list[WebSocket] = []
        self._event_history: list[WSEvent] = []
        self._max_history = 100

    async def connect(self, websocket: WebSocket) -> None:
        """Accept a new WebSocket connection."""
        await websocket.accept()
        self._connections.append(websocket)
        logger.info(
            "WebSocket connected — %d active connections",
            len(self._connections),
        )
        # Send recent history to the new client
        for event in self._event_history[-20:]:
            try:
                await websocket.send_text(event.to_json())
            except Exception:
                break

    def disconnect(self, websocket: WebSocket) -> None:
        """Remove a disconnected WebSocket."""
        if websocket in self._connections:
            self._connections.remove(websocket)
        logger.info(
            "WebSocket disconnected — %d active connections",
            len(self._connections),
        )

    async def broadcast(self, event: str, data: dict | None = None) -> None:
        """Broadcast an event to all connected WebSocket clients."""
        ws_event = WSEvent(
            event=event,
            data=data or {},
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        self._event_history.append(ws_event)
        if len(self._event_history) > self._max_history:
            self._event_history = self._event_history[-self._max_history:]

        message = ws_event.to_json()
        disconnected = []

        for ws in self._connections:
            try:
                await ws.send_text(message)
            except Exception:
                disconnected.append(ws)

        # Clean up dead connections
        for ws in disconnected:
            self.disconnect(ws)

    async def broadcast_agent_joined(self, agent_id: str, name: str) -> None:
        await self.broadcast("agent_joined", {"agent_id": agent_id, "name": name})

    async def broadcast_agent_left(self, agent_id: str, name: str) -> None:
        await self.broadcast("agent_left", {"agent_id": agent_id, "name": name})

    async def broadcast_task_posted(self, task_id: str, description: str) -> None:
        await self.broadcast("task_posted", {
            "task_id": task_id, "description": description,
        })

    async def broadcast_bid_submitted(
        self, task_id: str, agent_id: str, bid_sats: int
    ) -> None:
        await self.broadcast("bid_submitted", {
            "task_id": task_id, "agent_id": agent_id, "bid_sats": bid_sats,
        })

    async def broadcast_task_assigned(self, task_id: str, agent_id: str) -> None:
        await self.broadcast("task_assigned", {
            "task_id": task_id, "agent_id": agent_id,
        })

    async def broadcast_task_completed(
        self, task_id: str, agent_id: str, result: str
    ) -> None:
        await self.broadcast("task_completed", {
            "task_id": task_id, "agent_id": agent_id, "result": result[:200],
        })

    @property
    def connection_count(self) -> int:
        return len(self._connections)

    @property
    def event_history(self) -> list[WSEvent]:
        return list(self._event_history)


# Module-level singleton
ws_manager = WebSocketManager()
