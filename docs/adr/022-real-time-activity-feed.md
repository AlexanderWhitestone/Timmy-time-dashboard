# ADR 022: Real-Time Activity Feed

## Status
Proposed

## Context
The dashboard currently shows static snapshots of swarm state. Users must refresh to see:
- New tasks being created
- Agents joining/leaving
- Bids being submitted
- Tasks being completed

This creates a poor UX for monitoring the swarm in real-time.

## Decision
Implement a WebSocket-based real-time activity feed that streams events from the Event Log to connected dashboard clients.

## Architecture

### Data Flow
```
Coordinator Event → Event Log (SQLite)
       ↓
WebSocket Broadcast
       ↓
Dashboard Clients (via ws_manager)
```

### Components

1. **Event Source** (`src/swarm/coordinator.py`)
   - Already emits events via `log_event()`
   - Events are persisted to SQLite

2. **WebSocket Bridge** (`src/ws_manager/handler.py`)
   - Already exists for agent status
   - Extend to broadcast events

3. **Event Broadcaster** (`src/events/broadcaster.py` - NEW)
   ```python
   class EventBroadcaster:
       """Bridges event_log → WebSocket."""
       
       async def on_event_logged(self, event: EventLogEntry):
           """Called when new event is logged."""
           await ws_manager.broadcast_event({
               "type": event.event_type.value,
               "source": event.source,
               "task_id": event.task_id,
               "agent_id": event.agent_id,
               "timestamp": event.timestamp,
               "data": event.data,
           })
   ```

4. **Dashboard UI** (`/swarm/live` - enhanced)
   - Already exists at `/swarm/live`
   - Add activity feed panel
   - Connect to WebSocket
   - Show real-time events

5. **Mobile Support**
   - Same WebSocket for mobile view
   - Simplified activity list

### Event Types to Broadcast

| Event Type | Display As | Icon |
|------------|------------|------|
| `task.created` | "New task: {description}" | 📝 |
| `task.assigned` | "Task assigned to {agent}" | 👤 |
| `task.completed` | "Task completed" | ✓ |
| `agent.joined` | "Agent {name} joined" | 🟢 |
| `agent.left` | "Agent {name} left" | 🔴 |
| `bid.submitted` | "Bid: {amount}sats from {agent}" | 💰 |
| `tool.called` | "Tool: {tool_name}" | 🔧 |
| `system.error` | "Error: {message}" | ⚠️ |

### WebSocket Protocol

```json
// Client connects
{"action": "subscribe", "channel": "events"}

// Server broadcasts
{
  "type": "event",
  "payload": {
    "event_type": "task.assigned",
    "source": "coordinator",
    "task_id": "task-123",
    "agent_id": "agent-456",
    "timestamp": "2024-01-15T10:30:00Z",
    "data": {"bid_sats": 100}
  }
}
```

### UI Design: Activity Feed Panel

```
┌─────────────────────────────────────────┐
│ LIVE ACTIVITY                    [🔴]  │
├─────────────────────────────────────────┤
│ 📝 New task: Write Python function      │
│    10:30:01                             │
│ 💰 Bid: 50sats from forge               │
│    10:30:02                             │
│ 👤 Task assigned to forge               │
│    10:30:07                             │
│ ✓ Task completed                        │
│    10:30:15                             │
│ 🟢 Agent Echo joined                    │
│    10:31:00                             │
│                                         │
│ [Show All Events]                       │
└─────────────────────────────────────────┘
```

### Integration with Existing Systems

**Existing: Event Log** (`src/swarm/event_log.py`)
- Hook into `log_event()` to trigger broadcasts
- Use SQLite `AFTER INSERT` trigger or Python callback

**Existing: WebSocket Manager** (`src/ws_manager/handler.py`)
- Add `broadcast_event()` method
- Handle client subscriptions

**Existing: Coordinator** (`src/swarm/coordinator.py`)
- Already calls `log_event()` for all lifecycle events
- No changes needed

**Existing: Swarm Live Page** (`/swarm/live`)
- Enhance with activity feed panel
- WebSocket client connection

### Technical Design

#### Option A: Direct Callback (Chosen)
Modify `log_event()` to call broadcaster directly.

**Pros:** Simple, immediate delivery
**Cons:** Tight coupling

```python
# In event_log.py
def log_event(...):
    # ... store in DB ...
    
    # Broadcast to WebSocket clients
    asyncio.create_task(_broadcast_event(event))
```

#### Option B: SQLite Trigger + Poll
Use SQLite trigger to mark new events, poll from broadcaster.

**Pros:** Decoupled, survives restarts
**Cons:** Latency from polling

#### Option C: Event Bus
Use existing `src/events/bus.py` to publish/subscribe.

**Pros:** Decoupled, flexible
**Cons:** Additional complexity

**Decision:** Option A for simplicity, with Option C as future refactoring.

### Performance Considerations

- **Rate Limiting:** Max 10 events/second to clients
- **Buffering:** If client disconnected, buffer last 100 events
- **Filtering:** Clients can filter by event type
- **Deduplication:** WebSocket manager handles client dedup

### Security

- Only authenticated dashboard users receive events
- Sanitize event data (no secrets in logs)
- Rate limit connections per IP

## Consequences

### Positive
- Real-time visibility into swarm activity
- Better UX for monitoring
- Uses existing infrastructure (Event Log, WebSocket)

### Negative
- Increased server load from WebSocket connections
- Event data must be carefully sanitized
- More complex client-side state management

### Mitigations
- Event throttling
- Connection limits
- Graceful degradation to polling

## Implementation Plan

1. **Create EventBroadcaster** - Bridge event_log → ws_manager
2. **Extend ws_manager** - Add `broadcast_event()` method
3. **Modify event_log.py** - Hook in broadcaster
4. **Enhance /swarm/live** - Add activity feed panel with WebSocket
5. **Create EventFeed component** - Reusable HTMX + WebSocket widget
6. **Write tests** - E2E tests for real-time updates

## Dependencies
- Existing `src/swarm/event_log.py`
- Existing `src/ws_manager/handler.py`
- Existing `/swarm/live` page
- HTMX WebSocket extension (already loaded)
