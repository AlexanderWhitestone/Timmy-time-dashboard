# CLAUDE.md — AI Assistant Guide for Timmy Time

**Tech stack:** Python 3.11+ · FastAPI · Jinja2 + HTMX · SQLite · Agno ·
Ollama · pydantic-settings · WebSockets · Docker · Poetry

For agent roster and conventions, see [`AGENTS.md`](AGENTS.md).

---

## Quick Start

```bash
make install            # Install deps via Poetry
make dev                # Clean up + start dashboard at http://localhost:8000
make test               # Quick test run (no Ollama needed)
```

---

## Architecture Patterns

### Config access

```python
from config import settings
url = settings.ollama_url   # never use os.environ.get() directly in app code
```

All settings are defined in `src/config.py` via `pydantic-settings` (`BaseSettings`).
Environment variables and `.env` files are loaded automatically. Production mode
(`TIMMY_ENV=production`) enforces required secrets at startup.

### Singletons

```python
from dashboard.store import message_log
from infrastructure.notifications.push import notifier
from infrastructure.ws_manager.handler import ws_manager
from infrastructure.events.bus import event_bus
from infrastructure.router import get_router
```

### HTMX response pattern

```python
return templates.TemplateResponse(
    "partials/chat_message.html",
    {"request": request, "role": "user", "content": message}
)
```

Templates live in `src/dashboard/templates/`. Partials for HTMX fragments are in `templates/partials/`.

### Graceful degradation

Optional services (Ollama, Redis, AirLLM, Grok, Claude) degrade gracefully — log the error,
return a fallback, never crash.

### Route registration

New routes: create `src/dashboard/routes/<name>.py` → import and register in `src/dashboard/app.py` via `app.include_router()`.

### Middleware stack (order matters)

1. `RequestLoggingMiddleware` — outermost, captures all requests
2. `SecurityHeadersMiddleware` — CSP, X-Frame-Options, etc.
3. `CSRFMiddleware` — CSRF token validation (disabled in test mode via `TIMMY_DISABLE_CSRF=1`)
4. `TrustedHostMiddleware` / `CORSMiddleware` — standard FastAPI

Custom middleware lives in `src/dashboard/middleware/`.

---

## Project Layout

```
├── src/
│   ├── config.py              # Pydantic settings (foundation for all modules)
│   ├── brain/                  # Identity system, memory interface, embeddings
│   ├── dashboard/              # FastAPI web UI
│   │   ├── app.py              # App factory, lifespan, middleware, router registration
│   │   ├── middleware/         # CSRF, security headers, request logging
│   │   ├── routes/            # Route modules (20+ routers)
│   │   ├── templates/         # Jinja2 templates (base.html + pages + partials/)
│   │   ├── store.py           # In-memory message_log singleton
│   │   └── templating.py      # Shared Jinja2 templates instance
│   ├── infrastructure/         # Cross-cutting services
│   │   ├── events/            # Domain event bus and broadcaster
│   │   ├── models/            # Model registry (SQLite-backed)
│   │   ├── notifications/     # Push notification store
│   │   ├── openfang/          # OpenFang agent runtime client
│   │   ├── router/            # Cascade LLM router with circuit-breaker failover
│   │   └── ws_manager/        # WebSocket connection manager
│   ├── integrations/           # External platform bridges (all optional deps)
│   │   ├── chat_bridge/       # Vendor-agnostic chat abstraction (Discord impl)
│   │   ├── telegram_bot/      # Telegram bot bridge
│   │   ├── shortcuts/         # iOS Siri Shortcuts API metadata
│   │   └── voice/             # Local NLU intent detection (regex, no cloud)
│   ├── spark/                  # Event capture, EIDOS predictions, advisory engine
│   ├── timmy/                  # Core agent
│   │   ├── agent.py           # Main agent logic
│   │   ├── agent_core/        # Agent interface + Ollama adapter
│   │   ├── agents/            # Agent types (base, timmy)
│   │   ├── cli.py             # `timmy` CLI entry point
│   │   ├── memory/            # Vector store for semantic memory
│   │   ├── tools.py           # Agent tools
│   │   ├── tools_delegation/  # Task delegation tools
│   │   ├── tools_intro/       # Introductory tool definitions
│   │   ├── thinking.py        # Background thinking loop
│   │   └── briefing.py        # Morning briefing generator
│   └── timmy_serve/            # API server (port 8402)
│       ├── cli.py             # `timmy-serve` CLI entry point
│       ├── app.py             # FastAPI app for API server
│       └── l402_proxy.py      # Lightning L402 payment gating
├── tests/                      # Mirrors src/ structure
│   ├── conftest.py            # Fixtures, stubs, test-mode env vars
│   ├── conftest_markers.py    # Pytest marker definitions
│   ├── fixtures/              # Shared test fixtures
│   └── <module>/              # Per-module test directories
├── static/                     # Static files (CSS, JS, images)
├── docker/                     # Per-service Dockerfiles
├── deploy/                     # Production deployment (Caddy, cloud-init, ELK)
├── migrations/                 # Alembic DB migrations
├── scripts/                    # Utility scripts (pre-commit, security fixes)
├── docs/                       # Project documentation and ADRs
├── data/                       # Runtime data (SQLite DBs, images, models)
├── mobile-app/                 # Mobile app source
├── memory/                     # Memory/knowledge files
├── Makefile                    # All build/test/deploy commands
├── pyproject.toml              # Poetry config, pytest settings, coverage
└── docker-compose*.yml         # Dev, test, prod compose files
```

---

## Entry Points

| Command | Module | Purpose |
|---------|--------|---------|
| `timmy` | `src/timmy/cli.py` | Chat, think, status |
| `timmy-serve` | `src/timmy_serve/cli.py` | API server (port 8402) |
| `make dev` | `dashboard.app:app` | Dashboard via uvicorn (port 8000) |

---

## Module Map (8 packages)

| Package | Purpose | Key files |
|---------|---------|-----------|
| `config.py` | Pydantic settings (foundation for all modules) | Settings class, model fallback logic, startup validation |
| `timmy/` | Core agent, personas, agent interface, semantic memory | `agent.py`, `cli.py`, `thinking.py`, `tools.py` |
| `dashboard/` | FastAPI web UI, routes, templates, middleware | `app.py`, `routes/`, `templates/`, `middleware/` |
| `infrastructure/` | WebSocket, notifications, events, LLM router, OpenFang | `ws_manager/`, `router/`, `events/`, `openfang/` |
| `integrations/` | Discord, Telegram, Siri Shortcuts, voice NLU | `chat_bridge/`, `telegram_bot/`, `voice/` |
| `spark/` | Event capture, EIDOS predictions, advisory engine | `engine.py`, `eidos.py`, `advisor.py`, `memory.py` |
| `brain/` | Identity system, memory interface, embeddings | `client.py`, `embeddings.py`, `schema.py` |
| `timmy_serve/` | API server with L402 payment gating | `app.py`, `cli.py`, `l402_proxy.py` |

---

## Testing

```bash
make test               # Quick run (no Ollama needed)
make test-cov           # With coverage (term-missing + XML)
make test-unit          # Unit tests only (-m unit)
make test-integration   # Integration tests only (-m integration)
make test-fast          # Unit + integration combined
make test-functional    # Functional tests (real HTTP, no selenium)
make test-e2e           # End-to-end tests
make test-ci            # CI tests (excludes skip_ci, includes coverage)
make test-cov-html      # Coverage with HTML report → htmlcov/index.html
```

### Test configuration

- **Runner:** pytest with `pytest-xdist` (`-n auto --dist worksteal` by default)
- **Stubs in conftest:** `agno`, `airllm`, `pyttsx3`, `telegram`, `discord`, `pyzbar`, `requests`, `sentence_transformers`
  stubbed via `sys.modules.setdefault()` — tests run without those packages
- **Test mode env vars:** `TIMMY_TEST_MODE=1`, `TIMMY_DISABLE_CSRF=1`, `TIMMY_SKIP_EMBEDDINGS=1` set automatically in conftest
- **FastAPI testing:** Use the `client` fixture (wraps `TestClient`)
- **Database isolation:** `clean_database` fixture redirects all `DB_PATH` constants to `tmp_path`
- **Async:** `asyncio_mode = "auto"` — async tests detected automatically
- **Timeout:** 30s per test (`timeout = 30` in pyproject.toml)
- **Coverage threshold:** 60% (`fail_under` in `pyproject.toml`)
- **Markers:** `unit`, `integration`, `functional`, `e2e`, `dashboard`, `slow`, `selenium`, `docker`, `ollama`, `external_api`, `skip_ci`

### Key fixtures (conftest.py)

| Fixture | Scope | Purpose |
|---------|-------|---------|
| `client` | function | FastAPI `TestClient` with fresh app |
| `reset_message_log` | function (auto) | Clears in-memory chat log before/after each test |
| `clean_database` | function (auto) | Redirects DB paths to temp dir |
| `cleanup_event_loops` | function (auto) | Closes leftover asyncio loops |
| `db_connection` | function | In-memory SQLite with agents/tasks schema |
| `mock_ollama_client` | function | Mock Ollama client (generate, chat, list) |
| `mock_timmy_agent` | function | Mock Timmy agent (run, chat) |

### Docker testing

```bash
make test-docker                  # Tests in clean container
make test-docker ARGS="-k swarm"  # Filter tests in container
make test-docker-cov              # Coverage in container
make test-docker-functional       # Full-stack functional tests
make test-docker-down             # Tear down test containers
```

### Adding a new test

1. Create `tests/<module>/test_<feature>.py` (mirror source structure)
2. Use appropriate marker: `@pytest.mark.unit`, `@pytest.mark.integration`, etc.
3. Use `client` fixture for route tests, `mock_ollama_client` for LLM tests
4. Run `make test` to verify

---

## Docker & Deployment

### Local development with Docker

```bash
make up                 # Build + start everything in Docker
make up DEV=1           # Same, with hot-reload on file changes
make down               # Stop all containers
make logs               # Tail container logs
make fresh              # Full clean rebuild (no cached layers/volumes)
```

### Docker agent workers

```bash
make docker-build                     # Build timmy-time:latest image
make docker-up                        # Start dashboard container
make docker-agent                     # Add one agent worker
make docker-agent AGENT_NAME=Echo     # Named agent worker
make docker-shell                     # Bash shell in dashboard container
```

Container agents poll the coordinator HTTP API:
- `GET /internal/tasks` — list open tasks
- `POST /internal/bids` — submit a bid
- `COORDINATOR_URL=http://dashboard:8000` set by docker-compose

### Cloud deployment

```bash
make cloud-deploy       # One-click server setup (run as root)
make cloud-up           # Start production stack (Caddy + Ollama + Dashboard)
make cloud-update       # Pull latest code + rebuild
make cloud-scale N=4    # Scale agent workers
make cloud-pull-model MODEL=llama3.2  # Pull LLM model into Ollama
```

### Compose files

| File | Purpose |
|------|---------|
| `docker-compose.yml` | Base production stack |
| `docker-compose.dev.yml` | Dev overlay (hot-reload, bind mounts) |
| `docker-compose.test.yml` | Test containers |
| `docker-compose.prod.yml` | Production with Caddy reverse proxy |
| `docker-compose.logging.yml` | ELK stack overlay |

### Dockerfiles (in `docker/`)

| File | Purpose |
|------|---------|
| `Dockerfile.dashboard` | Main dashboard image |
| `Dockerfile.agent` | Agent worker image |
| `Dockerfile.ollama` | Ollama with pre-pulled models |
| `Dockerfile.openfang` | OpenFang agent runtime |
| `Dockerfile.test` | Test runner image |

---

## Code Quality

```bash
make lint               # Check formatting (black + isort, line-length=100)
make format             # Auto-format code
make type-check         # mypy (ignore-missing-imports)
make pre-commit-run     # Run all pre-commit checks
```

Pre-commit hook: `scripts/pre-commit-hook.sh` (install via `make install-hooks`).

---

## Key Conventions

1. **Tests must stay green.** Run `make test` before committing.
2. **No cloud AI dependencies.** All inference on localhost (Grok/Claude are opt-in overrides).
3. **Keep the root directory clean.** No new top-level files without purpose.
4. **Follow existing patterns** — singletons, graceful degradation, pydantic config.
5. **Security defaults:** Never hard-code secrets. Use `config.settings` for all env-var access.
6. **XSS prevention:** Never use `innerHTML` with untrusted content.
7. **Keep routes thin** — business logic lives in the module, not the route.
8. **Prefer editing existing files** over creating new ones.
9. **Use `from config import settings`** for all env-var access. Never use `os.environ.get()` in app code.
10. **New test files** must mirror the source structure under `tests/`.

---

## Security-Sensitive Areas

- `src/timmy_serve/l402_proxy.py` — Lightning L402 payment gating
- `src/config.py` — Secret validation (`l402_hmac_secret`, `l402_macaroon_secret`, API keys)
- `src/dashboard/middleware/csrf.py` — CSRF protection
- `src/dashboard/middleware/security_headers.py` — CSP and security headers
- Any file handling secrets or authentication tokens (Telegram, Discord, Anthropic, xAI)

---

## LLM Backend Configuration

The system supports multiple LLM backends controlled by `TIMMY_MODEL_BACKEND`:

| Value | Backend | Notes |
|-------|---------|-------|
| `ollama` (default) | Ollama local | Primary workhorse, free, unrestricted |
| `airllm` | AirLLM | Large models on Apple Silicon (MLX) or PyTorch |
| `grok` | xAI Grok | Premium cloud, L402 payment gating |
| `claude` | Anthropic Claude | Cloud fallback when Ollama offline |
| `auto` | Auto-detect | AirLLM on Apple Silicon if available, else Ollama |

Model fallback chain: user's `OLLAMA_MODEL` → `llama3.1:8b-instruct` → `qwen2.5:14b`.

---

## Useful Links

- **Dashboard:** http://localhost:8000 (dev) or via Docker
- **API server:** http://localhost:8402 (`timmy-serve`)
- **API docs:** http://localhost:8000/docs (when `DEBUG=true`)
- **Kibana:** http://localhost:5601 (when ELK stack is running)
- **Architecture docs:** `docs/architecture-v2.md`
- **Roadmap:** `docs/ROADMAP.md`
- **Security audit:** `docs/SECURITY.md`
- **Decision log:** `docs/DECISIONS.md`
