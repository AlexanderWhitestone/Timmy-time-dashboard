# CLAUDE.md — AI Assistant Guide for Timmy Time

This file provides context for AI assistants (Claude Code, Copilot, etc.)
working in this repository. Read this before making any changes.

For multi-agent development standards and agent-specific conventions, see
[`AGENTS.md`](AGENTS.md).

---

## Project Summary

**Timmy Time** is a local-first, sovereign AI agent system with a browser-based
Mission Control dashboard. No cloud AI — all inference runs on localhost via
Ollama (or AirLLM for large models). Bitcoin Lightning economics are built in
for API access gating.

**Tech stack:** Python 3.11+ · FastAPI · Jinja2 + HTMX · SQLite · Agno (agent
framework) · Ollama · pydantic-settings · WebSockets · Docker

---

## Quick Reference Commands

```bash
# Setup
make install            # Create venv + install dev deps
cp .env.example .env    # Configure environment

# Development
make dev                # Start dashboard at http://localhost:8000
make test               # Run full test suite (no Ollama needed)
make test-cov           # Tests + coverage report (terminal + XML)
make lint               # Run ruff or flake8

# Docker
make docker-build       # Build timmy-time:latest image
make docker-up          # Start dashboard container
make docker-agent       # Spawn one agent worker
make docker-down        # Stop all containers
```

---

## Project Layout

```
src/
  config.py              # Central pydantic-settings (all env vars)
  timmy/                 # Core agent: agent.py, backends.py, cli.py, prompts.py
  dashboard/             # FastAPI app + routes + Jinja2 templates
    app.py               # App factory, lifespan, router registration
    store.py             # In-memory MessageLog singleton
    routes/              # One file per route group (agents, health, swarm, etc.)
    templates/           # base.html + page templates + partials/
  swarm/                 # Multi-agent coordinator, registry, bidder, tasks, comms
    coordinator.py       # Central swarm orchestrator (security-sensitive)
    docker_runner.py     # Spawn agents as Docker containers
  timmy_serve/           # L402 Lightning proxy, payment handler, TTS, CLI
  spark/                 # Intelligence engine — events, predictions, advisory
  creative/              # Creative director + video assembler pipeline
  tools/                 # Git, image, music, video tools for persona agents
  lightning/             # Lightning backend abstraction (mock + LND)
  agent_core/            # Substrate-agnostic agent interface
  voice/                 # NLU intent detection (regex-based, local)
  ws_manager/            # WebSocket connection manager (ws_manager singleton)
  notifications/         # Push notification store (notifier singleton)
  shortcuts/             # Siri Shortcuts API endpoints
  telegram_bot/          # Telegram bridge
  self_tdd/              # Continuous test watchdog
tests/                   # One test_*.py per module, all mocked
static/                  # style.css + bg.svg (dark arcane theme)
docs/                    # GitHub Pages landing site
```

---

## Architecture Patterns

### Config access

All configuration goes through `src/config.py` using pydantic-settings:

```python
from config import settings
url = settings.ollama_url   # never use os.environ.get() directly in app code
```

Environment variables are read from `.env` automatically. See `.env.example` for
all available settings.

### Singletons

Core services are module-level singleton instances imported directly:

```python
from dashboard.store import message_log
from notifications.push import notifier
from ws_manager.handler import ws_manager
from timmy_serve.payment_handler import payment_handler
from swarm.coordinator import coordinator
```

### HTMX response pattern

Routes return Jinja2 template partials for HTMX requests:

```python
return templates.TemplateResponse(
    "partials/chat_message.html",
    {"request": request, "role": "user", "content": message}
)
```

### Graceful degradation

Optional services (Ollama, Redis, AirLLM) degrade gracefully — log the error,
return a fallback, never crash:

```python
try:
    result = await some_optional_service()
except Exception:
    result = fallback_value
```

### Route registration

New routes go in `src/dashboard/routes/<name>.py`, then register the router in
`src/dashboard/app.py`:

```python
from dashboard.routes.<name> import router as <name>_router
app.include_router(<name>_router)
```

---

## Testing

### Running tests

```bash
make test               # Quick run (pytest -q --tb=short)
make test-cov           # With coverage (term-missing + XML)
make test-cov-html      # With HTML coverage report
```

No Ollama or external services needed — all heavy dependencies are mocked.

### Test conventions

- **One test file per module:** `tests/test_<module>.py`
- **Stubs in conftest:** `agno`, `airllm`, `pyttsx3`, `telegram` are stubbed in
  `tests/conftest.py` using `sys.modules.setdefault()` so tests run without
  those packages installed
- **Test mode:** `TIMMY_TEST_MODE=1` is set automatically in conftest to disable
  auto-spawning of persona agents during tests
- **FastAPI testing:** Use the `client` fixture (wraps `TestClient`)
- **Database isolation:** SQLite files in `data/` are cleaned between tests;
  coordinator state is reset via autouse fixtures
- **Async:** `asyncio_mode = "auto"` in pytest config — async test functions
  are detected automatically
- **Coverage threshold:** CI fails if coverage drops below 60%
  (`fail_under = 60` in `pyproject.toml`)

### Adding a new test

```python
# tests/test_my_feature.py
from fastapi.testclient import TestClient

def test_my_endpoint(client):
    response = client.get("/my-endpoint")
    assert response.status_code == 200
```

---

## CI/CD

GitHub Actions workflow (`.github/workflows/tests.yml`):

- Runs on every push and pull request to all branches
- Python 3.11, installs `.[dev]` dependencies
- Runs pytest with coverage + JUnit XML output
- Publishes test results as PR comments and check annotations
- Uploads coverage XML as a downloadable artifact (14-day retention)

---

## Key Conventions

1. **Tests must stay green.** Run `make test` before committing.
2. **No cloud AI dependencies.** All inference runs on localhost.
3. **No new top-level files without purpose.** Keep the root directory clean.
4. **Follow existing patterns** — singletons, graceful degradation,
   pydantic-settings config.
5. **Security defaults:** Never hard-code secrets. Warn at startup when using
   default values.
6. **XSS prevention:** Never use `innerHTML` with untrusted content.
7. **Keep routes thin** — business logic lives in the module, not the route.
8. **Prefer editing existing files** over creating new ones.
9. **Use `from config import settings`** for all env-var access.
10. **Every new module gets a test:** `tests/test_<module>.py`.

---

## Entry Points

Three CLI commands are installed via `pyproject.toml`:

| Command | Module | Purpose |
|---------|--------|---------|
| `timmy` | `src/timmy/cli.py` | Chat, think, status commands |
| `timmy-serve` | `src/timmy_serve/cli.py` | L402-gated API server (port 8402) |
| `self-tdd` | `src/self_tdd/watchdog.py` | Continuous test watchdog |

---

## Environment Variables

Key variables (full list in `.env.example`):

| Variable | Default | Purpose |
|----------|---------|---------|
| `OLLAMA_URL` | `http://localhost:11434` | Ollama host |
| `OLLAMA_MODEL` | `llama3.2` | Model served by Ollama |
| `DEBUG` | `false` | Enable `/docs` and `/redoc` |
| `TIMMY_MODEL_BACKEND` | `ollama` | `ollama` / `airllm` / `auto` |
| `AIRLLM_MODEL_SIZE` | `70b` | `8b` / `70b` / `405b` |
| `L402_HMAC_SECRET` | *(change in prod)* | HMAC signing for invoices |
| `L402_MACAROON_SECRET` | *(change in prod)* | Macaroon signing |
| `LIGHTNING_BACKEND` | `mock` | `mock` / `lnd` |
| `SPARK_ENABLED` | `true` | Enable Spark intelligence engine |
| `TELEGRAM_TOKEN` | *(empty)* | Telegram bot token |

---

## Persistence

- `timmy.db` — Agno agent memory (SQLite, project root)
- `data/swarm.db` — Swarm registry + tasks (SQLite, `data/` directory)
- All `.db` files are gitignored — never commit database files

---

## Docker

Containers share a `data/` volume for SQLite. Container agents communicate with
the coordinator over HTTP (not in-memory `SwarmComms`):

```
GET  /internal/tasks    → list tasks open for bidding
POST /internal/bids     → submit a bid
```

`COORDINATOR_URL=http://dashboard:8000` is set automatically by docker-compose.

---

## Security-Sensitive Areas

- `src/swarm/coordinator.py` — requires review before changes
- `src/timmy_serve/l402_proxy.py` — Lightning payment gating
- `src/lightning/` — payment backend abstraction
- Any file handling secrets or authentication tokens
