# Timmy Time — Workset Plan Phase 2 (Functional Hardening)

**Date:** 2026-02-25  
**Based on:** QUALITY_ANALYSIS.md remaining issues

---

## Executive Summary

This workset addresses the core functional gaps that prevent the swarm system from operating as designed. The swarm currently registers agents in the database but doesn't actually spawn processes or execute bids. This workset makes the swarm operational.

---

## Workset E: Swarm System Realization 🐝

### E1: Real Agent Process Spawning (FUNC-01)
**Priority:** P1 — High  
**Files:** `swarm/agent_runner.py`, `swarm/coordinator.py`

**Issue:** `spawn_agent()` creates a database record but no Python process is actually launched.

**Fix:**
- Complete the `agent_runner.py` subprocess implementation
- Ensure spawned agents can communicate with coordinator
- Add proper lifecycle management (start, monitor, stop)

### E2: Working Auction System (FUNC-02)
**Priority:** P1 — High  
**Files:** `swarm/bidder.py`, `swarm/persona_node.py`

**Issue:** Bidding system runs auctions but no actual agents submit bids.

**Fix:**
- Connect persona agents to the bidding system
- Implement automatic bid generation based on capabilities
- Ensure auction resolution assigns tasks to winners

### E3: Persona Agent Auto-Bidding
**Priority:** P1 — High  
**Files:** `swarm/persona_node.py`, `swarm/coordinator.py`

**Fix:**
- Spawned persona agents should automatically bid on matching tasks
- Implement capability-based bid decisions
- Add bid amount calculation (base + jitter)

---

## Workset F: Testing & Reliability 🧪

### F1: WebSocket Reconnection Tests (TEST-01)
**Priority:** P2 — Medium  
**Files:** `tests/test_websocket.py`

**Issue:** WebSocket tests don't cover reconnection logic or malformed payloads.

**Fix:**
- Add reconnection scenario tests
- Test malformed payload handling
- Test connection failure recovery

### F2: Voice TTS Graceful Degradation
**Priority:** P2 — Medium  
**Files:** `timmy_serve/voice_tts.py`, `dashboard/routes/voice.py`

**Issue:** Voice routes fail without clear message when `pyttsx3` not installed.

**Fix:**
- Add graceful fallback message
- Return helpful error suggesting `pip install ".[voice]"`
- Don't crash, return 503 with instructions

### F3: Mobile Route Navigation
**Priority:** P2 — Medium  
**Files:** `templates/base.html`

**Issue:** `/mobile` route not linked from desktop navigation.

**Fix:**
- Add mobile link to base template nav
- Make it easy to find mobile-optimized view

---

## Workset G: Performance & Architecture ⚡

### G1: SQLite Connection Pooling (PERF-01)
**Priority:** P3 — Low  
**Files:** `swarm/registry.py`

**Issue:** New SQLite connection opened on every query.

**Fix:**
- Implement connection pooling or singleton pattern
- Reduce connection overhead
- Maintain thread safety

### G2: Development Experience
**Priority:** P2 — Medium  
**Files:** `Makefile`, `README.md`

**Issue:** No single command to start full dev environment.

**Fix:**
- Add `make dev-full` that starts dashboard + Ollama check
- Add better startup validation

---

## Execution Order

| Order | Workset | Task | Est. Time |
|-------|---------|------|-----------|
| 1 | E | Persona auto-bidding system | 45 min |
| 2 | E | Fix auction resolution | 30 min |
| 3 | F | Voice graceful degradation | 20 min |
| 4 | F | Mobile nav link | 10 min |
| 5 | G | SQLite connection pooling | 30 min |
| 6 | — | Test everything | 30 min |

**Total: ~2.5 hours**

---

## Success Criteria

- [ ] Persona agents automatically bid on matching tasks
- [ ] Auctions resolve with actual winners
- [ ] Voice routes degrade gracefully without pyttsx3
- [ ] Mobile route accessible from desktop nav
- [ ] SQLite connections pooled/reused
- [ ] All 895+ tests pass
- [ ] New tests for bidding system
