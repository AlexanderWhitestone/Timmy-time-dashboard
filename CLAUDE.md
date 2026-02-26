# CLAUDE.md — AI Assistant Guide for Timmy Time

**Tech stack:** Python 3.11+ · FastAPI · Jinja2 + HTMX · SQLite · Agno ·
Ollama · pydantic-settings · WebSockets · Docker

For agent roster and conventions, see [`AGENTS.md`](AGENTS.md).

---

## Architecture Patterns

### Config access

```python
from config import settings
url = settings.ollama_url   # never use os.environ.get() directly in app code
```

### Singletons

```python
from dashboard.store import message_log
from notifications.push import notifier
from ws_manager.handler import ws_manager
from swarm.coordinator import coordinator
```

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

---

## Security-Sensitive Areas

- `src/swarm/coordinator.py` — requires review before changes
- `src/timmy_serve/l402_proxy.py` — Lightning payment gating
- `src/lightning/` — payment backend abstraction
- Any file handling secrets or authentication tokens

---

## Entry Points

| Command | Module | Purpose |
|---------|--------|---------|
| `timmy` | `src/timmy/cli.py` | Chat, think, status |
| `timmy-serve` | `src/timmy_serve/cli.py` | L402-gated API server (port 8402) |
| `self-tdd` | `src/self_tdd/watchdog.py` | Continuous test watchdog |
| `self-modify` | `src/self_modify/cli.py` | Self-modification CLI |
