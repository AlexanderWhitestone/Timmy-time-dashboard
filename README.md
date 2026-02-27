# Timmy Time — Mission Control

[![Tests](https://github.com/AlexanderWhitestone/Timmy-time-dashboard/actions/workflows/tests.yml/badge.svg)](https://github.com/AlexanderWhitestone/Timmy-time-dashboard/actions/workflows/tests.yml)

A local-first, sovereign AI agent system. Talk to Timmy, watch his swarm, gate
API access with Bitcoin Lightning — all from a browser, no cloud AI required.

**[Live Docs →](https://alexanderwhitestone.github.io/Timmy-time-dashboard/)**

---

## Quick Start

```bash
git clone https://github.com/AlexanderWhitestone/Timmy-time-dashboard.git
cd Timmy-time-dashboard
make install              # create venv + install deps
cp .env.example .env      # configure environment

ollama serve              # separate terminal
ollama pull llama3.1:8b-instruct  # Required for reliable tool calling

make dev                  # http://localhost:8000
make test                 # no Ollama needed
```

**Note:** llama3.1:8b-instruct is used instead of llama3.2 because it is
specifically fine-tuned for reliable tool/function calling.
llama3.2 (3B) was found to hallucinate tool output consistently in testing.
Fallback: qwen2.5:14b if llama3.1:8b-instruct is not available.

---

## What's Here

| Subsystem | Description |
|-----------|-------------|
| **Timmy Agent** | Agno-powered agent (Ollama default, AirLLM optional for 70B/405B) |
| **Mission Control** | FastAPI + HTMX dashboard — chat, health, swarm, marketplace |
| **Swarm** | Multi-agent coordinator — spawn agents, post tasks, Lightning auctions |
| **L402 / Lightning** | Bitcoin Lightning payment gating for API access |
| **Spark** | Event capture, predictions, memory consolidation, advisory |
| **Creative Studio** | Multi-persona pipeline — image, music, video generation |
| **Hands** | 6 autonomous scheduled agents — Oracle, Sentinel, Scout, Scribe, Ledger, Weaver |
| **Self-Coding** | Codebase-aware self-modification with git safety |
| **Integrations** | Telegram bridge, Siri Shortcuts, voice NLU, mobile layout |

---

## Commands

```bash
make dev            # start dashboard (http://localhost:8000)
make test           # run all tests
make test-cov       # tests + coverage report
make lint           # run ruff/flake8
make docker-up      # start via Docker
make help           # see all commands
```

**CLI tools:** `timmy`, `timmy-serve`, `self-tdd`, `self-modify`

---

## Documentation

| Document | Purpose |
|----------|---------|
| [CLAUDE.md](CLAUDE.md) | AI assistant development guide |
| [AGENTS.md](AGENTS.md) | Multi-agent development standards |
| [.env.example](.env.example) | Configuration reference |
| [docs/](docs/) | Architecture docs, ADRs, audits |

---

## Configuration

```bash
cp .env.example .env
```

| Variable | Default | Purpose |
|----------|---------|---------|
| `OLLAMA_URL` | `http://localhost:11434` | Ollama host |
| `OLLAMA_MODEL` | `llama3.1:8b-instruct` | Model for tool calling. Use llama3.1:8b-instruct for reliable tool use; fallback to qwen2.5:14b |
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

## Project Layout

```
src/
  config.py           # pydantic-settings — all env vars live here
  timmy/              # Core agent (agent.py, backends.py, cli.py, prompts.py)
  hands/              # Autonomous scheduled agents (registry, scheduler, runner)
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
hands/                # Hand manifests — oracle/, sentinel/, etc.
tests/                # one test file per module, all mocked
static/style.css      # Dark mission-control theme (JetBrains Mono)
docs/                 # GitHub Pages landing page
AGENTS.md             # AI agent development standards ← read this
.env.example          # Environment variable reference
Makefile              # Common dev commands
```

---

## Mobile Access

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

## Hands — Autonomous Agents

Hands are scheduled, autonomous agents that run on cron schedules. Each Hand has a `HAND.toml` manifest, `SYSTEM.md` prompt, and optional `skills/` directory.

**Built-in Hands:**

| Hand | Schedule | Purpose |
|------|----------|---------|
| **Oracle** | 7am, 7pm UTC | Bitcoin intelligence — price, on-chain, macro analysis |
| **Sentinel** | Every 15 min | System health — dashboard, agents, database, resources |
| **Scout** | Every hour | OSINT monitoring — HN, Reddit, RSS for Bitcoin/sovereign AI |
| **Scribe** | Daily 9am | Content production — blog posts, docs, changelog |
| **Ledger** | Every 6 hours | Treasury tracking — Bitcoin/Lightning balances, payment audit |
| **Weaver** | Sunday 10am | Creative pipeline — orchestrates Pixel+Lyra+Reel for video |

**Dashboard:** `/hands` — manage, trigger, approve actions

**Example HAND.toml:**
```toml
[hand]
name = "oracle"
schedule = "0 7,19 * * *"  # Twice daily
enabled = true

[tools]
required = ["mempool_fetch", "price_fetch"]

[approval_gates]
broadcast = { action = "broadcast", description = "Post to dashboard" }

[output]
dashboard = true
channel = "telegram"
```

---

## AirLLM — Big Brain Backend

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

## CLI

```bash
timmy chat "What is sovereignty?"
timmy think "Bitcoin and self-custody"
timmy status

timmy-serve start          # L402-gated API server (port 8402)
timmy-serve invoice        # generate a Lightning invoice
timmy-serve status
```

Or with the bootstrap script (creates venv, tests, watchdog, server in one shot):
```bash
bash scripts/activate_self_tdd.sh
bash scripts/activate_self_tdd.sh --big-brain   # also installs AirLLM
```

---

## Troubleshooting

- **`ollama: command not found`** — `brew install ollama` or ollama.com
- **`connection refused`** — run `ollama serve` first
- **`ModuleNotFoundError`** — `source .venv/bin/activate && make install`
- **Health panel shows DOWN** — Ollama isn't running; chat returns offline message

---

## Roadmap

| Version | Name | Status |
|---------|------|--------|
| 1.0 | Genesis | Complete — Agno + Ollama + SQLite + Dashboard |
| 2.0 | Exodus | In progress — Swarm + L402 + Voice + Marketplace + Hands |
| 3.0 | Revelation | Planned — Lightning treasury + single `.app` bundle |
