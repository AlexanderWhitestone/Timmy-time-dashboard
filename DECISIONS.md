# DECISIONS.md — Architectural Decision Log

This file documents major architectural decisions and their rationale.

---

## Decision: Dynamic Model Name in System Prompts

**Date:** 2026-02-26

**Context:** Timmy's system prompts hardcoded "llama3.2" but the actual model is "llama3.1:8b-instruct", causing confusion.

**Decision:** Make model name dynamic by:
- Using `{model_name}` placeholder in prompt templates
- Injecting actual value from `settings.ollama_model` at runtime via `get_system_prompt()`

**Rationale:** Single source of truth. If model changes in config, prompts reflect it automatically.

---

## Decision: Unified Repo Root Detection

**Date:** 2026-02-26

**Context:** Multiple places in code detected repo root differently (git_tools.py, file_ops.py, timmy.py).

**Decision:** Add `repo_root` to config.py with auto-detection:
- Walk up from `__file__` to find `.git`
- Fall back to environment or current directory

**Rationale:** Consistent path resolution for all tools.

---

## Add New Decisions Above This Line

When making significant architectural choices, document:
1. Date
2. Context (what problem prompted the decision)
3. Decision (what was chosen)
4. Rationale (why this approach was better than alternatives)
