# AGENTS.md — Timmy Time Development Standards for AI Agents

Read [`CLAUDE.md`](CLAUDE.md) for architecture patterns and conventions.

---

## Communication Protocol

**Before making changes, always:**
1. Read CLAUDE.md and AGENTS.md fully
2. Explore the relevant src/ modules to understand existing patterns
3. Explain what you're changing and **why** in plain English
4. Provide decision rationale - don't just make changes, explain the reasoning

**For Timmy's growth goals:**
- Improve reasoning in complex/uncertain situations: think step-by-step, consider alternatives
- When uncertain, state uncertainty explicitly rather than guessing
- Document major decisions in DECISIONS.md

---

## Non-Negotiable Rules

1. **Tests must stay green.** Run `make test` before committing.
2. **No cloud dependencies.** All AI computation runs on localhost.
3. **No new top-level files without purpose.** Don't litter the root directory.
4. **Follow existing patterns** — singletons, graceful degradation, pydantic-settings.
5. **Security defaults:** Never hard-code secrets.
6. **XSS prevention:** Never use `innerHTML` with untrusted content.

---

## Agent Roster

### Build Tier

**Local (Ollama)** — Primary workhorse. Free. Unrestricted.
Best for: everything, iterative dev, Docker swarm workers.

**Kimi (Moonshot)** — Paid. Large-context feature drops, new subsystems, persona agents.
Avoid: touching CI/pyproject.toml, adding cloud calls, removing tests.

**DeepSeek** — Near-free. Second-opinion generation, large refactors (R1 for hard problems).
Avoid: bypassing review tier for security modules.

### Review Tier

**Claude (Anthropic)** — Architecture, tests, docs, CI/CD, PR review.
Avoid: large one-shot feature dumps.

**Gemini (Google)** — Docs, frontend polish, boilerplate, diff summaries.
Avoid: security modules, Python business logic without Claude review.

**Manus AI** — Security audits, coverage gaps, L402 validation.
Avoid: large refactors, new features, prompt changes.

---

## Docker Agents

Container agents poll the coordinator's HTTP API (not in-memory `SwarmComms`):

```
GET  /internal/tasks    → list tasks open for bidding
POST /internal/bids     → submit a bid
```

`COORDINATOR_URL=http://dashboard:8000` is set by docker-compose.

```bash
make docker-build       # build image
make docker-up          # start dashboard
make docker-agent       # add a worker
```

---

## File Conventions

| Pattern | Convention |
|---------|-----------|
| New route | `src/dashboard/routes/<name>.py` + register in `app.py` |
| New template | `src/dashboard/templates/<name>.html` extends `base.html` |
| New subsystem | Add to existing `src/<package>/` — see module map in CLAUDE.md |
| New test | `tests/<module>/test_<feature>.py` (mirror source structure) |
| Secrets | Via `config.settings` + startup warning if default |
| DB files | Project root or `data/` — never in `src/` |

---

## Roadmap

**v2.0 Exodus (in progress):** Swarm + L402 + Voice + Marketplace + Hands
**v3.0 Revelation (planned):** Lightning treasury + `.app` bundle + federation
