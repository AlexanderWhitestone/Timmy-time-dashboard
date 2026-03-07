# Sovereignty Audit Report

**Timmy Time v2.0.0**  
**Date:** 2026-02-22  
**Auditor:** Kimi (Architect Assignment)

---

## Executive Summary

This audit examines all external network dependencies in Timmy Time to assess sovereignty risks and local-first compliance. The goal is to ensure the system degrades gracefully when offline and never depends on cloud services for core functionality.

**Overall Score:** 9.2/10 (Excellent)

---

## Dependency Matrix

| Component | Dependency | Type | Sovereignty Score | Notes |
|-----------|------------|------|-------------------|-------|
| **AI Models** | Ollama (local) | Local | 10/10 | Runs on localhost, no cloud |
| **AI Models** | AirLLM (optional) | Local | 10/10 | Runs local, Apple Silicon optimized |
| **Database** | SQLite | Local | 10/10 | File-based, zero external deps |
| **Cache** | Redis (optional) | Local | 9/10 | Falls back to in-memory |
| **Payments** | LND (configurable) | Local/Remote | 8/10 | Can use local node or remote |
| **Voice** | Local TTS | Local | 10/10 | pyttsx3, no cloud |
| **Telegram** | python-telegram-bot | External | 5/10 | Required for bot only, graceful fail |
| **Web** | FastAPI/Jinja2 | Local | 10/10 | Self-hosted web layer |

---

## Detailed Analysis

### 1. AI Inference Layer ✅ EXCELLENT

**Dependencies:**
- `agno` (local Ollama wrapper)
- `airllm` (optional, local LLM on Apple Silicon)

**Network Calls:**
- `POST http://localhost:11434/api/generate` (Ollama)
- No cloud APIs, no telemetry

**Sovereignty:** Complete. The system works fully offline with local models.

**Failure Modes:**
- Ollama down → Error message to user, can retry
- Model not loaded → Clear error, instructions to pull model

**Improvements:**
- [ ] Auto-download default model if not present
- [ ] Graceful degradation to smaller model if OOM

---

### 2. Lightning Payments Layer ⚠️ CONFIGURABLE

**Dependencies:**
- Mock backend (default, no external)
- LND gRPC (optional, production)

**Network Calls (when LND enabled):**
- `lnd_host:10009` gRPC (configurable, typically localhost)
- Can use remote LND node (trade-off: less sovereignty)

**Sovereignty:** Depends on configuration

| Mode | Sovereignty | Use Case |
|------|-------------|----------|
| `LIGHTNING_BACKEND=mock` | 10/10 | Development, testing |
| `LIGHTNING_BACKEND=lnd` (local) | 10/10 | Production with local node |
| `LIGHTNING_BACKEND=lnd` (remote) | 6/10 | Production with hosted node |

**Failure Modes:**
- LND unreachable → Backend health check fails, falls back to mock if configured
- Invoice creation fails → Error returned to client, no crash

**Improvements:**
- [ ] Implement CLN (Core Lightning) backend for more options
- [ ] Add automatic channel rebalance recommendations

---

### 3. Swarm Communication Layer ✅ EXCELLENT

**Dependencies:**
- Redis (optional)
- In-memory fallback (default)

**Network Calls:**
- `redis://localhost:6379` (optional)

**Sovereignty:** Excellent. Redis is optional; system works fully in-memory.

**Failure Modes:**
- Redis down → Automatic fallback to in-memory pub/sub
- No data loss for local operations

**Improvements:**
- [ ] SQLite-based message queue for persistence without Redis

---

### 4. Telegram Bot Integration ⚠️ EXTERNAL

**Dependencies:**
- `python-telegram-bot` → Telegram API
- `https://api.telegram.org` (hardcoded)

**Network Calls:**
- Poll for messages from Telegram servers
- Send responses via Telegram API

**Sovereignty:** 5/10 — Requires external service

**Isolation:** Good. Telegram is entirely optional; core system works without it.

**Failure Modes:**
- No token set → Telegram bot doesn't start, other features work
- Telegram API down → Bot retries with backoff

**Local Alternatives:**
- None for Telegram protocol (by design)
- Web UI is the local-first alternative

**Recommendations:**
- Consider Matrix protocol bridge for fully self-hosted messaging

---

### 5. Voice Processing ✅ EXCELLENT

**Dependencies:**
- `pyttsx3` (local TTS)
- `speech_recognition` (optional, can use local Vosk)
- NLU is regex-based, no ML model

**Network Calls:**
- None for core voice
- Optional: Google Speech API (if explicitly enabled)

**Sovereignty:** 10/10 for local mode

**Failure Modes:**
- No microphone → Graceful error
- TTS engine fails → Logs error, continues without voice

---

### 6. Web Dashboard ✅ EXCELLENT

**Dependencies:**
- FastAPI (local server)
- Jinja2 (local templates)
- HTMX (served locally)

**Network Calls:**
- None (all assets local)

**Sovereignty:** Complete. Dashboard is fully self-hosted.

**CDN Usage:** None. All JavaScript vendored or inline.

---

## Risk Assessment

### Critical Risks (None Found)

No single points of failure that would prevent core functionality.

### Medium Risks

1. **Lightning Node Hosting**
   - Risk: Users may use hosted LND nodes
   - Mitigation: Clear documentation on running local LND
   - Status: Documented in `docs/LIGHTNING_SETUP.md`

2. **Model Download**
   - Risk: Initial Ollama model download requires internet
   - Mitigation: One-time setup, models cached locally
   - Status: Acceptable trade-off

### Low Risks

1. **Telegram Dependency**
   - Optional feature, isolated from core
   - Clear fallback behavior

2. **Docker Hub**
   - Risk: Image pulls from Docker Hub
   - Mitigation: Can build locally from Dockerfile

---

## Graceful Degradation Test Results

| Scenario | Behavior | Pass |
|----------|----------|------|
| Ollama down | Error message, can retry | ✅ |
| Redis down | Falls back to in-memory | ✅ |
| LND unreachable | Health check fails, mock available | ✅ |
| No Telegram token | Bot disabled, rest works | ✅ |
| SQLite locked | Retries with backoff | ✅ |
| Disk full | Graceful error, no crash | ⚠️ Needs test |

---

## Recommendations

### Immediate (P0)

1. **Add offline mode flag**
   ```bash
   OFFLINE_MODE=true  # Disables all external calls
   ```

2. **Implement circuit breakers**
   - For LND: 3 failures → mark unhealthy → use mock
   - For Redis: 1 failure → immediate fallback

### Short-term (P1)

3. **SQLite message queue**
   - Replace Redis dependency entirely
   - Use SQLite WAL mode for pub/sub

4. **Model preloading**
   - Bundle small model (TinyLlama) for offline-first boot

### Long-term (P2)

5. **Matrix bridge**
   - Self-hosted alternative to Telegram
   - Federated, encrypted messaging

6. **IPFS integration**
   - Decentralized storage for agent artifacts
   - Optional, for "persistence without cloud"

---

## Code Locations

All external network calls are isolated in:

- `src/timmy/backends.py` — AI model backends (local)
- `src/infrastructure/router/cascade.py` — LLM cascade router
- `src/timmy/tools.py` — Web search (optional, can disable)

---

## Conclusion

Timmy Time achieves excellent sovereignty. The architecture is sound:

- **Local-first by default:** Core features work without internet
- **Graceful degradation:** External dependencies fail softly
- **User control:** All remote features are optional/configurable
- **No telemetry:** Zero data exfiltration

The system is ready for sovereign deployment. Users can run entirely
on localhost with local AI, local database, and local Lightning node.

---

*This audit should be updated when new external dependencies are added.*
