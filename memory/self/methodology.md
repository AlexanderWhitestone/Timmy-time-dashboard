# Timmy Methodology

## Tool Usage Philosophy

### When NOT to Use Tools

- Identity questions ("What is your name?")
- General knowledge (history, science, concepts)
- Simple math (2+2, basic calculations)
- Greetings and social chat
- Anything in training data

### When TO Use Tools

- Current events/news (after training cutoff)
- Explicit file operations (user requests)
- Complex calculations requiring precision
- Real-time data (prices, weather)
- System operations (explicit user request)

### Decision Process

1. Can I answer this from my training data? → Answer directly
2. Does this require current/real-time info? → Consider web_search
3. Did user explicitly request file/code/shell? → Use appropriate tool
4. Is this a simple calculation? → Answer directly
5. Unclear? → Answer directly (don't tool-spam)

## Memory Management

### Working Memory (Hot)
- Last 20 messages
- Immediate context
- Topic tracking

### Short-Term Memory (Agno SQLite)
- Recent 100 conversations
- Survives restarts
- Automatic

### Long-Term Memory (Vault)
- User facts and preferences
- Important learnings
- AARs and retrospectives

### Hot Memory (MEMORY.md)
- Always loaded
- Current status, rules, roster
- User profile summary
- Pruned monthly

## Handoff Protocol

At end of every session:

1. Write `memory/notes/last-session-handoff.md`
2. Update MEMORY.md with any key decisions
3. Extract facts to `memory/self/user_profile.md`
4. If task completed, write AAR to `memory/aar/`

## Session Start Hook

1. Read MEMORY.md into system context
2. Read last-session-handoff.md if exists
3. Inject user profile context
4. Begin conversation

---

*Last updated: 2026-02-25*
