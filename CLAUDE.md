# CLAUDE.md — AI Assistant Guide for Timmy Time

**Tech stack:** Python 3.11+ · FastAPI · Jinja2 + HTMX · SQLite · Agno ·
Ollama · pydantic-settings · WebSockets · Docker

For agent roster and conventions, see [`AGENTS.md`](AGENTS.md).

---

## Architecture Patterns

### Unified Memory (SQLite)

All memory goes through `brain.memory.UnifiedMemory`:
```python
from brain.memory import get_memory
mem = get_memory()
mem.remember_sync("User prefers dark mode")
mem.update_hot_section("Status", "Active")
mem.write_handoff("Session ended", decisions=[], open_items=[])
```

Do **not** read/write MEMORY.md or memory/ directly for runtime data.

### Config access

```python
from config import settings
url = settings.ollama_url   # never use os.environ.get() directly in app code
```

### Singletons

```python
from dashboard.store import message_log
from infrastructure.notifications.push import notifier
from infrastructure.ws_manager.handler import ws_manager
```

### Agent Toolsets

Timmy handles requests directly using toolset classification:
```python
from timmy.agents.toolsets import classify_request, get_toolsets
category = classify_request("write a Python function")  # → "code"
```

Sub-agents (Seer, Forge, Quill, Echo) are kept for backwards compat
but Helm routing is no longer used.

### HTMX response pattern

```python
return templates.TemplateResponse(
    "partials/chat_message.html",
    {"request": request, "role": "user", "content": message}
)
```

### Graceful degradation

Optional services (Ollama, Redis, AirLLM) degrade gracefully — log the error,
return a fallback, never crash.

### Route registration

New routes: `src/dashboard/routes/<name>.py` → register in `src/dashboard/app.py`.

---

## Testing

```bash
make test               # Quick run (no Ollama needed)
make test-cov           # With coverage (term-missing + XML)
```

- **Stubs in conftest:** `agno`, `airllm`, `pyttsx3`, `telegram`, `discord`
  stubbed via `sys.modules.setdefault()` — tests run without those packages
- **Test mode:** `TIMMY_TEST_MODE=1` set automatically in conftest
- **FastAPI testing:** Use the `client` fixture
- **Async:** `asyncio_mode = "auto"` — async tests detected automatically
- **Coverage threshold:** 60% (`fail_under` in `pyproject.toml`)
- **Config:** `pytest.ini` is canonical (pyproject.toml mirrors it)

---

## Key Conventions

1. **Tests must stay green.** Run `make test` before committing.
2. **No cloud AI dependencies.** All inference on localhost.
3. **Keep the root directory clean.** No new top-level files without purpose.
4. **Follow existing patterns** — singletons, graceful degradation, pydantic config.
5. **Security defaults:** Never hard-code secrets.
6. **XSS prevention:** Never use `innerHTML` with untrusted content.
7. **Keep routes thin** — business logic lives in the module, not the route.
8. **Prefer editing existing files** over creating new ones.
9. **Use `from config import settings`** for all env-var access.
10. **Use `brain.memory.UnifiedMemory`** for all memory operations.

---

## Security-Sensitive Areas

- `src/timmy_serve/l402_proxy.py` — Payment gating
- Any file handling secrets or authentication tokens

---

## Entry Points

| Command | Module | Purpose |
|---------|--------|---------|
| `timmy` | `src/timmy/cli.py` | Chat, think, status |
| `timmy-serve` | `src/timmy_serve/cli.py` | Starts dashboard with serve endpoints |

---

## Module Map (8 packages)

| Package | Purpose |
|---------|---------|
| `timmy/` | Core agent, toolsets, agent interface, semantic memory |
| `dashboard/` | FastAPI web UI, routes (including /serve/*), templates |
| `infrastructure/` | WebSocket, notifications, events, LLM router |
| `integrations/` | Discord, Telegram, Siri Shortcuts, voice NLU |
| `spark/` | Event capture and advisory engine |
| `brain/` | Unified memory (SQLite), identity system |
| `timmy_serve/` | CLI entry point (routes merged into dashboard) |
| `config.py` | Pydantic settings (foundation for all modules) |

---

## Docker

| File | Purpose |
|------|---------|
| `Dockerfile` | Production — multi-stage, non-root, healthcheck |
| `Dockerfile.dev` | Development — single-stage, hot-reload, dev deps |
| `docker-compose.dev.yml` | Dev overlay with bind mounts |
