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
ollama pull llama3.2

make dev                  # http://localhost:8000
make test                 # no Ollama needed
```

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

Key variables: `OLLAMA_URL`, `OLLAMA_MODEL`, `TIMMY_MODEL_BACKEND`,
`L402_HMAC_SECRET`, `LIGHTNING_BACKEND`, `DEBUG`. Full list in `.env.example`.

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
