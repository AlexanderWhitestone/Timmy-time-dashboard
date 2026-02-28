"""Redis pub/sub messaging layer for swarm communication.

Provides a thin wrapper around Redis pub/sub so agents can broadcast
events (task posted, bid submitted, task assigned) and listen for them.

Falls back gracefully when Redis is unavailable — messages are logged
but not delivered, allowing the system to run without Redis for
development and testing.
"""

import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

# Channel names
CHANNEL_TASKS = "swarm:tasks"
CHANNEL_BIDS = "swarm:bids"
CHANNEL_EVENTS = "swarm:events"


@dataclass
class SwarmMessage:
    channel: str
    event: str
    data: dict
    timestamp: str

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, raw: str) -> "SwarmMessage":
        d = json.loads(raw)
        return cls(**d)


class SwarmComms:
    """Pub/sub messaging for the swarm.

    Uses Redis when available; falls back to an in-memory fanout for
    single-process development.
    """

    def __init__(self, redis_url: str = "redis://localhost:6379"):
        self._redis_url = redis_url
        self._redis = None
        self._pubsub = None
        self._listeners: dict[str, list[Callable]] = {}
        self._connected = False
        self._try_connect()

    def _try_connect(self) -> None:
        try:
            import redis
            self._redis = redis.from_url(
                self._redis_url,
                socket_connect_timeout=3,
                socket_timeout=3,
            )
            self._redis.ping()
            self._pubsub = self._redis.pubsub()
            self._connected = True
            logger.info("SwarmComms: connected to Redis at %s", self._redis_url)
        except Exception:
            self._connected = False
            logger.warning(
                "SwarmComms: Redis unavailable — using in-memory fallback"
            )

    @property
    def connected(self) -> bool:
        return self._connected

    def publish(self, channel: str, event: str, data: Optional[dict] = None) -> None:
        msg = SwarmMessage(
            channel=channel,
            event=event,
            data=data or {},
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        if self._connected and self._redis:
            try:
                self._redis.publish(channel, msg.to_json())
                return
            except Exception as exc:
                logger.error("SwarmComms: publish failed — %s", exc)

        # In-memory fallback: call local listeners directly
        for callback in self._listeners.get(channel, []):
            try:
                callback(msg)
            except Exception as exc:
                logger.error("SwarmComms: listener error — %s", exc)

    def subscribe(self, channel: str, callback: Callable[[SwarmMessage], Any]) -> None:
        self._listeners.setdefault(channel, []).append(callback)
        if self._connected and self._pubsub:
            try:
                self._pubsub.subscribe(**{channel: lambda msg: None})
            except Exception as exc:
                logger.error("SwarmComms: subscribe failed — %s", exc)

    def post_task(self, task_id: str, description: str) -> None:
        self.publish(CHANNEL_TASKS, "task_posted", {
            "task_id": task_id,
            "description": description,
        })

    def submit_bid(self, task_id: str, agent_id: str, bid_sats: int) -> None:
        self.publish(CHANNEL_BIDS, "bid_submitted", {
            "task_id": task_id,
            "agent_id": agent_id,
            "bid_sats": bid_sats,
        })

    def assign_task(self, task_id: str, agent_id: str) -> None:
        self.publish(CHANNEL_EVENTS, "task_assigned", {
            "task_id": task_id,
            "agent_id": agent_id,
        })

    def complete_task(self, task_id: str, agent_id: str, result: str) -> None:
        self.publish(CHANNEL_EVENTS, "task_completed", {
            "task_id": task_id,
            "agent_id": agent_id,
            "result": result,
        })
