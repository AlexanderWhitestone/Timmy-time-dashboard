# ADR 017: Event Logging System

## Status
Accepted

## Context
The swarm system needed a way to audit all agent actions, task lifecycle events, and system events. Without centralized logging, debugging failures and understanding system behavior required grep-ing through application logs.

## Decision
Implement a centralized event logging system in SQLite (`event_log` table) that captures all significant events with structured data.

## Event Types

| Type | Description |
|------|-------------|
| `task.created` | New task posted |
| `task.bidding` | Task opened for bidding |
| `task.assigned` | Task assigned to agent |
| `task.started` | Agent started working |
| `task.completed` | Task finished successfully |
| `task.failed` | Task failed |
| `agent.joined` | New agent registered |
| `agent.left` | Agent deregistered |
| `bid.submitted` | Agent submitted bid |
| `tool.called` | Tool execution started |
| `tool.completed` | Tool execution finished |
| `system.error` | System error occurred |

## Schema
```sql
CREATE TABLE event_log (
    id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    source TEXT NOT NULL,
    task_id TEXT,
    agent_id TEXT,
    data TEXT,  -- JSON
    timestamp TEXT NOT NULL
);
```

## Usage

```python
from swarm.event_log import log_event, EventType, get_task_events

# Log an event
log_event(
    event_type=EventType.TASK_ASSIGNED,
    source="coordinator",
    task_id=task.id,
    agent_id=winner.agent_id,
    data={"bid_sats": winner.bid_sats},
)

# Query events
events = get_task_events(task_id)
summary = get_event_summary(minutes=60)
```

## Integration
The coordinator automatically logs:
- Task creation, assignment, completion, failure
- Agent join/leave events
- System warnings and errors

## Consequences
- **Positive**: Complete audit trail, easy debugging, analytics support
- **Negative**: Additional database writes, storage growth over time

## Mitigations
- `prune_events()` function removes events older than N days
- Indexes on `task_id`, `agent_id`, and `timestamp` for fast queries
