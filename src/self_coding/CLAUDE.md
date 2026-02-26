# self_coding/ — Module Guide

Self-modification infrastructure with safety constraints.

## Structure
- `git_safety.py` — Atomic git operations with rollback
- `codebase_indexer.py` — Live mental model of the codebase
- `modification_journal.py` — Persistent log of modification attempts
- `reflection.py` — Generate lessons learned
- `self_modify/` — Runtime self-modification loop (LLM-driven)
- `self_tdd/` — Continuous test watchdog
- `upgrades/` — Self-upgrade approval queue

## Entry points
```toml
self-tdd = "self_coding.self_tdd.watchdog:main"
self-modify = "self_coding.self_modify.cli:main"
```

## Testing
```bash
pytest tests/self_coding/ -q
```
