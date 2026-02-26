# infrastructure/ — Module Guide

Cross-cutting services used by many modules.

## Structure
- `ws_manager/` — WebSocket connection manager (singleton: `ws_manager`)
- `notifications/` — Push notification store (singleton: `notifier`)
- `events/` — Domain event bus and broadcaster
- `router/` — Cascade LLM router with circuit-breaker failover

## Key singletons
```python
from infrastructure.ws_manager.handler import ws_manager
from infrastructure.notifications.push import notifier
from infrastructure.events.bus import event_bus
from infrastructure.router import get_router
```

## Testing
```bash
pytest tests/infrastructure/ tests/integrations/test_websocket*.py tests/integrations/test_notifications.py -q
```
