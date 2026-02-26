# Monitoring Patterns

## Pattern: Gradual Degradation

Symptoms:
- Response times creeping up (100ms → 500ms → 2s)
- Memory usage slowly climbing
- Error rate slowly increasing

Action: Alert at WARNING level before it becomes CRITICAL.

## Pattern: Sudden Spike

Symptoms:
- Response time jumps from normal to >10s
- Error rate jumps from 0% to >20%
- Resource usage doubles instantly

Action: CRITICAL alert immediately. Possible DDoS or crash loop.

## Pattern: Intermittent Failure

Symptoms:
- Failures every 3rd check
- Random latency spikes
- Error patterns not consistent

Action: WARNING after 3 consecutive failures. Check for race conditions.

## Pattern: Cascade Failure

Symptoms:
- One service fails, then others follow
- Database slow → API slow → Dashboard slow

Action: CRITICAL. Root cause likely the first failing service.
