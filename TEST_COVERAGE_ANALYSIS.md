# Test Coverage Analysis — Timmy Time Dashboard

**Date:** 2026-03-06
**Overall coverage:** 63.6% (7,996 statements, 2,910 missed)
**Threshold:** 60% (passes, but barely)
**Test suite:** 914 passed, 4 failed, 39 skipped, 5 errors — 35 seconds

---

## Current Coverage by Package

| Package | Approx. Coverage | Notes |
|---------|-----------------|-------|
| `spark/` | 90–98% | Best-covered package |
| `timmy_serve/` | 80–100% | Small package, well tested |
| `infrastructure/models/` | 42–97% | `registry` great, `multimodal` weak |
| `dashboard/middleware/` | 79–100% | Solid |
| `dashboard/routes/` | 36–100% | Highly uneven — some routes untested |
| `integrations/` | 51–100% | Paperclip well covered; Discord weak |
| `timmy/` | 0–100% | Several core modules at 0% |
| `brain/` | 0–75% | `client` and `worker` very low |
| `infrastructure/events/` | 0% | Completely untested |
| `infrastructure/error_capture.py` | 0% | Completely untested |

---

## Priority 1 — Zero-Coverage Modules (0%)

These modules have **no test coverage at all** and represent the biggest risk:

| Module | Stmts | Purpose |
|--------|-------|---------|
| `src/timmy/semantic_memory.py` | 187 | Semantic memory system — core agent feature |
| `src/timmy/agents/timmy.py` | 165 | Main Timmy agent class |
| `src/timmy/agents/base.py` | 57 | Base agent class |
| `src/timmy/interview.py` | 46 | Interview flow |
| `src/infrastructure/error_capture.py` | 91 | Error capture/reporting |
| `src/infrastructure/events/broadcaster.py` | 67 | Event broadcasting |
| `src/infrastructure/events/bus.py` | 74 | Event bus |
| `src/infrastructure/openfang/tools.py` | 41 | OpenFang tool definitions |
| `src/brain/schema.py` | 14 | Brain schema definitions |

**Recommendation:** `timmy/agents/timmy.py` (165 stmts) and `semantic_memory.py` (187 stmts) are the highest-value targets. The events subsystem (`broadcaster.py` + `bus.py` = 141 stmts) is critical infrastructure with zero tests.

---

## Priority 2 — Under-Tested Modules (<50%)

| Module | Cover | Stmts Missed | Purpose |
|--------|-------|-------------|---------|
| `brain/client.py` | 14.8% | 127 | Brain client — primary brain interface |
| `brain/worker.py` | 16.1% | 156 | Background brain worker |
| `brain/embeddings.py` | 35.0% | 26 | Embedding generation |
| `timmy/approvals.py` | 39.1% | 42 | Approval workflow |
| `dashboard/routes/marketplace.py` | 36.4% | 21 | Marketplace routes |
| `dashboard/routes/paperclip.py` | 41.1% | 96 | Paperclip dashboard routes |
| `infrastructure/hands/tools.py` | 41.3% | 27 | Tool execution |
| `infrastructure/models/multimodal.py` | 42.6% | 81 | Multimodal model support |
| `dashboard/routes/router.py` | 42.9% | 12 | Route registration |
| `dashboard/routes/swarm.py` | 43.3% | 17 | Swarm routes |
| `timmy/cascade_adapter.py` | 43.2% | 25 | Cascade LLM adapter |
| `timmy/tools_intro/__init__.py` | 44.7% | 84 | Tool introduction system |
| `timmy/tools.py` | 46.4% | 147 | Agent tool definitions |
| `timmy/cli.py` | 47.4% | 30 | CLI entry point |
| `timmy/conversation.py` | 48.5% | 34 | Conversation management |

**Recommendation:** `brain/client.py` + `brain/worker.py` together miss 283 statements and are the core of the brain/memory system. `timmy/tools.py` misses 147 statements and is the agent's tool registry — high impact.

---

## Priority 3 — Test Infrastructure Issues

### 3a. Broken Tests (4 failures)

All in `tests/test_setup_script.py` — tests reference `/home/ubuntu/setup_timmy.sh` which doesn't exist. These tests are environment-specific and should either:
- Be marked `@pytest.mark.skip_ci` or `@pytest.mark.functional`
- Use a fixture to locate the script relative to the project

### 3b. Collection Errors (5 errors)

`tests/functional/test_setup_prod.py` — same issue, references a non-existent script path. Should be guarded with a skip condition.

### 3c. pytest-xdist Conflicts with Coverage

The `pyproject.toml` `addopts` includes `-n auto --dist worksteal` (xdist), but `make test-cov` also passes `--cov` flags. This causes a conflict:
```
pytest: error: unrecognized arguments: -n --dist worksteal
```
**Fix:** Either:
- Remove `-n auto --dist worksteal` from `addopts` and add it only in `make test` target
- Or use `-p no:xdist` in the coverage targets (current workaround)

### 3d. Tox Configuration

`tox.ini` has `unit` and `integration` environments that run the **exact same command** — they're aliases. This is misleading:
- `unit` should run `-m unit` (fast, no I/O)
- `integration` should run `-m integration` (may use SQLite)
- Consider adding a `coverage` tox env

### 3e. CI Workflow (`tests.yml`)

- CI uses `pip install -e ".[dev]"` but the project uses Poetry — dependency resolution may differ
- CI doesn't pass marker filters, so it runs **all** tests including those that may need Docker/Ollama
- No coverage enforcement in CI (the `fail_under=60` in pyproject.toml only works with `--cov-fail-under`)
- No caching of Poetry virtualenvs

---

## Priority 4 — Test Quality Gaps

### 4a. Missing Error-Path Testing

Many modules have happy-path tests but lack coverage for:
- **Graceful degradation paths**: The architecture mandates graceful degradation when Ollama/Redis/AirLLM are unavailable, but most fallback paths are untested (e.g., `cascade.py` lines 563–655)
- **`brain/client.py`**: Only 14.8% covered — connection failures, retries, and error handling are untested
- **`infrastructure/error_capture.py`**: 0% — the error capture system itself has no tests

### 4b. No Integration Tests for Events System

The `infrastructure/events/` package (`broadcaster.py` + `bus.py`) is 0% covered. This is the pub/sub backbone for the application. Tests should cover:
- Event subscription and dispatch
- Multiple subscribers
- Error handling in event handlers
- Async event broadcasting

### 4c. Security Tests Are Thin

- `tests/security/` has only 3 files totaling ~140 lines
- `src/timmy_serve/l402_proxy.py` (payment gating, listed as security-sensitive) has no dedicated test file
- CSRF tests exist but bypass/traversal tests are minimal
- No tests for the `approvals.py` authorization workflow (39.1% covered)

### 4d. Missing WebSocket Tests

WebSocket handler (`ws_manager/handler.py`) has 81.2% coverage, but the disconnect/reconnect and error paths (lines 132–147) aren't tested. For a real-time dashboard, WebSocket reliability is critical.

### 4e. No Tests for `timmy/agents/` Subpackage

The Agno-based agent classes (`base.py`, `timmy.py`) are at 0% coverage (222 statements). These are stubbed in conftest but never actually exercised. Even with the Agno stub, the control flow and prompt construction logic should be tested.

---

## Priority 5 — Test Speed & Parallelism

| Metric | Value |
|--------|-------|
| Total wall time | ~35s (sequential) |
| Parallel (`-n auto`) | Would be ~10-15s |
| Slowest category | Functional tests (HTTP, Docker) |

**Observations:**
- 30-second timeout per test is generous — consider 10s for unit, 30s for integration
- The `--dist worksteal` strategy is good for uneven test durations
- 39 tests are skipped (mostly due to missing markers/env) — this is expected
- No test duration profiling is configured (consider `--durations=10`)

---

## Recommended Action Plan

### Quick Wins (High ROI, Low Effort)
1. **Fix the 4 broken tests** in `test_setup_script.py` (add skip guards)
2. **Fix xdist/coverage conflict** in `pyproject.toml` addopts
3. **Differentiate tox `unit` vs `integration`** environments
4. **Add `--durations=10`** to default addopts for profiling slow tests
5. **Add `--cov-fail-under=60`** to CI workflow to enforce the threshold

### Medium Effort, High Impact
6. **Test the events system** (`broadcaster.py` + `bus.py`) — 141 uncovered statements, critical infrastructure
7. **Test `timmy/agents/timmy.py`** — 165 uncovered statements, core agent
8. **Test `brain/client.py` and `brain/worker.py`** — 283 uncovered statements, core memory
9. **Test `timmy/tools.py`** error paths — 147 uncovered statements
10. **Test `error_capture.py`** — 91 uncovered statements, observability blind spot

### Longer Term
11. **Add graceful-degradation tests** — verify fallback behavior for all optional services
12. **Expand security test suite** — approvals, L402 proxy, input sanitization
13. **Add coverage tox environment** and enforce in CI
14. **Align CI with Poetry** — use `poetry install` instead of pip for consistent resolution
15. **Target 75% coverage** as the next threshold milestone (currently 63.6%)

---

## Coverage Floor Modules (Already Well-Tested)

These modules are at 95%+ and serve as good examples of testing patterns:

- `spark/eidos.py` — 98.3%
- `spark/memory.py` — 98.3%
- `infrastructure/models/registry.py` — 97.1%
- `timmy/agent_core/ollama_adapter.py` — 97.8%
- `timmy/agent_core/interface.py` — 100%
- `dashboard/middleware/security_headers.py` — 100%
- `dashboard/routes/agents.py` — 100%
- `timmy_serve/inter_agent.py` — 100%
