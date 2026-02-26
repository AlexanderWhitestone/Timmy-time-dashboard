# ADR 020: Cascade Router Integration with Timmy Agent

## Status
Proposed

## Context
Currently, the Timmy agent (`src/timmy/agent.py`) uses `src/timmy/backends.py` which provides a simple abstraction over Ollama and AirLLM. However, this lacks:
- Automatic failover between multiple LLM providers
- Circuit breaker pattern for failing providers
- Cost and latency tracking per provider
- Priority-based routing (local first, then APIs)

The Cascade Router (`src/router/cascade.py`) already implements these features but is not integrated with Timmy.

## Decision
Integrate the Cascade Router as the primary LLM routing layer for Timmy, replacing the direct backend abstraction.

## Architecture

### Current Flow
```
User Request → Timmy Agent → backends.py → Ollama/AirLLM
```

### Proposed Flow
```
User Request → Timmy Agent → Cascade Router → Provider 1 (Ollama)
                                      ↓ (if fail)
                                 Provider 2 (Local AirLLM)
                                      ↓ (if fail)
                                 Provider 3 (API - optional)
                                      ↓
                                 Track metrics per provider
```

### Integration Points

1. **Timmy Agent** (`src/timmy/agent.py`)
   - Replace `create_timmy()` backend initialization
   - Use `CascadeRouter.complete()` instead of direct `agent.run()`
   - Expose provider status in agent responses

2. **Cascade Router** (`src/router/cascade.py`)
   - Already supports: Ollama, OpenAI, Anthropic, AirLLM
   - Already has: Circuit breakers, metrics, failover logic
   - Add: Integration with existing `src/timmy/prompts.py`

3. **Configuration** (`config.yaml` or `config.py`)
   - Provider list with priorities
   - API keys (optional, for cloud fallback)
   - Circuit breaker thresholds

4. **Dashboard** (new route)
   - `/router/status` - Show provider health, metrics, recent failures
   - Real-time provider status indicator

### Provider Priority Order

1. **Ollama (local)** - Priority 1, always try first
2. **AirLLM (local)** - Priority 2, if Ollama unavailable
3. **API providers** - Priority 3+, only if configured

### Data Flow

```python
# Timmy Agent
async def respond(self, message: str) -> str:
    # Get cascade router
    router = get_cascade_router()
    
    # Route through cascade with automatic failover
    response = await router.complete(
        messages=[{"role": "user", "content": message}],
        system_prompt=TIMMY_SYSTEM_PROMPT,
    )
    
    # Response includes which provider was used
    return response.content
```

## Schema Additions

### Provider Status Table (new)
```sql
CREATE TABLE provider_metrics (
    provider_name TEXT PRIMARY KEY,
    total_requests INTEGER DEFAULT 0,
    successful_requests INTEGER DEFAULT 0,
    failed_requests INTEGER DEFAULT 0,
    avg_latency_ms REAL DEFAULT 0,
    last_error_time TEXT,
    circuit_state TEXT DEFAULT 'closed',
    updated_at TEXT
);
```

## Consequences

### Positive
- Automatic failover improves reliability
- Metrics enable data-driven provider selection
- Circuit breakers prevent cascade failures
- Configurable without code changes

### Negative
- Additional complexity in request path
- Potential latency increase from retries
- Requires careful circuit breaker tuning

### Mitigations
- Circuit breakers have short recovery timeouts (60s)
- Metrics exposed for monitoring
- Fallback to mock responses if all providers fail

## Implementation Plan

1. Create `src/timmy/cascade_adapter.py` - Adapter between Timmy and Cascade Router
2. Modify `src/timmy/agent.py` - Use adapter instead of direct backends
3. Create dashboard route `/router/status` - Provider health UI
4. Add provider metrics persistence to SQLite
5. Write tests for failover scenarios

## Dependencies
- Existing `src/router/cascade.py`
- Existing `src/timmy/agent.py`
- New dashboard route
