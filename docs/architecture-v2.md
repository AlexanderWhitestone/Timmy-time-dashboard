# Timmy Time Architecture v2

## Overview
This document describes how the 6 new features integrate with the existing architecture.

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              DASHBOARD UI                                   │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────────┐   │
│  │  Event Log   │ │   Ledger     │ │   Memory     │ │  Upgrade Queue   │   │
│  │  /swarm/events│ │/lightning/ledger│ │  /memory    │ │ /self-modify/queue│  │
│  └──────┬───────┘ └──────┬───────┘ └──────┬───────┘ └────────┬─────────┘   │
│         │                │                │                  │             │
│  ┌──────┴───────┐ ┌──────┴───────┐ ┌──────┴───────┐ ┌────────┴─────────┐   │
│  │  WebSocket   │ │              │ │              │ │   Real-Time      │   │
│  │  Activity    │ │              │ │              │ │   Activity Feed  │   │
│  │  Feed        │ │              │ │              │ │                  │   │
│  └──────┬───────┘ └──────────────┘ └──────────────┘ └──────────────────┘   │
└─────────┼───────────────────────────────────────────────────────────────────┘
          │ WebSocket
┌─────────┼───────────────────────────────────────────────────────────────────┐
│         │                      API LAYER                                    │
│  ┌──────┴───────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────────┐   │
│  │   Events     │ │    Ledger    │ │    Memory    │ │  Self-Modify     │   │
│  │   Routes     │ │    Routes    │ │    Routes    │ │    Routes        │   │
│  └──────┬───────┘ └──────┬───────┘ └──────┬───────┘ └────────┬─────────┘   │
└─────────┼────────────────┼────────────────┼──────────────────┼─────────────┘
          │                │                │                  │
┌─────────┼────────────────┼────────────────┼──────────────────┼─────────────┐
│         │           CORE SERVICES                                        │
│         │                │                │                  │            │
│  ┌──────┴───────┐ ┌──────┴───────┐ ┌──────┴───────┐ ┌────────┴─────────┐  │
│  │  Event Log   │ │   Ledger     │ │Vector Store  │ │ Self-Modify Loop │  │
│  │  Service     │ │   Service    │ │  (Echo)      │ │   with Queue     │  │
│  └──────┬───────┘ └──────┬───────┘ └──────┬───────┘ └────────┬─────────┘  │
│         │                │                │                  │            │
│         └────────────────┴────────────────┴──────────────────┘            │
│                                    │                                      │
│                              ┌─────┴─────┐                                 │
│                              │ SQLite DB │                                 │
│                              │  swarm.db │                                 │
│                              └───────────┘                                 │
│                                                                           │
│  ┌─────────────────────────────────────────────────────────────────────┐  │
│  │                     CASCADE ROUTER (New)                            │  │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌─────────────────────┐  │  │
│  │  │ Ollama   │→ │  AirLLM  │→ │   API    │→ │  Metrics & Health   │  │  │
│  │  │(local)   │  │ (local)  │  │(optional)│  │  Dashboard          │  │  │
│  │  └──────────┘  └──────────┘  └──────────┘  └─────────────────────┘  │  │
│  └─────────────────────────────────────────────────────────────────────┘  │
│                                    │                                      │
│                              ┌─────┴─────┐                                 │
│                              │   Timmy   │                                 │
│                              │   Agent   │                                 │
│                              └───────────┘                                 │
└─────────────────────────────────────────────────────────────────────────┘
```

## Data Flow

### 1. Event Log System
```
Coordinator Action → log_event() → SQLite event_log table
                                          ↓
                                    WebSocket Broadcast (ADR-022)
                                          ↓
                                    Dashboard Activity Feed
```

### 2. Lightning Ledger
```
Payment Handler → create_invoice_entry() → SQLite ledger table
                                                  ↓
                                            mark_settled()
                                                  ↓
                                            Dashboard /lightning/ledger
```

### 3. Semantic Memory
```
Conversation → store_memory() → SQLite memory_entries (with embedding)
                                        ↓
                                  search_memories(query)
                                        ↓
                                  Dashboard /memory
```

### 4. Self-Upgrade Queue
```
Self-Modify Loop → Propose Change → SQLite upgrades table (status: proposed)
                                            ↓
                                    Dashboard Review
                                            ↓
                                    Approve → Apply → Git Commit
                                     or
                                    Reject → Cleanup
```

### 5. Cascade Router
```
User Request → Cascade Router → Ollama (try)
                      ↓ fail
                 AirLLM (fallback)
                      ↓ fail
                 API Provider (optional)
                      ↓
                 Metrics Tracking
                      ↓
                 Dashboard /router/status
```

### 6. Real-Time Activity Feed
```
Event Logged → EventBroadcaster → ws_manager.broadcast()
                                          ↓
                                    WebSocket Clients
                                          ↓
                                    Dashboard Activity Panel
```

## Database Schema

### Tables

| Table | Purpose | Feature |
|-------|---------|---------|
| `tasks` | Task management | Existing |
| `agents` | Agent registry | Existing |
| `event_log` | Audit trail | **New - ADR-017** |
| `ledger` | Lightning payments | **New - ADR-018** |
| `memory_entries` | Semantic memory | **New - ADR-019** |
| `upgrades` | Self-mod queue | **New - ADR-021** |
| `provider_metrics` | LLM metrics | **New - ADR-020** |

## Integration Points

### Existing → New

| Existing Component | Integrates With | How |
|-------------------|-----------------|-----|
| `coordinator.py` | Event Log | Calls `log_event()` for all lifecycle events |
| `payment_handler.py` | Ledger | Creates entries on invoice/settlement |
| `self_modify/loop.py` | Upgrade Queue | Stops at proposal, waits for approval |
| `timmy/agent.py` | Cascade Router | Uses router instead of direct backends |
| `ws_manager/handler.py` | Activity Feed | Broadcasts events to clients |

### New → Existing

| New Component | Uses Existing | How |
|---------------|---------------|-----|
| Event Log | `coordinator.py` | Receives all coordinator actions |
| Ledger | `payment_handler.py` | Integrated into invoice lifecycle |
| Memory | Personas | Echo agent queries for context |
| Upgrade Queue | `self_modify/loop.py` | Controls when changes apply |
| Cascade Router | `timmy/agent.py` | Provides LLM abstraction |
| Activity Feed | `ws_manager/handler.py` | Uses WebSocket infrastructure |

## Implementation Order

### Phase 1: Data Layer (Done)
1. ✅ Event Log table + integration
2. ✅ Ledger table + integration  
3. ✅ Vector store table + functions

### Phase 2: UI Layer (Done)
1. ✅ Event Log dashboard page
2. ✅ Ledger dashboard page
3. ✅ Memory browser page

### Phase 3: Advanced Features (Planned)
1. 📝 Cascade Router integration (ADR-020)
   - Create adapter layer
   - Modify Timmy agent
   - Provider status dashboard
   
2. 📝 Self-Upgrade Queue (ADR-021)
   - Create `upgrades` table
   - Modify self-modify loop
   - Dashboard queue UI
   
3. 📝 Real-Time Activity Feed (ADR-022)
   - EventBroadcaster bridge
   - WebSocket integration
   - Activity feed panel

### Phase 4: Testing
1. Unit tests for each service
2. E2E tests for full workflows
3. Load testing for WebSocket connections

## Configuration

New config options in `config.py`:

```python
# Cascade Router
cascade_providers: list[ProviderConfig]
circuit_breaker_threshold: int = 5

# Self-Upgrade
auto_approve_upgrades: bool = False
upgrade_timeout_hours: int = 24

# Activity Feed
websocket_event_throttle: int = 10  # events/sec
activity_feed_buffer: int = 100     # events to buffer
```

## Security Considerations

| Feature | Risk | Mitigation |
|---------|------|------------|
| Event Log | Log injection | Sanitize all data fields |
| Ledger | Payment forgery | Verify with Lightning node |
| Memory | Data exposure | Filter by user permissions |
| Upgrade Queue | Unauthorized changes | Require approval, audit log |
| Cascade Router | API key exposure | Use environment variables |
| Activity Feed | Data leak | Authenticate WebSocket |
