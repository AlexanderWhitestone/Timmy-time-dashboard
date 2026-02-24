"""Spark Intelligence engine — the top-level API for Spark integration.

The engine is the single entry point used by the swarm coordinator and
dashboard routes.  It wires together memory capture, EIDOS predictions,
memory consolidation, and the advisory system.

Usage
-----
    from spark.engine import spark_engine

    # Capture a swarm event
    spark_engine.on_task_posted(task_id, description)
    spark_engine.on_bid_submitted(task_id, agent_id, bid_sats)
    spark_engine.on_task_completed(task_id, agent_id, result)
    spark_engine.on_task_failed(task_id, agent_id, reason)

    # Query Spark intelligence
    spark_engine.status()
    spark_engine.get_advisories()
    spark_engine.get_timeline()
"""

import json
import logging
from typing import Optional

from spark import advisor as spark_advisor
from spark import eidos as spark_eidos
from spark import memory as spark_memory
from spark.advisor import Advisory
from spark.memory import SparkEvent, SparkMemory

logger = logging.getLogger(__name__)


class SparkEngine:
    """Top-level Spark Intelligence controller."""

    def __init__(self, enabled: bool = True) -> None:
        self._enabled = enabled
        if enabled:
            logger.info("Spark Intelligence engine initialised")

    @property
    def enabled(self) -> bool:
        return self._enabled

    # ── Event capture (called by coordinator) ────────────────────────────────

    def on_task_posted(
        self,
        task_id: str,
        description: str,
        candidate_agents: Optional[list[str]] = None,
    ) -> Optional[str]:
        """Capture a task-posted event and generate a prediction."""
        if not self._enabled:
            return None

        event_id = spark_memory.record_event(
            event_type="task_posted",
            description=description,
            task_id=task_id,
            data=json.dumps({"candidates": candidate_agents or []}),
        )

        # Generate EIDOS prediction
        if candidate_agents:
            spark_eidos.predict_task_outcome(
                task_id=task_id,
                task_description=description,
                candidate_agents=candidate_agents,
            )

        logger.debug("Spark: captured task_posted %s", task_id[:8])
        return event_id

    def on_bid_submitted(
        self, task_id: str, agent_id: str, bid_sats: int,
    ) -> Optional[str]:
        """Capture a bid event."""
        if not self._enabled:
            return None

        event_id = spark_memory.record_event(
            event_type="bid_submitted",
            description=f"Agent {agent_id[:8]} bid {bid_sats} sats",
            agent_id=agent_id,
            task_id=task_id,
            data=json.dumps({"bid_sats": bid_sats}),
        )

        logger.debug("Spark: captured bid %s→%s (%d sats)",
                      agent_id[:8], task_id[:8], bid_sats)
        return event_id

    def on_task_assigned(
        self, task_id: str, agent_id: str,
    ) -> Optional[str]:
        """Capture a task-assigned event."""
        if not self._enabled:
            return None

        event_id = spark_memory.record_event(
            event_type="task_assigned",
            description=f"Task assigned to {agent_id[:8]}",
            agent_id=agent_id,
            task_id=task_id,
        )

        logger.debug("Spark: captured assignment %s→%s",
                      task_id[:8], agent_id[:8])
        return event_id

    def on_task_completed(
        self,
        task_id: str,
        agent_id: str,
        result: str,
        winning_bid: Optional[int] = None,
    ) -> Optional[str]:
        """Capture a task-completed event and evaluate EIDOS prediction."""
        if not self._enabled:
            return None

        event_id = spark_memory.record_event(
            event_type="task_completed",
            description=f"Task completed by {agent_id[:8]}",
            agent_id=agent_id,
            task_id=task_id,
            data=json.dumps({
                "result_length": len(result),
                "winning_bid": winning_bid,
            }),
        )

        # Evaluate EIDOS prediction
        evaluation = spark_eidos.evaluate_prediction(
            task_id=task_id,
            actual_winner=agent_id,
            task_succeeded=True,
            winning_bid=winning_bid,
        )
        if evaluation:
            accuracy = evaluation["accuracy"]
            spark_memory.record_event(
                event_type="prediction_result",
                description=f"Prediction accuracy: {accuracy:.0%}",
                task_id=task_id,
                data=json.dumps(evaluation, default=str),
                importance=0.7,
            )

        # Consolidate memory if enough events for this agent
        self._maybe_consolidate(agent_id)

        logger.debug("Spark: captured completion %s by %s",
                      task_id[:8], agent_id[:8])
        return event_id

    def on_task_failed(
        self,
        task_id: str,
        agent_id: str,
        reason: str,
    ) -> Optional[str]:
        """Capture a task-failed event and evaluate EIDOS prediction."""
        if not self._enabled:
            return None

        event_id = spark_memory.record_event(
            event_type="task_failed",
            description=f"Task failed by {agent_id[:8]}: {reason[:80]}",
            agent_id=agent_id,
            task_id=task_id,
            data=json.dumps({"reason": reason}),
        )

        # Evaluate EIDOS prediction
        spark_eidos.evaluate_prediction(
            task_id=task_id,
            actual_winner=agent_id,
            task_succeeded=False,
        )

        # Failures always worth consolidating
        self._maybe_consolidate(agent_id)

        logger.debug("Spark: captured failure %s by %s",
                      task_id[:8], agent_id[:8])
        return event_id

    def on_agent_joined(self, agent_id: str, name: str) -> Optional[str]:
        """Capture an agent-joined event."""
        if not self._enabled:
            return None

        return spark_memory.record_event(
            event_type="agent_joined",
            description=f"Agent {name} ({agent_id[:8]}) joined the swarm",
            agent_id=agent_id,
        )

    # ── Memory consolidation ────────────────────────────────────────────────

    def _maybe_consolidate(self, agent_id: str) -> None:
        """Consolidate events into memories when enough data exists."""
        agent_events = spark_memory.get_events(agent_id=agent_id, limit=50)
        if len(agent_events) < 5:
            return

        completions = [e for e in agent_events if e.event_type == "task_completed"]
        failures = [e for e in agent_events if e.event_type == "task_failed"]
        total = len(completions) + len(failures)

        if total < 3:
            return

        success_rate = len(completions) / total if total else 0

        if success_rate >= 0.8:
            spark_memory.store_memory(
                memory_type="pattern",
                subject=agent_id,
                content=f"Agent {agent_id[:8]} has a strong track record: "
                        f"{len(completions)}/{total} tasks completed successfully.",
                confidence=min(0.95, 0.6 + total * 0.05),
                source_events=total,
            )
        elif success_rate <= 0.3:
            spark_memory.store_memory(
                memory_type="anomaly",
                subject=agent_id,
                content=f"Agent {agent_id[:8]} is struggling: only "
                        f"{len(completions)}/{total} tasks completed.",
                confidence=min(0.95, 0.6 + total * 0.05),
                source_events=total,
            )

    # ── Query API ────────────────────────────────────────────────────────────

    def status(self) -> dict:
        """Return a summary of Spark Intelligence state."""
        eidos_stats = spark_eidos.get_accuracy_stats()
        return {
            "enabled": self._enabled,
            "events_captured": spark_memory.count_events(),
            "memories_stored": spark_memory.count_memories(),
            "predictions": eidos_stats,
            "event_types": {
                "task_posted": spark_memory.count_events("task_posted"),
                "bid_submitted": spark_memory.count_events("bid_submitted"),
                "task_assigned": spark_memory.count_events("task_assigned"),
                "task_completed": spark_memory.count_events("task_completed"),
                "task_failed": spark_memory.count_events("task_failed"),
                "agent_joined": spark_memory.count_events("agent_joined"),
            },
        }

    def get_advisories(self) -> list[Advisory]:
        """Generate current advisories based on accumulated intelligence."""
        if not self._enabled:
            return []
        return spark_advisor.generate_advisories()

    def get_timeline(self, limit: int = 50) -> list[SparkEvent]:
        """Return recent events as a timeline."""
        return spark_memory.get_events(limit=limit)

    def get_memories(self, limit: int = 50) -> list[SparkMemory]:
        """Return consolidated memories."""
        return spark_memory.get_memories(limit=limit)

    def get_predictions(self, limit: int = 20) -> list:
        """Return recent EIDOS predictions."""
        return spark_eidos.get_predictions(limit=limit)


# Module-level singleton — respects SPARK_ENABLED config
def _create_engine() -> SparkEngine:
    try:
        from config import settings
        return SparkEngine(enabled=settings.spark_enabled)
    except Exception:
        return SparkEngine(enabled=True)


spark_engine = _create_engine()
