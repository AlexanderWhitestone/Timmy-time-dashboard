"""Spark advisor — generates ranked recommendations from accumulated intelligence.

The advisor examines Spark's event history, consolidated memories, and EIDOS
prediction accuracy to produce actionable recommendations for the swarm.

Categories
----------
- agent_performance  — "Agent X excels at Y, consider routing more Y tasks"
- bid_optimization   — "Bids on Z tasks are consistently high, room to save"
- failure_prevention — "Agent A has failed 3 recent tasks, investigate"
- system_health      — "No events in 30 min, swarm may be idle"
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from spark import memory as spark_memory
from spark import eidos as spark_eidos

logger = logging.getLogger(__name__)

# Minimum events before the advisor starts generating recommendations
_MIN_EVENTS = 3


@dataclass
class Advisory:
    """A single ranked recommendation."""
    category: str          # agent_performance, bid_optimization, etc.
    priority: float        # 0.0–1.0 (higher = more urgent)
    title: str             # Short headline
    detail: str            # Longer explanation
    suggested_action: str  # What to do about it
    subject: Optional[str] = None  # agent_id or None for system-level
    evidence_count: int = 0  # Number of supporting events


def generate_advisories() -> list[Advisory]:
    """Analyse Spark data and produce ranked recommendations.

    Returns advisories sorted by priority (highest first).
    """
    advisories: list[Advisory] = []

    event_count = spark_memory.count_events()
    if event_count < _MIN_EVENTS:
        advisories.append(Advisory(
            category="system_health",
            priority=0.3,
            title="Insufficient data",
            detail=f"Only {event_count} events captured. "
                   f"Spark needs at least {_MIN_EVENTS} events to generate insights.",
            suggested_action="Run more swarm tasks to build intelligence.",
            evidence_count=event_count,
        ))
        return advisories

    advisories.extend(_check_failure_patterns())
    advisories.extend(_check_agent_performance())
    advisories.extend(_check_bid_patterns())
    advisories.extend(_check_prediction_accuracy())
    advisories.extend(_check_system_activity())

    advisories.sort(key=lambda a: a.priority, reverse=True)
    return advisories


def _check_failure_patterns() -> list[Advisory]:
    """Detect agents with recent failure streaks."""
    results: list[Advisory] = []
    failures = spark_memory.get_events(event_type="task_failed", limit=50)

    # Group failures by agent
    agent_failures: dict[str, int] = {}
    for ev in failures:
        aid = ev.agent_id
        if aid:
            agent_failures[aid] = agent_failures.get(aid, 0) + 1

    for aid, count in agent_failures.items():
        if count >= 2:
            results.append(Advisory(
                category="failure_prevention",
                priority=min(1.0, 0.5 + count * 0.15),
                title=f"Agent {aid[:8]} has {count} failures",
                detail=f"Agent {aid[:8]}... has failed {count} recent tasks. "
                       f"This pattern may indicate a capability mismatch or "
                       f"configuration issue.",
                suggested_action=f"Review task types assigned to {aid[:8]}... "
                                 f"and consider adjusting routing preferences.",
                subject=aid,
                evidence_count=count,
            ))

    return results


def _check_agent_performance() -> list[Advisory]:
    """Identify top-performing and underperforming agents."""
    results: list[Advisory] = []
    completions = spark_memory.get_events(event_type="task_completed", limit=100)
    failures = spark_memory.get_events(event_type="task_failed", limit=100)

    # Build success/failure counts per agent
    agent_success: dict[str, int] = {}
    agent_fail: dict[str, int] = {}

    for ev in completions:
        aid = ev.agent_id
        if aid:
            agent_success[aid] = agent_success.get(aid, 0) + 1

    for ev in failures:
        aid = ev.agent_id
        if aid:
            agent_fail[aid] = agent_fail.get(aid, 0) + 1

    all_agents = set(agent_success) | set(agent_fail)
    for aid in all_agents:
        wins = agent_success.get(aid, 0)
        fails = agent_fail.get(aid, 0)
        total = wins + fails
        if total < 2:
            continue

        rate = wins / total
        if rate >= 0.8 and total >= 3:
            results.append(Advisory(
                category="agent_performance",
                priority=0.6,
                title=f"Agent {aid[:8]} excels ({rate:.0%} success)",
                detail=f"Agent {aid[:8]}... has completed {wins}/{total} tasks "
                       f"successfully. Consider routing more tasks to this agent.",
                suggested_action="Increase task routing weight for this agent.",
                subject=aid,
                evidence_count=total,
            ))
        elif rate <= 0.3 and total >= 3:
            results.append(Advisory(
                category="agent_performance",
                priority=0.75,
                title=f"Agent {aid[:8]} struggling ({rate:.0%} success)",
                detail=f"Agent {aid[:8]}... has only succeeded on {wins}/{total} tasks. "
                       f"May need different task types or capability updates.",
                suggested_action="Review this agent's capabilities and assigned task types.",
                subject=aid,
                evidence_count=total,
            ))

    return results


def _check_bid_patterns() -> list[Advisory]:
    """Detect bid optimization opportunities."""
    results: list[Advisory] = []
    bids = spark_memory.get_events(event_type="bid_submitted", limit=100)

    if len(bids) < 5:
        return results

    # Extract bid amounts
    bid_amounts: list[int] = []
    for ev in bids:
        try:
            data = json.loads(ev.data)
            sats = data.get("bid_sats", 0)
            if sats > 0:
                bid_amounts.append(sats)
        except (json.JSONDecodeError, TypeError):
            continue

    if not bid_amounts:
        return results

    avg_bid = sum(bid_amounts) / len(bid_amounts)
    max_bid = max(bid_amounts)
    min_bid = min(bid_amounts)
    spread = max_bid - min_bid

    if spread > avg_bid * 1.5:
        results.append(Advisory(
            category="bid_optimization",
            priority=0.5,
            title=f"Wide bid spread ({min_bid}–{max_bid} sats)",
            detail=f"Bids range from {min_bid} to {max_bid} sats "
                   f"(avg {avg_bid:.0f}). Large spread may indicate "
                   f"inefficient auction dynamics.",
            suggested_action="Review agent bid strategies for consistency.",
            evidence_count=len(bid_amounts),
        ))

    if avg_bid > 70:
        results.append(Advisory(
            category="bid_optimization",
            priority=0.45,
            title=f"High average bid ({avg_bid:.0f} sats)",
            detail=f"The swarm average bid is {avg_bid:.0f} sats across "
                   f"{len(bid_amounts)} bids. This may be above optimal.",
            suggested_action="Consider adjusting base bid rates for persona agents.",
            evidence_count=len(bid_amounts),
        ))

    return results


def _check_prediction_accuracy() -> list[Advisory]:
    """Report on EIDOS prediction accuracy."""
    results: list[Advisory] = []
    stats = spark_eidos.get_accuracy_stats()

    if stats["evaluated"] < 3:
        return results

    avg = stats["avg_accuracy"]
    if avg < 0.4:
        results.append(Advisory(
            category="system_health",
            priority=0.65,
            title=f"Low prediction accuracy ({avg:.0%})",
            detail=f"EIDOS predictions have averaged {avg:.0%} accuracy "
                   f"over {stats['evaluated']} evaluations. The learning "
                   f"model needs more data or the swarm behaviour is changing.",
            suggested_action="Continue running tasks; accuracy should improve "
                             "as the model accumulates more training data.",
            evidence_count=stats["evaluated"],
        ))
    elif avg >= 0.75:
        results.append(Advisory(
            category="system_health",
            priority=0.3,
            title=f"Strong prediction accuracy ({avg:.0%})",
            detail=f"EIDOS predictions are performing well at {avg:.0%} "
                   f"average accuracy over {stats['evaluated']} evaluations.",
            suggested_action="No action needed. Spark intelligence is learning effectively.",
            evidence_count=stats["evaluated"],
        ))

    return results


def _check_system_activity() -> list[Advisory]:
    """Check for system idle patterns."""
    results: list[Advisory] = []
    recent = spark_memory.get_events(limit=5)

    if not recent:
        results.append(Advisory(
            category="system_health",
            priority=0.4,
            title="No swarm activity detected",
            detail="Spark has not captured any events. "
                   "The swarm may be idle or Spark event capture is not active.",
            suggested_action="Post a task to the swarm to activate the pipeline.",
        ))
        return results

    # Check event type distribution
    types = [e.event_type for e in spark_memory.get_events(limit=100)]
    type_counts = {}
    for t in types:
        type_counts[t] = type_counts.get(t, 0) + 1

    if "task_completed" not in type_counts and "task_failed" not in type_counts:
        if type_counts.get("task_posted", 0) > 3:
            results.append(Advisory(
                category="system_health",
                priority=0.6,
                title="Tasks posted but none completing",
                detail=f"{type_counts.get('task_posted', 0)} tasks posted "
                       f"but no completions or failures recorded.",
                suggested_action="Check agent availability and auction configuration.",
                evidence_count=type_counts.get("task_posted", 0),
            ))

    return results
