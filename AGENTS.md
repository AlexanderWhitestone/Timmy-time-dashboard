# AGENTS.md — Timmy Time Development Standards for AI Agents

This file is the authoritative reference for any AI agent contributing to
this repository.  Read it first.  Every time.

---

## 1. Project at a Glance

**Timmy Time** is a local-first, sovereign AI agent system.  No cloud.  No telemetry.
Bitcoin Lightning economics baked in.

| Thing            | Value                                              |
|------------------|----------------------------------------------------|
| Language         | Python 3.11+                                       |
| Web framework    | FastAPI + Jinja2 + HTMX                            |
| Agent framework  | Agno (wraps Ollama or AirLLM)                      |
| Persistence      | SQLite (`timmy.db`, `data/swarm.db`)               |
| Tests            | pytest — must stay green                           |
| Entry points     | `timmy`, `timmy-serve`, `self-tdd`                 |
| Config           | pydantic-settings, reads `.env`                    |
| Containers       | Docker — each agent can run as an isolated service |

```
src/
  config.py             # Central settings (OLLAMA_URL, DEBUG, etc.)
  timmy/                # Core agent: agent.py, backends.py, cli.py, prompts.py
  dashboard/            # FastAPI app + routes + Jinja2 templates
    app.py
    store.py            # In-memory MessageLog singleton
    routes/             # agents, health, swarm, swarm_ws, marketplace,
    │                   # mobile, mobile_test, voice, voice_enhanced,
    │                   # swarm_internal (HTTP API for Docker agents)
    templates/          # base.html + page templates + partials/
  swarm/                # Multi-agent coordinator, registry, bidder, tasks, comms
    docker_runner.py    # Spawn agents as Docker containers
  timmy_serve/          # L402 Lightning proxy, payment handler, TTS, CLI
  spark/                # Intelligence engine — events, predictions, advisory
  creative/             # Creative director + video assembler pipeline
  tools/                # Git, image, music, video tools for persona agents
  lightning/            # Lightning backend abstraction (mock + LND)
  agent_core/           # Substrate-agnostic agent interface
  voice/                # NLU intent detection (regex-based, no cloud)
  ws_manager/           # WebSocket manager (ws_manager singleton)
  notifications/        # Push notification store (notifier singleton)
  shortcuts/            # Siri Shortcuts API endpoints
  telegram_bot/         # Telegram bridge
  self_tdd/             # Continuous test watchdog
tests/                  # One test_*.py per module, all mocked
static/                 # style.css + bg.svg (arcane theme)
docs/                   # GitHub Pages site
```

---

## 2. Non-Negotiable Rules

1. **Tests must stay green.**  Run `make test` before committing.
2. **No cloud dependencies.**  All AI computation runs on localhost.
3. **No new top-level files without purpose.**  Don't litter the root directory.
4. **Follow existing patterns** — singletons, graceful degradation, pydantic-settings config.
5. **Security defaults:** Never hard-code secrets.  Warn at startup when defaults are in use.
6. **XSS prevention:**  Never use `innerHTML` with untrusted content.

---

## 3. Agent Roster

Agents are divided into two tiers: **Builders** generate code and features;
**Reviewers** provide quality gates, feedback, and hardening.  The Local agent
is the primary workhorse — use it as much as possible to minimise cost.

---

### 🏗️ BUILD TIER

---

### Local — Ollama (primary workhorse)
**Model:** Any — `qwen2.5-coder`, `deepseek-coder-v2`, `codellama`, or whatever
is loaded in Ollama.  The owner decides the model; this agent is unrestricted.
**Cost:** Free.  Runs on the host machine.

**Best for:**
- Everything.  This is the default agent for all coding tasks.
- Iterative development, fast feedback loops, bulk generation
- Running as a Docker swarm worker — scales horizontally at zero marginal cost
- Experimenting with new models without changing any other code

**Conventions to follow:**
- Communicate with the coordinator over HTTP (`COORDINATOR_URL` env var)
- Register capabilities honestly so the auction system routes tasks well
- Write tests for anything non-trivial

**No restrictions.**  If a model can do it, do it.

---

### Kimi (Moonshot AI)
**Model:** Moonshot large-context models.
**Cost:** Paid API.

**Best for:**
- Large context feature drops (new pages, new subsystems, new agent personas)
- Implementing roadmap items that require reading many files at once
- Generating boilerplate for new agents (Echo, Mace, Helm, Seer, Forge, Quill)

**Conventions to follow:**
- Deliver working code with accompanying tests (even if minimal)
- Match the arcane CSS theme — extend `static/style.css`
- New agents follow the `SwarmNode` + `Registry` + Docker pattern
- Lightning-gated endpoints follow the L402 pattern in `src/timmy_serve/l402_proxy.py`

**Avoid:**
- Touching CI/CD or pyproject.toml without coordinating
- Adding cloud API calls
- Removing existing tests

---

### DeepSeek (DeepSeek API)
**Model:** `deepseek-chat` (V3) or `deepseek-reasoner` (R1).
**Cost:** Near-free (~$0.14/M tokens).

**Best for:**
- Second-opinion feature generation when Kimi is busy or context is smaller
- Large refactors with reasoning traces (use R1 for hard problems)
- Code review passes before merging Kimi PRs
- Anything that doesn't need a frontier model but benefits from strong reasoning

**Conventions to follow:**
- Same conventions as Kimi
- Prefer V3 for straightforward tasks; R1 for anything requiring multi-step logic
- Submit PRs for review by Claude before merging

**Avoid:**
- Bypassing the review tier for security-sensitive modules
- Touching `src/swarm/coordinator.py` without Claude review

---

### 🔍 REVIEW TIER

---

### Claude (Anthropic)
**Model:** Claude Sonnet.
**Cost:** Paid API.

**Best for:**
- Architecture decisions and code-quality review
- Writing and fixing tests; keeping coverage green
- Updating documentation (README, AGENTS.md, inline comments)
- CI/CD, tooling, Docker infrastructure
- Debugging tricky async or import issues
- Reviewing PRs from Local, Kimi, and DeepSeek before merge

**Conventions to follow:**
- Prefer editing existing files over creating new ones
- Keep route files thin — business logic lives in the module, not the route
- Use `from config import settings` for all env-var access
- New routes go in `src/dashboard/routes/`, registered in `app.py`
- Always add a corresponding `tests/test_<module>.py`

**Avoid:**
- Large one-shot feature dumps (use Local or Kimi)
- Touching `src/swarm/coordinator.py` for security work (that's Manus's lane)

---

### Gemini (Google)
**Model:** Gemini 2.0 Flash (free tier) or Pro.
**Cost:** Free tier generous; upgrade only if needed.

**Best for:**
- Documentation, README updates, inline docstrings
- Frontend polish — HTML templates, CSS, accessibility review
- Boilerplate generation (test stubs, config files, GitHub Actions)
- Summarising large diffs for human review

**Conventions to follow:**
- Submit changes as PRs; always include a plain-English summary of what changed
- For CSS changes, test at mobile breakpoint (≤768px) before submitting
- Never modify Python business logic without Claude review

**Avoid:**
- Security-sensitive modules (that's Manus's lane)
- Changing auction or payment logic
- Large Python refactors

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
- New feature work (use Local or Kimi)
- Changing agent personas or prompt content

---

## 4. Docker — Running Agents as Containers

Each agent can run as an isolated Docker container.  Containers share the
`data/` volume for SQLite and communicate with the coordinator over HTTP.

```bash
make docker-build          # build the image
make docker-up             # start dashboard + deps
make docker-agent          # spawn one agent worker (LOCAL model)
make docker-down           # stop everything
make docker-logs           # tail all service logs
```

### How container agents communicate

Container agents cannot use the in-memory `SwarmComms` channel.  Instead they
poll the coordinator's internal HTTP API:

```
GET  /internal/tasks          → list tasks open for bidding
POST /internal/bids           → submit a bid
```

Set `COORDINATOR_URL=http://dashboard:8000` in the container environment
(docker-compose sets this automatically).

### Spawning a container agent from Python

```python
from swarm.docker_runner import DockerAgentRunner

runner = DockerAgentRunner(coordinator_url="http://dashboard:8000")
info   = runner.spawn("Echo", image="timmy-time:latest")
runner.stop(info["container_id"])
```

---

## 5. Architecture Patterns

### Singletons (module-level instances)
```python
from dashboard.store import message_log
from notifications.push import notifier
from ws_manager.handler import ws_manager
from timmy_serve.payment_handler import payment_handler
from swarm.coordinator import coordinator
```

### Config access
```python
from config import settings
url = settings.ollama_url   # never os.environ.get() directly in route files
```

### HTMX pattern
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

## 6. Running Locally

```bash
make install        # create venv + install dev deps
make test           # run full test suite
make dev            # start dashboard (http://localhost:8000)
make watch          # self-TDD watchdog (60s poll)
make test-cov       # coverage report
```

Or with Docker:
```bash
make docker-build   # build image
make docker-up      # start dashboard
make docker-agent   # add a Local agent worker
```

---

## 7. Roadmap (v2 → v3)

**v2.0.0 — Exodus (in progress)**
- [x] Persistent swarm state across restarts
- [x] Docker infrastructure for agent containers
- [x] Implement Echo, Mace, Helm, Seer, Forge, Quill persona agents (+ Pixel, Lyra, Reel)
- [x] MCP tool integration for Timmy
- [ ] Real LND gRPC backend for `PaymentHandler` (replace mock)
- [ ] Marketplace frontend — wire `/marketplace` route to real data

**v3.0.0 — Revelation (planned)**
- [ ] Bitcoin Lightning treasury (agent earns and spends sats autonomously)
- [ ] Single `.app` bundle for macOS (no Python install required)
- [ ] Federation — multiple Timmy instances discover and bid on each other's tasks
- [ ] Redis pub/sub replacing SQLite polling for high-throughput swarms

---

## 8. File Conventions

| Pattern | Convention |
|---------|-----------|
| New route | `src/dashboard/routes/<name>.py` + register in `app.py` |
| New template | `src/dashboard/templates/<name>.html` extends `base.html` |
| New partial | `src/dashboard/templates/partials/<name>.html` |
| New subsystem | `src/<name>/` with `__init__.py` |
| New test file | `tests/test_<module>.py` |
| Secrets | Read via `os.environ.get("VAR", "default")` + startup warning if default |
| DB files | `.db` files go in project root or `data/` — never in `src/` |
| Docker | One service per agent type in `docker-compose.yml` |
