# Changelog — 2026-02-26

## Fixed: Timmy Self-Awareness & Tool Reliability

### P1: Git Tool Working Directory
- **Problem**: Git tools failed with "fatal: Not a git repository" because they ran from process working directory
- **Solution**: Added `repo_root` auto-detection to config; all git tools now default to repo root
- **Impact**: Timmy can now use git tools without knowing the absolute path

### P2: Boot-Time Self-Awareness  
- **Problem**: Timmy had no knowledge of recent commits, Hands, or system state
- **Solution**: Created `build_timmy_context()` that gathers:
  - Recent git commits (last 20)
  - Active sub-agents from swarm registry
  - Hands configuration and schedules
  - Hot memory from MEMORY.md
- **Impact**: Timmy's system prompt now includes live context about the system

### P3: Persistent Cross-Session Memory
- **Problem**: Timmy forgot lessons between sessions (e.g., "don't fabricate tool output")
- **Solution**: 
  - Added `memory_write` tool to save memories during conversation
  - Memories written to MEMORY.md with timestamps and categories
  - Session summary auto-written at session end
- **Impact**: Corrections and lessons now persist across sessions

### P4: Swarm Agents Registration
- **Problem**: Dashboard showed "NO AGENTS REGISTERED"
- **Solution**: Added `/api/swarm/status` endpoint returning detailed agent states
- **Impact**: Frontend can now poll and display live agent status

### P5: Anti-Hallucination Hard Rules
- **Problem**: Timmy fabricated tool output when he should have waited
- **Solution**: Added 6 hard rules to system prompt:
  1. Never fabricate tool output
  2. Report exact error messages
  3. Admit when you don't know
  4. Don't say "I'll wait" then immediately provide fake output
  5. Use memory_write when corrected
  6. Source code location is known (repo_root)
- **Impact**: Clear behavioral boundaries for the LLM

### P6: Session Init Behavior
- **Problem**: Timmy couldn't answer "what's new?" or "who are you?" from real data
- **Solution**: Added `_session_init()` that runs on first message:
  - Reads recent git log
  - Reads AGENTS.md
  - Stores in session context for grounding responses
- **Impact**: Timmy now answers self-knowledge questions from real data

### New API Endpoints
- `POST /api/timmy/refresh-context` — Refresh Timmy's context
- `GET /api/timmy/context` — View current context (debug)
- `GET /api/swarm/status` — Detailed swarm status

### Files Modified
- `src/config.py` — Added `repo_root` auto-detection
- `src/tools/git_tools.py` — Default `repo_path` to repo root
- `src/tools/memory_tool.py` — Added `memory_write` tool
- `src/agents/timmy.py` — Context building, session init, hard rules
- `src/dashboard/routes/agents.py` — New refresh-context endpoint
- `src/dashboard/routes/swarm.py` — New status endpoint

### Testing
- All 18 git tool tests pass
- Context builds successfully with 6 Hands, 4 agents
