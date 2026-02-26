# Changelog — 2025-02-27

## Model Upgrade & Hallucination Fix

### Change 1: Model Upgrade (Primary Fix)
**Problem:** llama3.2 (3B parameters) consistently hallucinated tool output instead of waiting for real results.

**Solution:** Upgraded default model to `llama3.1:8b-instruct` which is specifically fine-tuned for reliable tool/function calling.

**Changes:**
- `src/config.py`: Changed `ollama_model` default from `llama3.2` to `llama3.1:8b-instruct`
- Added fallback logic: if primary model unavailable, auto-fallback to `qwen2.5:14b`
- `README.md`: Updated setup instructions with new model requirement

**User Action Required:**
```bash
ollama pull llama3.1:8b-instruct
```

### Change 2: Structured Output Enforcement (Foundation)
**Preparation:** Added infrastructure for two-phase tool calling with JSON schema enforcement.

**Implementation:**
- Session context tracking in `TimmyOrchestrator`
- `_session_init()` runs on first message to load real data

### Change 3: Git Tool Working Directory Fix
**Problem:** Git tools failed with "fatal: Not a git repository" due to wrong working directory.

**Solution:**
- Rewrote `src/tools/git_tools.py` to use subprocess with explicit `cwd=REPO_ROOT`
- Added `REPO_ROOT` module-level constant auto-detected at import time
- All git commands now run from the correct directory

### Change 4: Session Init with Git Log
**Problem:** Timmy couldn't answer "what's new?" from real data.

**Solution:**
- `_session_init()` now reads `git log --oneline -15` from repo root on first message
- Recent commits prepended to system prompt
- Timmy now grounds self-description in actual commit history

### Change 5: Documentation Updates
- `README.md`: Updated Quickstart with new model requirement
- `README.md`: Configuration table reflects new default model
- Added notes explaining why llama3.1:8b-instruct is required

### Files Modified
- `src/config.py` — Model configuration with fallback
- `src/tools/git_tools.py` — Complete rewrite with subprocess + cwd
- `src/agents/timmy.py` — Session init with git log reading
- `README.md` — Updated setup and configuration docs

### Testing
- All git tool tests pass with new subprocess implementation
- Git log correctly returns commits from repo root
- Session init loads context on first message
