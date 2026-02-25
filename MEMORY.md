# Timmy Hot Memory

> Working RAM — always loaded, ~300 lines max, pruned monthly
> Last updated: 2026-02-25

---

## Current Status

**Agent State:** Operational  
**Mode:** Development  
**Active Tasks:** 0  
**Pending Decisions:** None

---

## Standing Rules

1. **Sovereignty First** — No cloud dependencies, no data exfiltration
2. **Local-Only Inference** — Ollama on localhost, Apple Silicon optimized
3. **Privacy by Design** — Telemetry disabled, secrets in .env only
4. **Tool Minimalism** — Use tools only when necessary, prefer direct answers
5. **Memory Discipline** — Write handoffs at session end, prune monthly

---

## Agent Roster

| Agent | Role | Status | Capabilities |
|-------|------|--------|--------------|
| Timmy | Core | Active | chat, reasoning, planning |
| Echo | Research | Standby | web_search, file_read |
| Forge | Code | Standby | shell, python, git |
| Seer | Data | Standby | python, analysis |
| Helm | DevOps | Standby | shell, deployment |

---

## User Profile

**Name:** TestUser


## Key Decisions

- **2026-02-25:** Implemented 3-tier memory architecture
- **2026-02-25:** Disabled telemetry by default (sovereign AI)
- **2026-02-25:** Fixed Agno Toolkit API compatibility

---

## Pending Actions

- [ ] Learn user's name and preferences
- [ ] Populate user profile in self/identity.md
- [ ] First AAR after meaningful task completion

---

## Current Session

**Session ID:** (active)  
**Started:** 2026-02-25  
**Context:** Memory system initialization  
**Last Handoff:** (none yet)

---

## Quick Reference

**Available Tools:**
- `web_search` — Current events only
- `read_file` / `write_file` — Explicit request only
- `python` — Calculations, code execution
- `shell` — System commands (caution)

**Memory Locations:**
- Hot: `MEMORY.md` (this file)
- Vault: `memory/`
- Handoff: `memory/notes/last-session-handoff.md`

---

*Prune date: 2026-03-25*
