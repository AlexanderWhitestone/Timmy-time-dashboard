# Timmy Time — Architectural Refactoring Plan

**Author:** Claude (VP Engineering review)
**Date:** 2026-02-26
**Branch:** `claude/plan-repo-refactoring-hgskF`

---

## Executive Summary

The Timmy Time codebase has grown to **53K lines of Python** across **272
files** (169 source + 103 test), **28 modules** in `src/`, **27 route files**,
**49 templates**, **90 test files**, and **87KB of root-level markdown**. It
works, but it's burning tokens, slowing down test runs, and making it hard to
reason about change impact.

This plan proposes **6 phases** of refactoring, ordered by impact and risk. Each
phase is independently valuable — you can stop after any phase and still be
better off.

---

## The Problems

### 1. Monolith sprawl
28 modules in `src/` with no grouping. Eleven modules aren't even included in
the wheel build (`agents`, `events`, `hands`, `mcp`, `memory`, `router`,
`self_coding`, `task_queue`, `tools`, `upgrades`, `work_orders`). Some are
used by the dashboard routes but forgotten in `pyproject.toml`.

### 2. Dashboard is the gravity well
The dashboard has 27 route files (4,562 lines), 49 templates, and has become
the integration point for everything. Every new feature = new route file + new
template + new test file. This doesn't scale.

### 3. Documentation entropy
10 root-level `.md` files (87KB). README is 303 lines, CLAUDE.md is 267 lines,
AGENTS.md is 342 lines — with massive content duplication between them. Plus
PLAN.md, WORKSET_PLAN.md, WORKSET_PLAN_PHASE2.md, MEMORY.md,
IMPLEMENTATION_SUMMARY.md, QUALITY_ANALYSIS.md, QUALITY_REVIEW_REPORT.md.
Human eyes glaze over. AI assistants waste tokens reading redundant info.

### 4. Test sprawl — and a skeleton problem
97 test files, 19,600 lines — but **61 of those files (63%) are empty
skeletons** with zero actual test functions. Only 36 files have real tests
containing 471 test functions total. Many "large" test files (like
`test_scripture.py` at 901 lines, `test_router_cascade.py` at 523 lines) are
infrastructure-only — class definitions, imports, fixtures, but no assertions.
The functional/E2E directory (`tests/functional/`) has 7 files and 0 working
tests. Tests are flat in `tests/` with no organization. Running the full suite
means loading every module, every mock, every fixture even when you only
changed one thing.

### 5. Unclear project boundaries
Is this one project or several? The `timmy` CLI, `timmy-serve` API server,
`self-tdd` watchdog, and `self-modify` CLI are four separate entry points that
could be four separate packages. The `creative` extra needs PyTorch. The
`lightning` module is a standalone payment system. These shouldn't live in the
same test run.

### 6. Wheel build doesn't match reality
`pyproject.toml` includes 17 modules but `src/` has 28. The missing 11 modules
are used by code that IS included (dashboard routes import from `hands`,
`mcp`, `memory`, `work_orders`, etc.). The wheel would break at runtime.

### 7. Dependency coupling through dashboard

The dashboard is the hub that imports from 20+ modules. The dependency graph
flows inward: `config` is the foundation (22 modules depend on it), `mcp` is
widely used (12+ importers), `swarm` is referenced by 15+ modules. No true
circular dependencies exist (the `timmy ↔ swarm` relationship uses lazy
imports), but the dashboard pulls in everything, so changing any module can
break the dashboard routes.

### 8. Conftest does too much

`tests/conftest.py` has 4 autouse fixtures that run on **every single test**:
reset message log, reset coordinator state, clean database, cleanup event
loops. Many tests don't need any of these. This adds overhead to the test
suite and couples all tests to the swarm coordinator.

---

## Phase 1: Documentation Cleanup (Low Risk, High Impact)

**Goal:** Cut root markdown from 87KB to ~20KB. Make README human-readable.
Eliminate token waste.

### 1.1 Slim the README

Cut README.md from 303 lines to ~80 lines:

```
# Timmy Time — Mission Control

Local-first sovereign AI agent system. Browser dashboard, Ollama inference,
Bitcoin Lightning economics. No cloud AI.

## Quick Start
  make install && make dev  →  http://localhost:8000

## What's Here
  - Timmy Agent (Ollama/AirLLM)
  - Mission Control Dashboard (FastAPI + HTMX)
  - Swarm Coordinator (multi-agent auctions)
  - Lightning Payments (L402 gating)
  - Creative Studio (image/music/video)
  - Self-Coding (codebase-aware self-modification)

## Commands
  make dev / make test / make docker-up / make help

## Documentation
  - Development guide: CLAUDE.md
  - Architecture: docs/architecture-v2.md
  - Agent conventions: AGENTS.md
  - Config reference: .env.example
```

### 1.2 De-duplicate CLAUDE.md

Remove content that duplicates README or AGENTS.md. CLAUDE.md should only
contain what AI assistants need that isn't elsewhere:
- Architecture patterns (singletons, config, HTMX, graceful degradation)
- Testing conventions (conftest, fixtures, stubs)
- Security-sensitive areas
- Entry points table

Target: 267 → ~130 lines.

### 1.3 Archive or delete temporary docs

| File | Action |
|------|--------|
| `MEMORY.md` | DELETE — session context, not permanent docs |
| `WORKSET_PLAN.md` | DELETE — use GitHub Issues |
| `WORKSET_PLAN_PHASE2.md` | DELETE — use GitHub Issues |
| `PLAN.md` | MOVE to `docs/PLAN_ARCHIVE.md` |
| `IMPLEMENTATION_SUMMARY.md` | MOVE to `docs/IMPLEMENTATION_ARCHIVE.md` |
| `QUALITY_ANALYSIS.md` | CONSOLIDATE with `docs/QUALITY_AUDIT.md` |
| `QUALITY_REVIEW_REPORT.md` | CONSOLIDATE with `docs/QUALITY_AUDIT.md` |

**Result:** Root directory goes from 10 `.md` files to 3 (README, CLAUDE,
AGENTS).

### 1.4 Clean up .handoff/

The `.handoff/` directory (CHECKPOINT.md, CONTINUE.md, TODO.md, scripts) is
session-scoped context. Either gitignore it or move to `docs/handoff/`.

---

## Phase 2: Module Consolidation (Medium Risk, High Impact)

**Goal:** Reduce 28 modules to ~12 by merging small, related modules into
coherent packages. This directly reduces cognitive load and token consumption.

### 2.1 Module structure (partially implemented)

**Actual current structure (7 packages + config):**

```
src/                           # 7 packages (was 28)
  config.py                    # Pydantic settings (foundation)

  timmy/                       # Core agent + agents/ + agent_core/ + memory/
  dashboard/                   # FastAPI web UI, routes, templates
  infrastructure/              # ws_manager/ + notifications/ + events/ + router/
  integrations/                # chat_bridge/ + telegram_bot/ + shortcuts/ + voice/
  spark/                       # Event capture and advisory
  brain/                       # Identity system, memory interface
  timmy_serve/                 # API server
```

**Planned but never created:** `swarm/`, `self_coding/`, `creative/`,
`lightning/`, `mcp/`, `hands/`, `scripture/`

### 2.2 Dashboard route consolidation

27 route files → ~12 by grouping related routes:

| Current files | Merged into |
|--------------|-------------|
| `agents.py`, `briefing.py` | `agents.py` |
| `swarm.py`, `swarm_internal.py`, `swarm_ws.py` | `swarm.py` |
| `voice.py`, `voice_enhanced.py` | `voice.py` |
| `mobile.py`, `mobile_test.py` | `mobile.py` (delete test page) |
| `self_coding.py`, `self_modify.py` | `self_coding.py` |
| `tasks.py`, `work_orders.py` | `tasks.py` |

`mobile_test.py` (257 lines) is a test page route that's excluded from
coverage — it should not ship in production.

### 2.3 Fix the wheel build

Update `pyproject.toml` `[tool.hatch.build.targets.wheel]` to include all
modules that are actually imported. Currently 11 modules are missing from the
build manifest.

---

## Phase 3: Test Reorganization (Medium Risk, Medium Impact)

**Goal:** Organize tests to match module structure, enable selective test runs,
reduce full-suite runtime.

### 3.1 Mirror source structure in tests

```
tests/
  conftest.py               # Global fixtures only
  timmy/                    # Tests for timmy/ module
    conftest.py             # Timmy-specific fixtures
    test_agent.py
    test_backends.py
    test_cli.py
    test_orchestrator.py
    test_personas.py
    test_memory.py
  dashboard/
    conftest.py             # Dashboard fixtures (client fixture)
    test_routes_agents.py
    test_routes_swarm.py
    ...
  swarm/
    test_coordinator.py
    test_tasks.py
    test_work_orders.py
  integrations/
    test_chat_bridge.py
    test_telegram.py
    test_voice.py
  self_coding/
    test_git_safety.py
    test_codebase_indexer.py
    test_self_modify.py
  ...
```

### 3.2 Add pytest marks for selective execution

```python
# pyproject.toml
[tool.pytest.ini_options]
markers = [
    "unit: Unit tests (fast, no I/O)",
    "integration: Integration tests (may use SQLite)",
    "dashboard: Dashboard route tests",
    "swarm: Swarm coordinator tests",
    "slow: Tests that take >1 second",
]
```

Usage:
```bash
make test                    # Run all tests
pytest -m unit               # Fast unit tests only
pytest -m dashboard          # Just dashboard tests
pytest tests/swarm/          # Just swarm module tests
pytest -m "not slow"         # Skip slow tests
```

### 3.3 Audit and clean skeleton test files

61 test files are empty skeletons — they have imports, class definitions, and
fixture setup but **zero test functions**. These add import overhead and create
a false sense of coverage. For each skeleton file:

1. If the module it tests is stable and well-covered elsewhere → **delete it**
2. If the module genuinely needs tests → **implement the tests** or file an
   issue
3. If it's a duplicate (e.g., both `test_swarm.py` and
   `test_swarm_integration.py` exist) → **consolidate**

Notable skeletons to address:
- `test_scripture.py` (901 lines, 0 tests) — massive infrastructure, no assertions
- `test_router_cascade.py` (523 lines, 0 tests) — same pattern
- `test_agent_core.py` (457 lines, 0 tests)
- `test_self_modify.py` (451 lines, 0 tests)
- All 7 files in `tests/functional/` (0 working tests)

### 3.4 Split genuinely oversized test files

For files that DO have tests but are too large:
- `test_task_queue.py` (560 lines, 30 tests) → split by feature area
- `test_mobile_scenarios.py` (339 lines, 36 tests) → split by scenario group

Rule of thumb: No test file over 400 lines.

---

## Phase 4: Configuration & Build Cleanup (Low Risk, Medium Impact)

### 4.1 Clean up pyproject.toml

- Fix the wheel include list to match actual imports
- Consider whether 4 separate CLI entry points belong in one package
- Add `[project.urls]` for documentation, repository links
- Review dependency pins — some are very loose (`>=1.0.0`)

### 4.2 Consolidate Docker files

4 docker-compose variants (default, dev, prod, test) is a lot. Consider:
- `docker-compose.yml` (base)
- `docker-compose.override.yml` (dev — auto-loaded by Docker)
- `docker-compose.prod.yml` (production only)

### 4.3 Clean up root directory

Non-essential root files to move or delete:

| File | Action |
|------|--------|
| `apply_security_fixes.py` | Move to `scripts/` or delete if one-time |
| `activate_self_tdd.sh` | Move to `scripts/` |
| `coverage.xml` | Gitignore (CI artifact) |
| `data/self_modify_reports/` | Gitignore the contents |

---

## Phase 5: Consider Package Extraction (High Risk, High Impact)

**Goal:** Evaluate whether some modules should be separate packages/repos.

### 5.1 Candidates for extraction

| Module | Why extract | Dependency direction |
|--------|------------|---------------------|
| `lightning/` | Standalone payment system, security-sensitive | Dashboard imports lightning |
| `creative/` | Needs PyTorch, very different dependency profile | Dashboard imports creative |
| `timmy-serve` | Separate process (port 8402), separate purpose | Shares config + timmy agent |
| `self_coding/` + `self_modify/` | Self-contained self-modification system | Dashboard imports for routes |

### 5.2 Monorepo approach (recommended over multi-repo)

If splitting, use a monorepo with namespace packages:

```
packages/
  timmy-core/          # Agent + memory + CLI
  timmy-dashboard/     # FastAPI app
  timmy-swarm/         # Coordinator + tasks
  timmy-lightning/     # Payment system
  timmy-creative/      # Creative tools (heavy deps)
```

Each package gets its own `pyproject.toml`, test suite, and can be installed
independently. But they share the same repo, CI, and release cycle.

**However:** This is high effort and may not be worth it unless the team
grows or the dependency profiles diverge further. Consider this only after
Phases 1-4 are done and the pain persists.

---

## Phase 6: Token Optimization for AI Development (Low Risk, High Impact)

**Goal:** Reduce context window consumption when AI assistants work on this
codebase.

### 6.1 Lean CLAUDE.md (already covered in Phase 1)

Every byte in CLAUDE.md is read by every AI interaction. Remove duplication.

### 6.2 Module-level CLAUDE.md files

Instead of one massive guide, put module-specific context where it's needed:

```
src/swarm/CLAUDE.md        # "This module is security-sensitive. Always..."
src/lightning/CLAUDE.md    # "Never hard-code secrets. Use settings..."
src/dashboard/CLAUDE.md   # "Routes return template partials for HTMX..."
```

AI assistants read these only when working in that directory.

### 6.3 Standardize module docstrings

Every `__init__.py` should have a one-line summary. AI assistants read these
to understand module purpose without reading every file:

```python
"""Swarm — Multi-agent coordinator with auction-based task assignment."""
```

### 6.4 Reduce template duplication

49 templates with repeated boilerplate. Consider Jinja2 macros for common
patterns (card layouts, form groups, table rows).

---

## Prioritized Execution Order

| Priority | Phase | Effort | Risk | Impact |
|----------|-------|--------|------|--------|
| **1** | Phase 1: Doc cleanup | 2-3 hours | Low | High — immediate token savings |
| **2** | Phase 6: Token optimization | 1-2 hours | Low | High — ongoing AI efficiency |
| **3** | Phase 4: Config/build cleanup | 1-2 hours | Low | Medium — hygiene |
| **4** | Phase 2: Module consolidation | 4-8 hours | Medium | High — structural improvement |
| **5** | Phase 3: Test reorganization | 3-5 hours | Medium | Medium — faster test cycles |
| **6** | Phase 5: Package extraction | 8-16 hours | High | High — only if needed |

---

## Quick Wins (Can Do Right Now)

1. Delete MEMORY.md, WORKSET_PLAN.md, WORKSET_PLAN_PHASE2.md (3 files, 0 risk)
2. Move PLAN.md, IMPLEMENTATION_SUMMARY.md, quality docs to `docs/` (5 files)
3. Slim README to ~80 lines
4. Fix pyproject.toml wheel includes (11 missing modules)
5. Gitignore `coverage.xml` and `data/self_modify_reports/`
6. Delete `dashboard/routes/mobile_test.py` (test page in production routes)
7. Delete or gut empty test skeletons (61 files with 0 tests — they waste CI
   time and create noise)

---

## What NOT to Do

- **Don't rewrite from scratch.** The code works. Refactor incrementally.
- **Don't split into multiple repos.** Monorepo with packages (if needed) is
  simpler for a small team.
- **Don't change the tech stack.** FastAPI + HTMX + Jinja2 is fine. Don't add
  React, Vue, or a SPA framework.
- **Don't merge CLAUDE.md into README.** They serve different audiences.
- **Don't remove test files** just to reduce count. Reorganize them.
- **Don't break the singleton pattern.** It works for this scale.

---

## Success Metrics

| Metric | Original | Target | Current |
|--------|----------|--------|---------|
| Root `.md` files | 10 | 3 | 5 |
| Root markdown size | 87KB | ~20KB | ~28KB |
| `src/` modules | 28 | ~12-15 | **7 packages + config** |
| Dashboard routes | 27 | ~12-15 | 22 |
| Test organization | flat | mirrored | **mirrored** |
| Wheel modules | 17/28 | all | needs audit |
| Module-level docs | 0 | all key modules | needs audit |

---

## Execution Status

### Completed

- [x] **Phase 1: Doc cleanup** — README 303→93 lines, CLAUDE.md 267→80,
  AGENTS.md 342→72, deleted 3 session docs, archived 4 planning docs
- [x] **Phase 4: Config/build cleanup** — fixed 11 missing wheel modules, added
  pytest markers, updated .gitignore, moved scripts to scripts/
- [x] **Phase 6: Token optimization** — added docstrings to 15+ __init__.py files
- [x] **Phase 3: Test reorganization** — 97 test files organized into 13
  subdirectories mirroring source structure
- [x] **Phase 2a: Route consolidation** — 27 → 22 route files (merged voice,
  swarm internal/ws, self-modify; deleted mobile_test)

- [ ] **Phase 2b: Full module consolidation** — 28 → 14 modules. Partially
  completed. Some consolidations were applied:
  - `chat_bridge/` + `telegram_bot/` + `shortcuts/` + `voice/` → `integrations/` (done)
  - `ws_manager/` + `notifications/` + `events/` + `router/` → `infrastructure/` (done)
  - `agents/` + `agent_core/` + `memory/` → `timmy/` (done)
  - **Not completed:** `swarm/`, `self_coding/`, `creative/`, `lightning/` packages
    were never created. These modules do not exist in `src/`.
- [ ] **Phase 6.2: Module-level CLAUDE.md** — not completed. The referenced
  directories (`swarm/`, `self_coding/`, `creative/`, `lightning/`) do not exist.

### Remaining

- [ ] **Phase 5: Package extraction** — only if team grows or dep profiles diverge
