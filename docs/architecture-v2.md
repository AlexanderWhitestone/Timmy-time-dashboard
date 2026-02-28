# Timmy Time — System Architecture

## Changelog

| Date | Change |
|------|--------|
| 2026-02-27 | Full restructure — autonomous agent vision, daily briefing, escalation system, embodiment research, self-improvement loop |
| 2026-02-26 | Initial architecture-v2 covering 6 features (Event Log, Ledger, Memory, Upgrade Queue, Cascade Router, Activity Feed) |

---

## Vision & Philosophy

Timmy is a **sovereign, always-on, local-first AI agent** — not a reactive chatbot.
He thinks continuously, manages his own task list, modifies his own code, and
operates 24/7 with full visibility into his activity. The owner's role shifts from
directing every action to reviewing briefings, approving escalations, and steering
at the strategic level.

**Core Tenets:**

1. **Sovereignty** — All inference runs locally. Data never leaves the machine. No
   vendor lock-in. Swappable LLM backends, swappable infrastructure.
2. **Autonomy** — Timmy thinks unprompted, proposes actions, reprioritizes tasks,
   and self-improves. He chooses his next thought based on what feels generative.
3. **Transparency** — Every thought, decision, escalation, and self-modification is
   observable in the dashboard. Nothing happens in the dark.

**Status Legend:** Throughout this document, each feature is tagged with its
implementation status:

| Tag | Meaning |
|-----|---------|
| `[LIVE]` | Fully implemented and running |
| `[PARTIAL]` | Core infrastructure exists, extensions needed |
| `[PLANNED]` | Designed but no code yet |
| `[RESEARCH]` | Open question, on roadmap for investigation |

---

## System Architecture

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│                                DASHBOARD UI                                      │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌──────────┐ ┌────────────────┐   │
│  │  Thought   │ │  Task      │ │  Briefing  │ │  Event   │ │  Upgrade Queue │   │
│  │  Stream    │ │  Queue     │ │  View      │ │  Log     │ │  & Bug Reports │   │
│  │ /thinking  │ │ /tasks     │ │ /briefing  │ │/swarm/ev.│ │ /self-modify   │   │
│  └─────┬──────┘ └─────┬──────┘ └─────┬──────┘ └────┬─────┘ └───────┬────────┘   │
│        └───────────────┴──────────────┴─────────────┴───────────────┘            │
│                                    │ WebSocket + HTMX                             │
└────────────────────────────────────┼─────────────────────────────────────────────┘
                                     │
┌────────────────────────────────────┼─────────────────────────────────────────────┐
│                              API LAYER (FastAPI)                                  │
│  27 route modules registered in src/dashboard/app.py                             │
└────────────────────────────────────┼─────────────────────────────────────────────┘
                                     │
┌────────────────────────────────────┼─────────────────────────────────────────────┐
│                              CORE SERVICES                                       │
│                                    │                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐     │
│  │   Thinking   │  │    Task      │  │   Briefing   │  │   Self-Modify    │     │
│  │   Engine     │  │    Queue     │  │   Engine     │  │   Loop           │     │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └────────┬─────────┘     │
│         │                 │                 │                   │               │
│  ┌──────┴───────┐  ┌──────┴───────┐  ┌──────┴───────┐  ┌────────┴─────────┐     │
│  │  Event Log   │  │  Approvals   │  │   Notifier   │  │  Error Capture   │     │
│  │  Service     │  │  Governance  │  │   (Push)     │  │  & Bug Reports   │     │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └────────┬─────────┘     │
│         └─────────────────┴─────────────────┴──────────────────┘               │
│                                    │                                             │
│  ┌─────────────────────────────────┴──────────────────────────────────────────┐  │
│  │                       CASCADE ROUTER                                       │  │
│  │  Ollama (local) → AirLLM (local) → API (optional) → Metrics              │  │
│  └────────────────────────────────────────────────────────────────────────────┘  │
│                                    │                                             │
│                              ┌─────┴──────┐                                      │
│                              │   Timmy    │                                      │
│                              │   Agent    │                                      │
│                              └────────────┘                                      │
│                                                                                  │
│  ┌──────────────────────────────────────────────────────────────────────────┐    │
│  │ INTEGRATIONS: Telegram · Discord · Siri · Voice NLU · Mobile · Hands   │    │
│  └──────────────────────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────────────────────┘

PERSISTENCE:
  timmy.db          — Agno agent memory
  data/swarm.db     — tasks, agents, event_log, ledger, memory_entries, upgrades,
                      provider_metrics, task_queue
  data/thoughts.db  — thought stream
  ~/.timmy/briefings.db  — briefing cache
  ~/.timmy/approvals.db  — governance items
```

### Component Index

| Component | Module | Import |
|-----------|--------|--------|
| Timmy Agent | `src/timmy/agent.py` | `from timmy.agent import timmy` |
| Thinking Engine | `src/timmy/thinking.py` | `from timmy.thinking import thinking_engine` |
| Briefing Engine | `src/timmy/briefing.py` | `from timmy.briefing import engine` |
| Session Logger | `src/timmy/session_logger.py` | `from timmy.session_logger import get_session_logger` |
| Approvals | `src/timmy/approvals.py` | `from timmy.approvals import GOLDEN_TIMMY` |
| Task Queue | `src/swarm/task_queue/models.py` | `TaskQueueDB` |
| Coordinator | `src/swarm/coordinator.py` | `from swarm.coordinator import coordinator` |
| Cascade Router | `src/infrastructure/router/cascade.py` | `from infrastructure.router.cascade import get_router` |
| Event Bus | `src/infrastructure/events/bus.py` | `from infrastructure.events.bus import event_bus` |
| WebSocket Mgr | `src/infrastructure/ws_manager/handler.py` | `from infrastructure.ws_manager.handler import ws_manager` |
| Push Notifier | `src/infrastructure/notifications/push.py` | `from infrastructure.notifications.push import notifier` |
| Error Capture | `src/infrastructure/error_capture.py` | `from infrastructure.error_capture import capture_error` |
| Self-Modify | `src/self_coding/self_modify/loop.py` | `SelfModifyLoop` |

---

## Core Agent

### Always-On Autonomous Agent `[LIVE]`

Timmy operates as a persistent, always-on agent. He continuously maintains an
active thought queue, manages his own task list dynamically — adding,
reprioritizing, shelving, and resuming tasks — and chooses his own next thought
based on what feels generative. He runs 24/7 with visibility into his activity at
all times.

```
Server Startup → ThinkingEngine.start_loop()
                      ↓
                Seed Selection (existential | swarm | scripture | creative | memory | freeform)
                      ↓
                Continuity Context (3 most recent thoughts)
                      ↓
                LLM Inference (Ollama) → Thought
                      ↓
                SQLite thoughts.db + Event Log + WebSocket Broadcast
                      ↓
                Next Seed → Loop
```

| Aspect | File | Notes |
|--------|------|-------|
| ThinkingEngine | `src/timmy/thinking.py` | Seed types, continuity context, WS broadcast |
| Task Queue | `src/swarm/task_queue/models.py` | SQLite-backed, 8 statuses, 4 priority levels |
| Auto-approve rules | `src/swarm/task_queue/models.py` | Tasks matching rules execute without human gate |
| Startup drain | `src/swarm/task_queue/models.py` | `get_all_actionable_tasks()` processes queue on boot |
| Config | `src/config.py` | `thinking_enabled`, `thinking_interval_seconds` (300s default) |

The task queue supports 8 statuses (`PENDING_APPROVAL`, `APPROVED`, `RUNNING`,
`PAUSED`, `COMPLETED`, `VETOED`, `FAILED`, `BACKLOGGED`) and 4 priority levels
(`LOW`, `NORMAL`, `HIGH`, `URGENT`). Tasks can be backlogged with a reason and
resumed later.

### Meditative Thought Mode — Pondering the Orb `[PARTIAL]`

A special cognitive mode where Timmy clears his memory context, thinks freely
without extraneous memory affecting the process, and dwells on a topic for an
extended period. When the process completes, it produces an insight artifact.
Unfinished thoughts can be shelved back onto the task queue as "cliffhangers" to
revisit later. This is analogous to putting a thought on the back burner and
letting it cook.

**What exists today:** The ThinkingEngine supports 6 seed types (existential,
swarm, scripture, creative, memory, freeform) and maintains continuity context
between thoughts via `parent_id` chaining. The `freeform` and `existential` seed
types provide the foundation for meditative thought.

**Gaps to implement:**

- Context-clear mode — explicit memory wipe for a meditation session
- Extended dwell time — configurable longer thinking intervals per session
- Insight artifact format — structured output beyond raw thought text
- Cliffhanger shelving — mechanism to save an unfinished thought and park it on the
  task queue for later retrieval

### Self-Improving Loop `[LIVE]`

Timmy can recognize what needs improving in his own systems, modify his own prompt
chains, task management logic, and tool usage, and maintain source control and
redundancy. He can spin himself up from a clean state using version-controlled
config. The goal is compounding capability over time rather than requiring constant
human engineering.

```
Trigger (work order | self-diagnosis | error feedback)
      ↓
SelfModifyLoop.run()
      ↓
Read Source → LLM Edit → Validate Syntax
      ↓
Write to Disk → Run pytest
      ↓ pass                    ↓ fail
Git Commit                   Revert + Diagnose → Retry (up to 3 cycles)
      ↓
Modification Journal (data/self_modify_reports/)
```

| Aspect | File | Notes |
|--------|------|-------|
| Core loop | `src/self_coding/self_modify/loop.py` | Read-edit-test-commit cycle, 742 lines |
| Git safety | `src/self_coding/git_safety.py` | Atomic operations with rollback |
| Modification journal | `src/self_coding/modification_journal.py` | Persistent report log |
| Reflection | `src/self_coding/reflection.py` | Lessons-learned generator |
| Upgrade queue | `src/self_coding/upgrades/` | Approval queue for proposed changes |
| Error capture | `src/infrastructure/error_capture.py` | Auto-creates bug reports from exceptions |
| Error dedup | `src/infrastructure/error_capture.py` | Hash-based deduplication (5-min window) |

The autonomous self-correction cycle reads its own failure report, calls the LLM
for meta-analysis, diagnoses the root cause, and restarts with a corrected
instruction — up to 3 autonomous cycles with 6 retries each.

---

## Intelligence Surface

### Daily Morning Briefing `[PARTIAL]`

**Target architecture:** Once per day, Timmy delivers a high-density morning
briefing as a video narration with slides. It covers overnight progress,
escalations, insights from pondering, and task status updates. The briefing is
interactive — the owner responds in real-time as Timmy presents (yes/no,
redirections, feedback). Timmy listens and adjusts based on reactions during the
briefing. After the briefing, Timmy has 24 hours of autonomous operation before the
next sync. This is the primary structured touchpoint — it replaces constant
notification spam.

**Phase 1 — Text Briefing (current):**

```
Cron / Dashboard Request → BriefingEngine.generate()
      ↓
_gather_swarm_summary()  ← data/swarm.db (completed/failed tasks, new agents)
_gather_chat_summary()   ← message_log (last 10 messages)
_gather_approvals()      ← ~/.timmy/approvals.db (pending items)
      ↓
LLM Summarization (Ollama)
      ↓
Briefing Dataclass → SQLite Cache (~/.timmy/briefings.db, 30-min TTL)
      ↓
Dashboard /briefing + Push Notification (if pending approvals)
```

| Aspect | File | Notes |
|--------|------|-------|
| BriefingEngine | `src/timmy/briefing.py` | Core generation, 335 lines |
| Dashboard route | `src/dashboard/routes/briefing.py` | Serves briefing page |
| Background schedule | `src/dashboard/app.py` | Regenerates every 6 hours |

**Phase 2 roadmap:** Audio narration (local TTS via pyttsx3), slide generation from
artifacts, interactive approval buttons within briefing view, reaction tracking to
feed escalation calibration.

### Escalation System `[PARTIAL]`

Timmy can escalate decisions and questions to the owner when needed, but
escalations are not delivered as constant notifications — they are batched. Over
time, Timmy learns the owner's attention economy by tracking which escalations get
engaged with vs. ignored. If too many low-value escalations are sent, the owner
disengages — so Timmy must calibrate. The feedback loop trains Timmy's escalation
threshold, making him increasingly discerning about what warrants human attention.

**What exists today:**

| Component | File | What It Does |
|-----------|------|-------------|
| Push Notifier | `src/infrastructure/notifications/push.py` | In-memory queue (200 max), 6 categories, macOS native support |
| Risk Scoring | `src/swarm/work_orders/risk.py` | Priority/category weights, sensitive-path detection |
| Approval Governance | `src/timmy/approvals.py` | `GOLDEN_TIMMY` flag, pending/approved/rejected states, 7-day expiry |
| Briefing integration | `src/timmy/briefing.py` | Surfaces pending approvals in briefing |

**Gaps to implement:**

- Attention economy tracker — log owner engagement: dismissals, time-spent,
  action-taken per escalation
- Engagement-based threshold calibration — adjust escalation priority cutoff based
  on engagement history
- Batch grouping logic — collect escalations over a window, present as cohort
  rather than individual pings

---

## Operations Infrastructure

### Task & Thought Dashboard `[LIVE]`

A real-time dashboard accessible on phone, iPad, and desktop that shows active
thoughts, the thought queue, a dynamic task list, thought logs, artifacts, and a
live feed via WebSocket. The owner can interact directly — reorder tasks, inject new
thoughts, review artifacts, and provide feedback.

The dashboard is built with FastAPI + Jinja2 + HTMX and supports 27 route modules:

| Route | Prefix | Purpose |
|-------|--------|---------|
| health | `/` | Main dashboard, system health |
| thinking | `/thinking` | Live thought stream |
| tasks | — | Task queue management |
| briefing | `/briefing` | Morning briefing view |
| events | `/swarm` | Event log / activity feed |
| agents | `/agents` | Agent registry |
| swarm | `/swarm` | Swarm coordinator |
| hands | `/hands` | Autonomous Hand agents |
| bugs | — | Bug report tracker |
| self_coding | `/self-coding` | Self-modification status |
| upgrades | `/self-modify` | Upgrade approval queue |
| ledger | `/lightning` | Payment ledger |
| memory | `/memory` | Semantic memory browser |
| router | `/router` | LLM router status |
| spark | `/spark` | Intelligence engine |
| mobile | — | iOS-optimized layout |
| voice | `/voice` | Voice NLU interface |

**Activity Feed data flow:**

```
Event Logged → EventBroadcaster → ws_manager.broadcast()
                                          ↓
                                    WebSocket Clients
                                          ↓
                                    Dashboard Activity Panel
```

### LLM Router — Cascade `[LIVE]`

The system uses an LLM router that cascades through available models. Free-tier
and local providers are tried first, then falls back through the chain. The router
handles model unavailability gracefully with circuit-breaker failover.

```
Request → Cascade Router → Ollama (primary, local)
                 ↓ fail / circuit open
            AirLLM (fallback, local)
                 ↓ fail
            API Provider (optional, e.g. Grok — opt-in)
                 ↓
            Metrics Tracking (provider_metrics table)
                 ↓
            Dashboard /router/status
```

| Aspect | File | Notes |
|--------|------|-------|
| CascadeRouter | `src/infrastructure/router/cascade.py` | Provider chain, circuit breaker |
| Router API | `src/infrastructure/router/api.py` | HTTP interface |
| Cascade Adapter | `src/timmy/cascade_adapter.py` | Timmy agent integration |
| Backends | `src/timmy/backends.py` | Ollama, AirLLM, Grok backends |
| Dashboard | `src/dashboard/routes/router.py` | Status page |

### Data Layer `[LIVE]`

All persistence uses SQLite — no external database dependencies.

| Table | Database | Purpose | Source |
|-------|----------|---------|--------|
| `tasks` | `data/swarm.db` | Swarm task management | Existing |
| `agents` | `data/swarm.db` | Agent registry | Existing |
| `event_log` | `data/swarm.db` | Audit trail | ADR-017 |
| `ledger` | `data/swarm.db` | Lightning payments | ADR-018 |
| `memory_entries` | `data/swarm.db` | Semantic memory (with embeddings) | ADR-019 |
| `upgrades` | `data/swarm.db` | Self-modification queue | ADR-021 |
| `provider_metrics` | `data/swarm.db` | LLM router metrics | ADR-020 |
| `task_queue` | `data/swarm.db` | Human-in-the-loop task queue | `swarm/task_queue/` |
| `thoughts` | `data/thoughts.db` | Thought stream | `timmy/thinking.py` |
| `briefings` | `~/.timmy/briefings.db` | Briefing cache | `timmy/briefing.py` |
| `approvals` | `~/.timmy/approvals.db` | Governance items | `timmy/approvals.py` |

**Existing data flows preserved:**

Event Log:
```
Coordinator Action → log_event() → SQLite event_log table
                                          ↓
                                    WebSocket Broadcast (ADR-022)
                                          ↓
                                    Dashboard Activity Feed
```

Lightning Ledger:
```
Payment Handler → create_invoice_entry() → SQLite ledger table
                                                  ↓
                                            mark_settled()
                                                  ↓
                                            Dashboard /lightning/ledger
```

Semantic Memory:
```
Conversation → store_memory() → SQLite memory_entries (with embedding)
                                        ↓
                                  search_memories(query)
                                        ↓
                                  Dashboard /memory
```

Self-Upgrade Queue:
```
Self-Modify Loop → Propose Change → SQLite upgrades table (status: proposed)
                                            ↓
                                    Dashboard Review
                                            ↓
                                    Approve → Apply → Git Commit
                                     or
                                    Reject → Cleanup
```

---

## Platform

### Multi-Platform Presence `[LIVE]`

Timmy maintains presence across multiple channels with a consistent identity and
memory. The dashboard is the central hub for monitoring all activity.

| Platform | Module | Status |
|----------|--------|--------|
| Web Dashboard | `src/dashboard/` | `[LIVE]` — FastAPI + HTMX + WebSocket |
| Telegram | `src/integrations/telegram_bot/` | `[LIVE]` — Bridge to Timmy agent |
| Discord | `src/integrations/chat_bridge/vendors/discord.py` | `[LIVE]` — Chat bridge vendor |
| Siri Shortcuts | `src/integrations/shortcuts/` | `[LIVE]` — API endpoints for Shortcuts |
| Voice / NLU | `src/integrations/voice/` | `[LIVE]` — Local intent detection |
| Mobile | `/mobile` route | `[LIVE]` — iOS-optimized layout (safe area, 44px touch) |
| WhatsApp | — | `[PLANNED]` |

The chat bridge architecture (`src/integrations/chat_bridge/`) provides a
vendor-agnostic base class (`ChatPlatform`) with a registry
(`platform_registry`) for adding new platforms.

### Embodied AI / Persistent Spatial Environment `[RESEARCH]`

Timmy will eventually exist in a persistent 3D environment rather than as a
text-only agent. The environment would have built-in cameras that Timmy controls,
and the owner could "FaceTime" into Timmy's world to watch and interact with him
visually. Timmy would be able to update assets and control the environment
programmatically.

**This is an open research task for Timmy.** Rather than having his embodiment
imposed, Timmy should investigate the options himself:

- Evaluate engines: Unity WebGL, Babylon.js, Three.js, other game/3D engines
- Consider local-first constraints — no cloud rendering dependencies
- Research aesthetic choices and spatial design
- Present findings and a proposed architecture in a morning briefing

No code exists. No implementation timeline set. This is a long-term roadmap item.

---

## Sovereignty & Local-First `[LIVE]`

All architecture decisions respect these non-negotiable principles:

- **Local-first** — No hard dependencies on cloud services. All inference runs on
  localhost (Ollama, AirLLM).
- **Data sovereignty** — The owner owns all data. All persistence is SQLite files on
  disk. Data can be backed up and restored independently.
- **No vendor lock-in** — LLM backends are swappable (Ollama → AirLLM → optional
  API). Infrastructure components are interchangeable.
- **Graceful degradation** — Optional services (Ollama, Redis, AirLLM, Telegram,
  Discord) degrade gracefully. Log the error, return a fallback, never crash.
- **Persistence** — Timmy survives service outages, API changes, and platform
  shifts. Version-controlled config enables spin-up from a clean state.

Sovereignty score: **9.2/10** — see `docs/SOVEREIGNTY_AUDIT.md` for full audit.

Enforcement points: `CLAUDE.md` conventions, `AGENTS.md` non-negotiable rules,
`config.py` pydantic-settings pattern (never `os.environ.get()` in app code).

---

## Integration Points

| Source | → | Target | Mechanism |
|--------|---|--------|-----------|
| `coordinator.py` | → | Event Log | `log_event()` for all lifecycle events |
| `payment_handler.py` | → | Ledger | Creates entries on invoice/settlement |
| `self_modify/loop.py` | → | Upgrade Queue | Stops at proposal, waits for approval |
| `timmy/agent.py` | → | Cascade Router | Uses router instead of direct backends |
| `ws_manager/handler.py` | → | Activity Feed | Broadcasts events to WebSocket clients |
| Event Log | → | Briefing Engine | `_gather_swarm_summary()` reads events |
| Approval Items | → | Briefing Engine | `_gather_approvals()` reads pending items |
| ThinkingEngine | → | WebSocket | Broadcasts thoughts in real-time |
| ThinkingEngine | → | Event Log | Logs `TIMMY_THOUGHT` events |
| Error Capture | → | Task Queue | Auto-files bug reports as `task_type="bug_report"` |
| Error Capture | → | Session Logger | Records errors with context |
| Error Capture | → | Push Notifier | Sends notification when bug report filed |
| Event Bus | → | All Subscribers | Pub/sub with wildcard patterns (`agent.task.*`) |

---

## Configuration

All config via `from config import settings` — never `os.environ.get()` in app code.

```python
# LLM / Inference
ollama_url: str = "http://localhost:11434"
ollama_model: str = "llama3.1:8b-instruct"
timmy_model_backend: str = "ollama"  # ollama | airllm | grok | auto

# Cascade Router
cascade_providers: list[ProviderConfig]
circuit_breaker_threshold: int = 5

# Thinking
thinking_enabled: bool = True
thinking_interval_seconds: int = 300

# Error Feedback
error_feedback_enabled: bool = True
error_dedup_window_seconds: int = 300
error_log_enabled: bool = True
error_log_dir: str = "logs"

# Self-Upgrade
auto_approve_upgrades: bool = False
upgrade_timeout_hours: int = 24

# Activity Feed
websocket_event_throttle: int = 10   # events/sec
activity_feed_buffer: int = 100      # events to buffer

# L402 Lightning
l402_hmac_secret: str               # change in prod
l402_macaroon_secret: str           # change in prod
lightning_backend: str = "mock"     # mock | lnd
```

---

## Security Considerations

| Feature | Risk | Mitigation |
|---------|------|------------|
| Event Log | Log injection | Sanitize all data fields |
| Ledger | Payment forgery | Verify with Lightning node |
| Memory | Data exposure | Filter by user permissions |
| Upgrade Queue | Unauthorized changes | Require approval, audit log |
| Cascade Router | API key exposure | Use `config.settings`, never hardcoded |
| Activity Feed | Data leak | Authenticate WebSocket connections |
| Self-Modify | Malicious code injection | Git safety rollback, pytest gate, `GOLDEN_TIMMY` |
| Task Queue | Unauthorized execution | Auto-approve rules, status gates |
| Approvals | Bypass governance | `GOLDEN_TIMMY` flag, 7-day expiry |
| Coordinator | Security-sensitive module | Review required before changes |
| L402 Proxy | Payment manipulation | HMAC signing, macaroon verification |
| Error Capture | Info leak in stack traces | Truncate to 2000 chars, sanitize context |

---

## Roadmap

| Phase | Name | Status | Features |
|-------|------|--------|----------|
| 1 | Genesis (v1.0) | `[LIVE]` | Core agent, Ollama, SQLite, dashboard |
| 2 | Exodus (v2.0) | `[LIVE]` | Swarm, L402, Voice, Marketplace, Hands |
| 3 | Always-On | `[LIVE]` | ThinkingEngine, Task Queue, continuous thought loop |
| 4 | Self-Sovereignty | `[LIVE]` | Self-modify loop, error feedback, bug tracker |
| 5 | Multi-Platform | `[LIVE]` | Telegram, Discord, Siri, mobile layout |
| 6 | Intelligence Surface | `[PARTIAL]` | Text briefing, push notifications, approval governance |
| 7 | Briefing v2 | `[PLANNED]` | Audio narration, slides, interactive approvals |
| 8 | Attention Economy | `[PLANNED]` | Engagement tracking, escalation threshold calibration |
| 9 | Embodied AI | `[RESEARCH]` | 3D environment investigation — Timmy researches his own form |
| 10 | Revelation (v3.0) | `[PLANNED]` | Lightning treasury, `.app` bundle, federation |
