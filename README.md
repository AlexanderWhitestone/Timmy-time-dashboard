# Timmy Time — Mission Control

[![Tests](https://github.com/AlexanderWhitestone/Timmy-time-dashboard/actions/workflows/tests.yml/badge.svg)](https://github.com/AlexanderWhitestone/Timmy-time-dashboard/actions/workflows/tests.yml)

A local-first, sovereign AI agent system.  Talk to Timmy, watch his swarm, gate API access with Bitcoin Lightning — all from a browser, no cloud AI required.

**[Live Docs →](https://alexanderwhitestone.github.io/Timmy-time-dashboard/)**

---

## What's built

| Subsystem | Description |
|-----------|-------------|
| **Timmy Agent** | Agno-powered agent (Ollama default, AirLLM optional for 70B/405B) |
| **Mission Control** | FastAPI + HTMX dashboard — chat, health, swarm, marketplace |
| **Swarm** | Multi-agent coordinator — spawn agents, post tasks, run Lightning auctions |
| **L402 / Lightning** | Bitcoin Lightning payment gating for API access (mock backend; LND scaffolded) |
| **Spark Intelligence** | Event capture, predictions, memory consolidation, advisory engine |
| **Creative Studio** | Multi-persona creative pipeline — image, music, video generation |
| **Tools** | Git, image, music, and video tools accessible by persona agents |
| **Voice** | NLU intent detection + TTS (pyttsx3, no cloud) |
| **WebSocket** | Real-time swarm live feed |
| **Mobile** | Responsive layout with full iOS safe-area and touch support |
| **Telegram** | Bridge Telegram messages to Timmy |
| **CLI** | `timmy`, `timmy-serve`, `self-tdd` entry points |

**Full test suite, 100% passing.**

---

## Prerequisites

**Python 3.11+**
```bash
python3 --version   # must be 3.11+
```
If not: `brew install python@3.11`

**Ollama** — runs the local LLM
```bash
brew install ollama
# or download from https://ollama.com
```

---

## Quickstart

```bash
# 1. Clone
git clone https://github.com/AlexanderWhitestone/Timmy-time-dashboard.git
cd Timmy-time-dashboard

# 2. Install
make install
# or manually: python3 -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"

# 3. Start Ollama (separate terminal)
ollama serve
ollama pull llama3.2

# 4. Launch dashboard
make dev
# opens at http://localhost:8000
```

---

## Common commands

```bash
make test       # run all tests (no Ollama needed)
make test-cov   # test + coverage report
make dev        # start dashboard (http://localhost:8000)
make watch      # self-TDD watchdog (60s poll, alerts on regressions)
```

Or with the bootstrap script (creates venv, tests, watchdog, server in one shot):
```bash
bash activate_self_tdd.sh
bash activate_self_tdd.sh --big-brain   # also installs AirLLM
```

---

## CLI

```bash
timmy chat "What is sovereignty?"
timmy think "Bitcoin and self-custody"
timmy status

timmy-serve start          # L402-gated API server (port 8402)
timmy-serve invoice        # generate a Lightning invoice
timmy-serve status
```

---

## Mobile access

The dashboard is fully mobile-optimized (iOS safe area, 44px touch targets, 16px
input to prevent zoom, momentum scroll).

```bash
# Bind to your local network
uvicorn dashboard.app:app --host 0.0.0.0 --port 8000 --reload

# Find your IP
ipconfig getifaddr en0    # Wi-Fi on macOS
```

Open `http://<your-ip>:8000` on your phone (same Wi-Fi network).

Mobile-specific routes:
- `/mobile` — single-column optimized layout
- `/mobile-test` — 21-scenario HITL test harness (layout, touch, scroll, notch)

---

## AirLLM — big brain backend

Run 70B or 405B models locally with no GPU, using AirLLM's layer-by-layer loading.
Apple Silicon uses MLX automatically.

```bash
pip install ".[bigbrain]"
pip install "airllm[mlx]"   # Apple Silicon only

timmy chat "Explain self-custody" --backend airllm --model-size 70b
```

Or set once in `.env`:
```bash
TIMMY_MODEL_BACKEND=auto
AIRLLM_MODEL_SIZE=70b
```

| Flag  | Parameters  | RAM needed |
|-------|-------------|------------|
| `8b`  | 8 billion   | ~16 GB     |
| `70b` | 70 billion  | ~140 GB    |
| `405b`| 405 billion | ~810 GB    |

---

## Configuration

```bash
cp .env.example .env
# edit .env
```

| Variable | Default | Purpose |
|----------|---------|---------|
| `OLLAMA_URL` | `http://localhost:11434` | Ollama host |
| `OLLAMA_MODEL` | `llama3.2` | Model served by Ollama |
| `DEBUG` | `false` | Enable `/docs` and `/redoc` |
| `TIMMY_MODEL_BACKEND` | `ollama` | `ollama` \| `airllm` \| `auto` |
| `AIRLLM_MODEL_SIZE` | `70b` | `8b` \| `70b` \| `405b` |
| `L402_HMAC_SECRET` | *(default — change in prod)* | HMAC signing key for macaroons |
| `L402_MACAROON_SECRET` | *(default — change in prod)* | Macaroon secret |
| `LIGHTNING_BACKEND` | `mock` | `mock` (production-ready) \| `lnd` (scaffolded, not yet functional) |

---

## Architecture

```
Browser / Phone
      │ HTTP + HTMX + WebSocket
      ▼
┌─────────────────────────────────────────┐
│             FastAPI (dashboard.app)      │
│  routes: agents, health, swarm,          │
│          marketplace, voice, mobile      │
└───┬─────────────┬──────────┬────────────┘
    │             │          │
    ▼             ▼          ▼
Jinja2        Timmy       Swarm
Templates     Agent       Coordinator
(HTMX)        │           ├─ Registry (SQLite)
              ├─ Ollama   ├─ AuctionManager (L402 bids)
              └─ AirLLM   ├─ SwarmComms (Redis / in-memory)
                          └─ SwarmManager (subprocess)
    │
    ├── Voice NLU + TTS (pyttsx3, local)
    ├── WebSocket live feed (ws_manager)
    ├── L402 Lightning proxy (macaroon + invoice)
    ├── Push notifications (local + macOS native)
    └── Siri Shortcuts API endpoints

Persistence: timmy.db (Agno memory), data/swarm.db (registry + tasks)
External:    Ollama :11434, optional Redis, optional LND gRPC
```

---

## Project layout

```
src/
  config.py           # pydantic-settings — all env vars live here
  timmy/              # Core agent (agent.py, backends.py, cli.py, prompts.py)
  dashboard/          # FastAPI app, routes, Jinja2 templates
  swarm/              # Multi-agent: coordinator, registry, bidder, tasks, comms
  timmy_serve/        # L402 proxy, payment handler, TTS, serve CLI
  spark/              # Intelligence engine — events, predictions, advisory
  creative/           # Creative director + video assembler pipeline
  tools/              # Git, image, music, video tools for persona agents
  lightning/          # Lightning backend abstraction (mock + LND)
  agent_core/         # Substrate-agnostic agent interface
  voice/              # NLU intent detection
  ws_manager/         # WebSocket connection manager
  notifications/      # Push notification store
  shortcuts/          # Siri Shortcuts endpoints
  telegram_bot/       # Telegram bridge
  self_tdd/           # Continuous test watchdog
tests/                # one test file per module, all mocked
static/style.css      # Dark mission-control theme (JetBrains Mono)
docs/                 # GitHub Pages landing page
AGENTS.md             # AI agent development standards ← read this
.env.example          # Environment variable reference
Makefile              # Common dev commands
```

---

## Troubleshooting

**`ollama: command not found`** — install from `brew install ollama` or ollama.com

**`connection refused` in chat** — run `ollama serve` in a separate terminal

**`ModuleNotFoundError: No module named 'sqlalchemy'`** — re-run install to pick up the updated `agno[sqlite]` dependency:
`make install`

**`ModuleNotFoundError: No module named 'dashboard'`** — activate the venv:
`source .venv/bin/activate && pip install -e ".[dev]"`

**Health panel shows DOWN** — Ollama isn't running; chat still works but returns
the offline error message

**L402 startup warnings** — set `L402_HMAC_SECRET` and `L402_MACAROON_SECRET` in
`.env` to silence them (required for production)

---

## For AI agents contributing to this repo

Read [`AGENTS.md`](AGENTS.md).  It covers per-agent assignments, architecture
patterns, coding conventions, and the v2→v3 roadmap.

---

## Roadmap

| Version | Name       | Status      | Milestone |
|---------|------------|-------------|-----------|
| 1.0.0   | Genesis    | ✅ Complete | Agno + Ollama + SQLite + Dashboard |
| 2.0.0   | Exodus     | 🔄 In progress | Swarm + L402 + Voice + Marketplace |
| 3.0.0   | Revelation | 📋 Planned  | Lightning treasury + single `.app` bundle |
