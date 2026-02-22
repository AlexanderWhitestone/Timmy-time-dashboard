# AGENTS.md — Timmy Time Development Standards for AI Agents

This file is the authoritative reference for any AI agent (Claude, Kimi, Manus,
or future tools) contributing to this repository.  Read it first.  Every time.

---

## 1. Project at a Glance

**Timmy Time** is a local-first, sovereign AI agent system.  No cloud.  No telemetry.
Bitcoin Lightning economics baked in.

| Thing            | Value                                  |
|------------------|----------------------------------------|
| Language         | Python 3.11+                           |
| Web framework    | FastAPI + Jinja2 + HTMX                |
| Agent framework  | Agno (wraps Ollama or AirLLM)          |
| Persistence      | SQLite (`timmy.db`, `data/swarm.db`)   |
| Tests            | pytest — 228 passing, **must stay green** |
| Entry points     | `timmy`, `timmy-serve`, `self-tdd`     |
| Config           | pydantic-settings, reads `.env`        |

```
src/
  config.py             # Central settings (OLLAMA_URL, DEBUG, etc.)
  timmy/                # Core agent: agent.py, backends.py, cli.py, prompts.py
  dashboard/            # FastAPI app + routes + Jinja2 templates
    app.py
    store.py            # In-memory MessageLog singleton
    routes/             # agents, health, swarm, swarm_ws, marketplace,
    │                   # mobile, mobile_test, voice, voice_enhanced
    templates/          # base.html + page templates + partials/
  swarm/                # Multi-agent coordinator, registry, bidder, tasks, comms
  timmy_serve/          # L402 Lightning proxy, payment handler, TTS, CLI
  voice/                # NLU intent detection (regex-based, no cloud)
  websocket/            # WebSocket manager (ws_manager singleton)
  notifications/        # Push notification store (notifier singleton)
  shortcuts/            # Siri Shortcuts API endpoints
  self_tdd/             # Continuous test watchdog
tests/                  # One test_*.py per module, all mocked
static/style.css        # Dark mission-control theme (JetBrains Mono)
docs/                   # GitHub Pages site (docs/index.html)
```

---

## 2. Non-Negotiable Rules

1. **Tests must stay green.**  Run `make test` before committing.  If you break
   tests, fix them before you do anything else.
2. **No cloud dependencies.**  All computation must run on localhost.
3. **No new top-level files without purpose.**  Don't litter the root directory.
4. **Follow existing patterns** — singletons (`message_log`, `notifier`,
   `ws_manager`, `coordinator`), graceful degradation (try/except → fallback),
   pydantic-settings config.
5. **Security defaults:** Never hard-code secrets.  Warn at startup when defaults
   are in use (see `l402_proxy.py` and `payment_handler.py` for the pattern).
6. **XSS prevention:**  Never use `innerHTML` with untrusted content.  Use
   `textContent` or `innerText` for any user-controlled string in JS.

---

## 3. Per-Agent Assignments

### Claude (Anthropic)
**Strengths:** Architecture, scaffolding, iterative refinement, testing, docs, breadth.

**Best for:**
- Adding new subsystems from scratch
- Refactoring / code-quality passes
- Writing or fixing tests
- Updating documentation (README, AGENTS.md, inline comments)
- CI/CD and tooling
- Debugging tricky async or import issues

**Conventions to follow:**
- Prefer editing existing files over creating new ones
- Keep route files thin — business logic lives in the module, not the route
- Use `from config import settings` for all env-var access
- New routes go in `src/dashboard/routes/`, registered in `app.py`
- New templates extend `base.html`
- Always add a corresponding `tests/test_<module>.py`

**Avoid:**
- Large one-shot feature dumps (that's Kimi's lane)
- Touching `src/swarm/coordinator.py` for security work (that's Manus's lane)
- Committing with `--no-verify`

---

### Kimi (Moonshot AI)
**Strengths:** High-volume feature generation, rapid expansion, large context.

**Best for:**
- Big feature drops (new pages, new subsystems, new agent personas)
- Implementing the roadmap items listed below
- Generating boilerplate for new agents (Echo, Mace, Helm, Seer, Forge, Quill)

**Conventions to follow:**
- Deliver working code with accompanying tests (even if minimal)
- Match the dark Mission Control CSS theme — extend `static/style.css`
- New agents should follow the `SwarmNode` + `Registry` pattern in `src/swarm/`
- Lightning-gated endpoints follow the L402 pattern in `src/timmy_serve/l402_proxy.py`

**Avoid:**
- Touching CI/CD or pyproject.toml without coordinating
- Adding cloud API calls
- Removing existing tests

---

### Manus AI
**Strengths:** Precision security work, targeted bug fixes, coverage gap analysis.

**Best for:**
- Security audits (XSS, injection, secret exposure)
- Closing test coverage gaps for existing modules
- Performance profiling of specific endpoints
- Validating L402/Lightning payment flows

**Conventions to follow:**
- Scope tightly — one security issue per PR
- Every security fix must have a regression test
- Use `pytest-cov` output to identify gaps before writing new tests
- Document the vulnerability class in the PR description

**Avoid:**
- Large-scale refactors (that's Claude's lane)
- New feature work (that's Kimi's lane)
- Changing agent personas or prompt content

---

## 4. Architecture Patterns

### Singletons (module-level instances)
These are shared state — import them, don't recreate them:
```python
from dashboard.store import message_log        # MessageLog
from notifications.push import notifier        # PushNotifier
from websocket.handler import ws_manager       # WebSocketManager
from timmy_serve.payment_handler import payment_handler  # PaymentHandler
from swarm.coordinator import coordinator      # SwarmCoordinator
```

### Config access
```python
from config import settings
url = settings.ollama_url   # never os.environ.get() directly in route files
```

### HTMX pattern
Server renders HTML fragments.  Routes return `TemplateResponse` with a partial
template.  JS is minimal — no React, no Vue.
```python
return templates.TemplateResponse(
    "partials/chat_message.html",
    {"request": request, "role": "user", "content": message}
)
```

### Graceful degradation
```python
try:
    result = await some_optional_service()
except Exception:
    result = fallback_value   # log, don't crash
```

### Tests
- All heavy deps (`agno`, `airllm`, `pyttsx3`) are stubbed in `tests/conftest.py`
- Use `pytest.fixture` for shared state; prefer function scope
- Use `TestClient` from `fastapi.testclient` for route tests
- No real Ollama required — mock `agent.run()`

---

## 5. Running Locally

```bash
make install        # create venv + install dev deps
make test           # run full test suite
make dev            # start dashboard (http://localhost:8000)
make watch          # self-TDD watchdog (background, 60s interval)
make test-cov       # coverage report
```

Or manually:
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest                                          # all 228 tests
uvicorn dashboard.app:app --reload --host 0.0.0.0 --port 8000
```

---

## 6. Roadmap (v2 → v3)

These are unbuilt items — claim one per PR, coordinate via Issues:

**v2.0.0 — Exodus (in progress)**
- [ ] Implement Echo, Mace, Helm, Seer, Forge, Quill agent personas as Agno agents
- [ ] Real LND gRPC backend for `PaymentHandler` (replace mock)
- [ ] MCP tool integration for Timmy
- [ ] Marketplace frontend — wire up the existing `/marketplace` route to real data
- [ ] Persistent swarm state across restarts (currently in-memory)

**v3.0.0 — Revelation (planned)**
- [ ] Bitcoin Lightning treasury (agent earns and spends sats autonomously)
- [ ] Single `.app` bundle for macOS (no Python install required)
- [ ] Federation — multiple Timmy instances discover and bid on each other's tasks

---

## 7. File Conventions

| Pattern | Convention |
|---------|-----------|
| New route | `src/dashboard/routes/<name>.py` + register in `app.py` |
| New template | `src/dashboard/templates/<name>.html` extends `base.html` |
| New partial | `src/dashboard/templates/partials/<name>.html` |
| New subsystem | `src/<name>/` with `__init__.py` |
| New test file | `tests/test_<module>.py` |
| Secrets | Read via `os.environ.get("VAR", "default")` + startup warning if default |
| DB files | `.db` files go in project root or `data/` — never in `src/` |
