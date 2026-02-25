"""Swarm WebSocket route — /swarm/live endpoint.

Provides a real-time WebSocket feed of swarm events for the live
dashboard view.  Clients connect and receive JSON events as they
happen: agent joins, task posts, bids, assignments, completions.
"""

import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ws_manager.handler import ws_manager

logger = logging.getLogger(__name__)

router = APIRouter(tags=["swarm-ws"])


@router.websocket("/swarm/live")
async def swarm_live(websocket: WebSocket):
    """WebSocket endpoint for live swarm event streaming."""
    await ws_manager.connect(websocket)
    try:
        while True:
            # Keep the connection alive; client can also send commands
            data = await websocket.receive_text()
            # Echo back as acknowledgment (future: handle client commands)
            logger.debug("WS received: %s", data[:100])
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception as exc:
        logger.error("WebSocket error: %s", exc)
        ws_manager.disconnect(websocket)
