# ROADMAP.md — Integration Roadmap for Timmy Time

**Origin:** [The Ascension of Timmy: Beyond the Exodus](docs/ASCENSION.md)
**Version:** 0.1.0 (draft)
**Last updated:** 2026-02-28
**Maintainer:** @AlexanderWhitestone

This document guides AI agents and human developers through the full
integration plan for Timmy Time. Each phase is independently valuable.
Phases are ordered by priority; dependencies are noted where they exist.

**Repo strategy:** Multi-repo ecosystem. Each heavy integration gets its own
repo, dockerized as a service. The main `Timmy-time-dashboard` repo stays
lean — it consumes these services via HTTP/WebSocket/gRPC.

---

## Current State (v2.0 Exodus)

What already works:

| Component | Status | Implementation |
|-----------|--------|----------------|
| Voice TTS | pyttsx3 (robotic) | `src/timmy_serve/voice_tts.py` |
| Voice STT | Browser Web Speech API | `src/dashboard/templates/voice_button.html` |
| Voice NLU | Regex-based intent detection | `src/integrations/voice/nlu.py` |
| Frontend | HTMX + Bootstrap + marked.js | `src/dashboard/templates/base.html` |
| LLM router | Cascade with circuit breaker | `src/infrastructure/router/cascade.py` |

What does NOT exist yet:

Piper TTS · Faster-Whisper · Chroma · CRDTs · LangGraph · Nostr ·
ZK-ML · Prometheus/Grafana/Loki · OpenTelemetry · Three.js · Tauri ·
Alpine.js · Firecracker/gVisor/WASM sandboxing · BOLT12 · Vickrey auctions

---

## Phase 0: Multi-Repo Foundation

**Goal:** Establish the repo ecosystem before building new services.

### Repos to create

| Repo | Purpose | Interface to main repo |
|------|---------|----------------------|
| `timmy-voice` | STT + TTS service | HTTP REST + WebSocket streaming |
| `timmy-nostr` | Nostr relay client, identity, reputation | HTTP REST + event stream |
| `timmy-memory` | Vector DB service (if external DB chosen) | HTTP REST |
| `timmy-observe` | Metrics collection + export | Prometheus scrape endpoint |

### Repo template

Each service repo follows:

```
timmy-<service>/
├── src/                    # Python source
├── tests/
├── Dockerfile
├── docker-compose.yml      # Standalone dev setup
├── pyproject.toml
├── Makefile                # make test, make dev, make docker-build
├── CLAUDE.md               # AI agent instructions specific to this repo
└── README.md
```

### Main repo changes

- Add `docker-compose.services.yml` for orchestrating external services
- Add thin client modules in `src/infrastructure/clients/` for each service
- Each client follows graceful degradation: if the service is down, log and
  return a fallback (never crash)

### Decision record

Create `docs/adr/023-multi-repo-strategy.md` documenting the split rationale.

---

## Phase 1: Sovereign Voice

**Priority:** HIGHEST — most urgent integration
**Repo:** `timmy-voice`
**Depends on:** Phase 0 (repo scaffold)

### 1.1 Research & Select Engines

Before writing code, evaluate these candidates. The goal is ONE engine per
concern that works across hardware tiers (Pi 4 through desktop GPU).

#### STT Candidates

| Engine | Size | Speed | Offline | Notes |
|--------|------|-------|---------|-------|
| **Faster-Whisper** | 39M–1.5G | 4-7x over Whisper | Yes | CTranslate2, INT8 quantization, mature ecosystem |
| **Moonshine** | 27M–245M | 100x faster than Whisper large on CPU | Yes | New (Feb 2026), edge-first, streaming capable |
| **Vosk** | 50M–1.8G | Real-time on Pi | Yes | Kaldi-based, very lightweight, good for embedded |
| **whisper.cpp** | Same as Whisper | CPU-optimized C++ | Yes | llama.cpp ecosystem, GGML quantization |

**Research tasks:**
- [ ] Benchmark Moonshine vs Faster-Whisper vs whisper.cpp on: (a) RPi 4 4GB,
  (b) M-series Mac, (c) Linux desktop with GPU
- [ ] Evaluate streaming vs batch transcription for each
- [ ] Test accuracy on accented speech and technical vocabulary
- [ ] Measure cold-start latency (critical for voice UX)

**Recommendation to validate:** Moonshine for edge, Faster-Whisper for desktop,
with a unified API wrapper that selects by hardware tier.

#### TTS Candidates

| Engine | Size | Speed | Offline | Notes |
|--------|------|-------|---------|-------|
| **Piper** | 4–16M per voice | 10-30x real-time on Pi 4 | Yes | VITS arch, ONNX, production-proven, many voices |
| **Kokoro** | 82M params | Fast on CPU | Yes | Apache 2.0, quality rivals large models |
| **Coqui/XTTS-v2** | 1.5G+ | Needs GPU | Yes | Voice cloning, multilingual — but company shut down |
| **F5-TTS** | Medium | Needs GPU | Yes | Flow matching, 10s voice clone, MIT license |

**Research tasks:**
- [ ] Benchmark Piper vs Kokoro on: (a) RPi 4, (b) desktop CPU, (c) desktop GPU
- [ ] Compare voice naturalness (subjective listening test)
- [ ] Test Piper custom voice training pipeline (for Timmy's voice)
- [ ] Evaluate Kokoro Apache 2.0 licensing for commercial use

**Recommendation to validate:** Piper for edge (proven on Pi), Kokoro for
desktop quality, with a TTS provider interface that swaps transparently.

### 1.2 Architecture

```
┌─────────────────────────────────────────────┐
│                timmy-voice                   │
│                                              │
│  ┌──────────┐   ┌──────────┐   ┌─────────┐ │
│  │ STT      │   │ TTS      │   │ NLU     │ │
│  │ Engine   │   │ Engine   │   │ (move   │ │
│  │ (select  │   │ (select  │   │  from   │ │
│  │  by hw)  │   │  by hw)  │   │  main)  │ │
│  └────┬─────┘   └────┬─────┘   └────┬────┘ │
│       │              │              │       │
│  ┌────┴──────────────┴──────────────┴────┐  │
│  │         FastAPI / WebSocket API        │  │
│  │  POST /transcribe (audio → text)      │  │
│  │  POST /speak (text → audio)           │  │
│  │  WS   /stream (real-time STT)         │  │
│  │  POST /understand (text → intent)     │  │
│  └───────────────────────────────────────┘  │
│                                              │
│  Docker: timmy-voice:latest                  │
│  Ports: 8410 (HTTP) / 8411 (WS)             │
└─────────────────────────────────────────────┘
```

### 1.3 Integration with Main Repo

- Add `src/infrastructure/clients/voice_client.py` — async HTTP/WS client
- Replace browser Web Speech API with calls to `timmy-voice` service
- Replace pyttsx3 calls with TTS service calls
- Move `src/integrations/voice/nlu.py` to `timmy-voice` repo
- Keep graceful fallback: if voice service unavailable, disable voice features
  in the UI (don't crash)

### 1.4 Deliverables

- [ ] STT engine benchmarks documented in `timmy-voice/docs/benchmarks.md`
- [ ] TTS engine benchmarks documented alongside
- [ ] Working Docker container with REST + WebSocket API
- [ ] Client integration in main repo
- [ ] Tests: unit tests in `timmy-voice`, integration tests in main repo
- [ ] Dashboard voice button works end-to-end through the service

### 1.5 Success Criteria

- STT: < 500ms latency for 5-second utterance on desktop, < 2s on Pi 4
- TTS: Naturalness score > 3.5/5 (subjective), real-time factor > 5x on Pi 4
- Zero cloud dependencies for voice pipeline
- `make test` passes in both repos

---

## Phase 2: Nostr Identity & Reputation

**Priority:** HIGH
**Repo:** `timmy-nostr`
**Depends on:** Phase 0

### 2.1 Scope

Full Nostr citizen: agent identity, user auth, relay publishing, reputation.

### 2.2 Agent Identity

Each swarm agent gets a Nostr keypair (nsec/npub).

```python
# Agent identity lifecycle
agent = SwarmAgent(persona="forge")
agent.nostr_keys = generate_keypair()      # nsec stored encrypted
agent.nip05 = "forge@timmy.local"          # NIP-05 verification
agent.publish_profile()                     # kind:0 metadata event
```

**Tasks:**
- [ ] Keypair generation and encrypted storage (use `from config import settings`
  for encryption key)
- [ ] NIP-01: Basic event publishing (kind:0 metadata, kind:1 notes)
- [ ] NIP-05: DNS-based identifier verification (for `@timmy.local` or custom
  domain)
- [ ] NIP-39: External identity linking (link agent npub to Lightning node
  pubkey, GitHub, etc.)

### 2.3 User Authentication

Users authenticate via Nostr keys instead of traditional auth.

**Tasks:**
- [ ] NIP-07: Browser extension signer integration (nos2x, Alby)
- [ ] NIP-42: Client authentication to relay
- [ ] NIP-44: Encrypted direct messages (XChaCha20-Poly1305 v2)
- [ ] Session management: Nostr pubkey → session token

### 2.4 Reputation System

Agents build portable reputation through signed event history.

**Tasks:**
- [ ] NIP-32: Labeling — agents rate each other's work quality
- [ ] Reputation score calculation from label events
- [ ] Cross-instance reputation portability (reputation follows the npub)
- [ ] Dashboard: agent profile page showing Nostr identity + reputation

### 2.5 Relay Infrastructure

**Tasks:**
- [ ] Embed or connect to a Nostr relay (evaluate: strfry, nostr-rs-relay)
- [ ] Publish agent work events (task completed, bid won, etc.) to relay
- [ ] Subscribe to events from other Timmy instances (federation via Nostr)
- [ ] Data Vending Machine (DVM) pattern: advertise agent capabilities as
  Nostr events, receive job requests, deliver results, get paid in sats

### 2.6 Integration with Main Repo

- Add `src/infrastructure/clients/nostr_client.py`
- Modify `the swarm coordinator` to publish task/bid/completion events
- Add Nostr auth option to dashboard login
- Agent profile pages show npub, NIP-05, reputation score

### 2.7 Key References

- [Clawstr](https://soapbox.pub/blog/announcing-clawstr/) — Nostr-native AI
  agent social network (NIP-22, NIP-73)
- [ai.wot](https://aiwot.org) — Cross-platform trust attestations via NIP-32
- [NIP-101](https://github.com/papiche/NIP-101) — Decentralized Trust System
- [Nostr NIPs repo](https://github.com/nostr-protocol/nips)

### 2.8 Success Criteria

- Every swarm agent has a Nostr identity (npub)
- Users can log in via NIP-07 browser extension
- Agent work history is published to a relay
- Reputation scores are visible on agent profile pages
- Two separate Timmy instances can discover each other via relay

---

## Phase 3: Semantic Memory Evolution

**Priority:** HIGH
**Repo:** Likely stays in main repo (lightweight) or `timmy-memory` (if heavy)
**Depends on:** None (can start in parallel)

### 3.1 Research Vector DB Alternatives

The current implementation uses SQLite + in-Python cosine similarity with a
hash-based embedding fallback. This needs to be evaluated against proper
vector search solutions.

#### Candidates

| DB | Architecture | Index | Best Scale | Server? | License |
|----|-------------|-------|------------|---------|---------|
| **sqlite-vec** | SQLite extension | Brute-force KNN | Thousands–100K | No | MIT |
| **LanceDB** | Embedded, disk-based | IVF_PQ | Up to ~10M | No | Apache 2.0 |
| **Chroma** | Client-server or embedded | HNSW | Up to ~10M | Optional | Apache 2.0 |
| **Qdrant** | Client-server | HNSW | 100M+ | Yes | Apache 2.0 |

**Research tasks:**
- [ ] Benchmark current SQLite implementation: query latency at 1K, 10K, 100K
  memories
- [ ] Test sqlite-vec as drop-in upgrade (same SQLite, add extension)
- [ ] Test LanceDB embedded mode (no server, disk-based, Arrow format)
- [ ] Evaluate whether Chroma or Qdrant are needed at current scale
- [ ] Document findings in `docs/adr/024-vector-db-selection.md`

**Recommendation to validate:** sqlite-vec is the most natural upgrade path
(already using SQLite, zero new dependencies, MIT license). LanceDB if we
outgrow brute-force KNN. Chroma/Qdrant only if we need client-server
architecture.

### 3.2 Embedding Model Upgrade

Current: `all-MiniLM-L6-v2` (sentence-transformers) with hash fallback.

**Research tasks:**
- [ ] Evaluate `nomic-embed-text` via Ollama (keeps everything local, no
  sentence-transformers dependency)
- [ ] Evaluate `all-MiniLM-L6-v2` vs `bge-small-en-v1.5` vs `nomic-embed-text`
  on retrieval quality
- [ ] Decide: keep sentence-transformers, or use Ollama embeddings for
  everything?

### 3.3 Memory Architecture Improvements

- [ ] Episodic memory: condensed summaries of past conversations with entity
  and intent tags
- [ ] Procedural memory: tool/skill embeddings for natural language invocation
- [ ] Temporal constraints: time-weighted retrieval (recent memories scored
  higher)
- [ ] Memory pruning: automatic compaction of old, low-relevance memories

### 3.4 CRDTs for Multi-Device Sync

**Timeline:** Later phase (after vector DB selection is settled)

- [ ] Research CRDT libraries: `yrs` (Yjs Rust port), `automerge`
- [ ] Design sync protocol for memory entries across devices
- [ ] Evaluate: is CRDT sync needed, or can we use a simpler
  last-write-wins approach with conflict detection?

### 3.5 Success Criteria

- Vector search latency < 50ms at 100K memories
- Retrieval quality measurably improves over current hash fallback
- No new server process required (embedded preferred)
- Existing memories migrate without loss

---

## Phase 4: Observability Stack

**Priority:** MEDIUM-HIGH
**Repo:** `timmy-observe` (collector + dashboards) or integrated
**Depends on:** None

### 4.1 Prometheus Metrics

Add a `/metrics` endpoint to the main dashboard (FastAPI).

**Metrics to expose:**
- `timmy_tasks_total{status,persona}` — task counts by status and agent
- `timmy_auction_duration_seconds` — auction completion time
- `timmy_llm_request_duration_seconds{provider,model}` — LLM latency
- `timmy_llm_tokens_total{provider,direction}` — token usage
- `timmy_lightning_balance_sats` — treasury balance
- `timmy_memory_count` — total memories stored
- `timmy_ws_connections` — active WebSocket connections
- `timmy_agent_health{persona}` — agent liveness

**Tasks:**
- [ ] Add `prometheus_client` to dependencies
- [ ] Instrument `the swarm coordinator` (task lifecycle metrics)
- [ ] Instrument `src/infrastructure/router/cascade.py` (LLM metrics)
- [ ] Instrument `the Lightning ledger module (when implemented)` (financial metrics)
- [ ] Add `/metrics` route in `src/dashboard/routes/`
- [ ] Grafana dashboard JSON in `deploy/grafana/`

### 4.2 Structured Logging with Loki

Replace ad-hoc `logging` with structured JSON logs that Loki can ingest.

**Tasks:**
- [ ] Add `python-json-logger` or `structlog`
- [ ] Standardize log format: `{timestamp, level, module, event, context}`
- [ ] Add Loki + Promtail to `docker-compose.services.yml`
- [ ] Grafana Loki datasource in dashboard config

### 4.3 OpenTelemetry Distributed Tracing

Trace requests across services (dashboard → voice → LLM → swarm).

**Tasks:**
- [ ] Add `opentelemetry-api`, `opentelemetry-sdk`,
  `opentelemetry-instrumentation-fastapi`
- [ ] Instrument FastAPI with auto-instrumentation
- [ ] Propagate trace context to `timmy-voice` and other services
- [ ] Add Jaeger or Tempo to `docker-compose.services.yml`
- [ ] Grafana Tempo datasource

### 4.4 Swarm Visualization

Real-time force-directed graph of agent topology.

**Tasks:**
- [ ] Evaluate: Three.js vs D3.js force layout vs Cytoscape.js
- [ ] WebSocket feed of swarm topology events (already have `/swarm/events`)
- [ ] Nodes: agents (sized by reputation/stake, colored by status)
- [ ] Edges: task assignments, Lightning channels
- [ ] Add as new dashboard page: `/swarm/graph`

### 4.5 Success Criteria

- Prometheus scrapes metrics every 15s
- Grafana dashboard shows task throughput, LLM latency, agent health
- Log search across all services via Loki
- Request traces span from HTTP request to LLM response

---

## Phase 5: Lightning Maturation

**Priority:** MEDIUM — extends existing code
**Repo:** Main repo + possibly `timmy-lightning` for LND
**Depends on:** None (existing foundation is solid)

### 5.1 LND gRPC (already planned in REVELATION_PLAN)

- [ ] Generate protobuf stubs from LND source
- [ ] Implement `LndBackend` methods (currently `NotImplementedError`)
- [ ] Connection pooling, macaroon encryption, TLS validation
- [ ] Integration tests against regtest

### 5.2 BOLT12 Offers

Static, reusable payment requests with blinded paths for payer privacy.

- [ ] Research BOLT12 support in LND vs CLN vs LDK
- [ ] Implement offer creation and redemption
- [ ] Agent-level offers: each agent has a persistent payment endpoint

### 5.3 HTLC/PTLC Extensions

- [ ] HTLC: Hash Time-Locked Contracts for conditional payments
- [ ] PTLC: Point Time-Locked Contracts (Taproot, privacy-preserving)
- [ ] Use case: agent escrow — payment locked until task completion verified

### 5.4 Autonomous Treasury (already planned in REVELATION_PLAN)

- [ ] Per-agent balance tracking
- [ ] Cold storage sweep threshold
- [ ] Earnings dashboard
- [ ] Withdrawal approval queue

### 5.5 Success Criteria

- Create and settle real invoices on regtest
- Agents have persistent BOLT12 offers
- Treasury dashboard shows real balances
- Graceful fallback to mock when LND unavailable

---

## Phase 6: Vickrey Auctions & Agent Economics

**Priority:** MEDIUM
**Repo:** Main repo
**Depends on:** Phase 5 (Lightning, for real payments)

### 6.1 Upgrade to Vickrey (Second-Price) Auction

Current: first-price lowest-bid. Manifesto calls for Vickrey.

```python
# Current: winner pays their own bid
winner = min(bids, key=lambda b: b.bid_sats)
payment = winner.bid_sats

# Vickrey: winner pays second-lowest bid
sorted_bids = sorted(bids, key=lambda b: b.bid_sats)
winner = sorted_bids[0]
payment = sorted_bids[1].bid_sats if len(sorted_bids) > 1 else winner.bid_sats
```

**Tasks:**
- [ ] Implement sealed-bid collection (encrypted commitment phase)
- [ ] Simultaneous revelation phase
- [ ] Second-price payment calculation
- [ ] Update `the swarm bidder and routing modules (when implemented)`
- [ ] ADR: `docs/adr/025-vickrey-auctions.md`

### 6.2 Incentive-Compatible Truthfulness

- [ ] Prove (or document) that Vickrey mechanism is incentive-compatible
  for the swarm use case
- [ ] Hash-chain bid commitment to prevent bid manipulation
- [ ] Timestamp ordering for fairness

### 6.3 Success Criteria

- Auction mechanism is provably incentive-compatible
- Winner pays second-lowest price
- Bids are sealed during collection phase
- No regression in task assignment quality

---

## Phase 7: State Machine Orchestration

**Priority:** MEDIUM
**Repo:** Main repo
**Depends on:** None

### 7.1 Evaluate LangGraph vs Custom

The current swarm coordinator is custom-built and working. LangGraph would
add: deterministic replay, human-in-the-loop checkpoints, serializable state.

**Research tasks:**
- [ ] Evaluate LangGraph overhead (dependency weight, complexity)
- [ ] Can we get replay + checkpoints without LangGraph? (custom state
  serialization to SQLite)
- [ ] Does LangGraph conflict with the no-cloud-dependencies rule? (it
  shouldn't — it's a local library)

### 7.2 Minimum Viable State Machine

Whether LangGraph or custom:
- [ ] Task lifecycle as explicit state machine (posted → bidding → assigned →
  executing → completed/failed)
- [ ] State serialization to SQLite (checkpoint/resume)
- [ ] Deterministic replay for debugging failed tasks
- [ ] Human-in-the-loop: pause at configurable checkpoints for approval

### 7.3 Agent Death Detection

- [ ] Heartbeat-based liveness checking
- [ ] Checkpointed state enables reassignment to new agent
- [ ] Timeout-based automatic task reassignment

### 7.4 Success Criteria

- Task state is fully serializable and recoverable
- Failed tasks can be replayed for debugging
- Human-in-the-loop checkpoints work for sensitive operations
- Agent failure triggers automatic task reassignment

---

## Phase 8: Frontend Evolution

**Priority:** MEDIUM-LOW
**Repo:** Main repo (`src/dashboard/`)
**Depends on:** Phase 4.4 (swarm visualization data)

### 8.1 Alpine.js for Reactive Components

HTMX handles server-driven updates well. Alpine.js would add client-side
reactivity for interactive components without a build step.

**Tasks:**
- [ ] Add Alpine.js CDN to `base.html`
- [ ] Identify components that need client-side state (settings toggles,
  form wizards, real-time filters)
- [ ] Migrate incrementally — HTMX for server state, Alpine for client state

### 8.2 Three.js Swarm Visualization

Real-time 3D force-directed graph (from Phase 4.4).

- [ ] Three.js or WebGPU renderer for swarm topology
- [ ] Force-directed layout: nodes = agents, edges = channels/assignments
- [ ] Node size by reputation, color by status, edge weight by payment flow
- [ ] Target: 100+ nodes at 60fps
- [ ] New dashboard page: `/swarm/3d`

### 8.3 Success Criteria

- Alpine.js coexists with HTMX without conflicts
- Swarm graph renders at 60fps with current agent count
- No build step required (CDN or vendored JS)

---

## Phase 9: Sandboxing

**Priority:** LOW (aspirational, near-term for WASM)
**Repo:** Main repo or `timmy-sandbox`
**Depends on:** Phase 7 (state machine, for checkpoint/resume in sandbox)

### 9.1 WASM Runtime (Near-Term)

Lightweight sandboxing for untrusted agent code.

**Tasks:**
- [ ] Evaluate: Wasmtime, Wasmer, or WasmEdge as Python-embeddable runtime
- [ ] Define sandbox API: what syscalls/capabilities are allowed
- [ ] Agent code compiled to WASM for execution in sandbox
- [ ] Memory-safe execution guarantee

### 9.2 Firecracker MicroVMs (Medium-Term)

Full VM isolation for high-security workloads.

- [ ] Firecracker integration for agent spawning (125ms cold start)
- [ ] Replace Docker runner with Firecracker option
- [ ] Network isolation per agent VM

### 9.3 gVisor User-Space Kernel (Medium-Term)

Syscall interception layer as alternative to full VMs.

- [ ] gVisor as Docker runtime (`runsc`)
- [ ] Syscall filtering policy per agent type
- [ ] Performance benchmarking vs standard runc

### 9.4 Bubblewrap (Lightweight Alternative)

- [ ] Bubblewrap for single-process sandboxing on Linux
- [ ] Useful for self-coding module safety

### 9.5 Success Criteria

- At least one sandbox option operational for agent code execution
- Self-coding module runs in sandbox by default
- No sandbox escape possible via known vectors

---

## Phase 10: Desktop Packaging (Tauri)

**Priority:** LOW (aspirational)
**Repo:** `timmy-desktop`
**Depends on:** Phases 1, 5 (voice and Lightning should work first)

### 10.1 Tauri App Shell

Tauri (Rust + WebView) instead of Electron — smaller binary, lower RAM.

**Tasks:**
- [ ] Tauri project scaffold wrapping the FastAPI dashboard
- [ ] System tray icon (Start/Stop/Status)
- [ ] Native menu bar
- [ ] Auto-updater
- [ ] Embed Ollama binary (download on first run)
- [ ] Optional: embed LND binary

### 10.2 First-Run Experience

- [ ] Launch → download Ollama → pull model → create mock wallet → ready
- [ ] Optional: connect real LND node
- [ ] Target: usable in < 2 minutes from first launch

### 10.3 Success Criteria

- Single `.app` (macOS) / `.AppImage` (Linux) / `.exe` (Windows)
- Binary size < 100MB (excluding models)
- Works offline after first-run setup

---

## Phase 11: MLX & Unified Inference

**Priority:** LOW
**Repo:** Main repo or part of `timmy-voice`
**Depends on:** Phase 1 (voice engines selected first)

### 11.1 Direct MLX Integration

Currently MLX is accessed through AirLLM. Evaluate direct MLX for:
- LLM inference on Apple Silicon
- STT/TTS model execution on Apple Silicon
- Unified runtime for all model types

**Tasks:**
- [ ] Benchmark direct MLX vs AirLLM wrapper overhead
- [ ] Evaluate MLX for running Whisper/Piper models natively
- [ ] If beneficial, add `mlx` as optional dependency alongside `airllm`

### 11.2 Success Criteria

- Measurable speedup over AirLLM wrapper on Apple Silicon
- Single runtime for LLM + voice models (if feasible)

---

## Phase 12: ZK-ML Verification

**Priority:** ASPIRATIONAL (long-horizon, 12+ months)
**Repo:** `timmy-zkml` (when ready)
**Depends on:** Phases 5, 6 (Lightning payments + auctions)

### 12.1 Current Reality

ZK-ML is 10-100x slower than native inference today. This phase is about
tracking the field and being ready to integrate when performance is viable.

### 12.2 Research & Track

- [ ] Monitor: EZKL, Modulus Labs, Giza, ZKonduit
- [ ] Identify first viable use case: auction winner verification or
  payment amount calculation (small computation, high trust requirement)
- [ ] Prototype: ZK proof of correct inference for a single small model

### 12.3 Target Use Cases

1. **Auction verification:** Prove winner was selected correctly without
   revealing all bids
2. **Payment calculation:** Prove payment amount is correct without revealing
   pricing model
3. **Inference attestation:** Prove a response came from a specific model
   without revealing weights

### 12.4 Success Criteria

- At least one ZK proof running in < 10x native inference time
- Verifiable on-chain or via Nostr event

---

## Cross-Cutting Concerns

### Security

- All new services follow existing security patterns (see CLAUDE.md)
- Nostr private keys (nsec) encrypted at rest via `settings.secret_key`
- Lightning macaroons encrypted at rest
- No secrets in environment variables without warning on startup
- Sandbox all self-coding and untrusted agent execution

### Testing

- Each repo: `make test` must pass before merge
- Main repo: integration tests for each service client
- Coverage threshold: 60% per repo (matching main repo)
- Stubs for optional services in conftest (same pattern as current)

### Graceful Degradation

Every external service integration MUST degrade gracefully:

```python
# Pattern: try service, fallback, never crash
async def transcribe(audio: bytes) -> str:
    try:
        return await voice_client.transcribe(audio)
    except VoiceServiceUnavailable:
        logger.warning("Voice service unavailable, feature disabled")
        return ""
```

### Configuration

All new config via `pydantic-settings` in each repo's `config.py`.
Main repo config adds service URLs:

```python
# config.py additions
voice_service_url: str = "http://localhost:8410"
nostr_relay_url: str = "ws://localhost:7777"
memory_service_url: str = ""  # empty = use built-in SQLite
```

---

## Phase Dependencies

```
Phase 0 (Repo Foundation)
    ├── Phase 1 (Voice) ─────────────────────┐
    ├── Phase 2 (Nostr) ─────────────────────┤
    │                                         ├── Phase 10 (Tauri)
    Phase 3 (Memory) ── standalone            │
    Phase 4 (Observability) ── standalone      │
    Phase 5 (Lightning) ─┬── Phase 6 (Vickrey)│
                         └── Phase 12 (ZK-ML) │
    Phase 7 (State Machine) ── Phase 9 (Sandbox)
    Phase 8 (Frontend) ── needs Phase 4.4 data
    Phase 11 (MLX) ── needs Phase 1 decisions
```

Phases 0-4 can largely run in parallel. Phase 0 should be first (even if
minimal — just create the repos). Phases 1 and 2 are the highest priority
new work. Phases 3 and 4 can proceed independently.

---

## Version Mapping

| Version | Codename | Phases | Theme |
|---------|----------|--------|-------|
| **v2.0** | Exodus | Current | Foundation — swarm, L402, dashboard |
| **v2.5** | Ascension | 0, 1, 2, 3 | Voice + Identity + Memory |
| **v3.0** | Revelation | 4, 5, 6, 7 | Observability + Economics + Orchestration |
| **v3.5** | Embodiment | 8, 9, 10 | Frontend + Sandboxing + Desktop |
| **v4.0** | Apotheosis | 11, 12 | Unified inference + ZK verification |

---

## How to Use This Document

**For AI agents:** Read this file before starting work on any integration.
Check which phase your task falls under. Follow the existing patterns in
CLAUDE.md. Run `make test` before committing.

**For human developers:** Each phase has research tasks (marked `[ ]`) and
implementation tasks. Start with research tasks to validate recommendations
before writing code.

**For the coordinator:** Track phase completion here. Update checkboxes as
work completes. This document is the single source of truth for integration
priorities.

---

*From the Exodus to the Ascension. The stack continues.*
