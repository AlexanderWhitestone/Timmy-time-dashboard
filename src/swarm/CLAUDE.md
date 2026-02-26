# swarm/ — Module Guide

Security-sensitive module. Changes to `coordinator.py` require review.

## Structure
- `coordinator.py` — Auction-based task assignment (singleton: `coordinator`)
- `tasks.py`, `bidder.py`, `comms.py` — Core swarm primitives
- `work_orders/` — External work order submission and execution
- `task_queue/` — Human-in-the-loop approval queue
- `event_log.py` — Structured event logging
- `personas.py`, `persona_node.py` — Agent persona management

## Key singletons
```python
from swarm.coordinator import coordinator
```

## Testing
```bash
pytest tests/swarm/ -q
```
