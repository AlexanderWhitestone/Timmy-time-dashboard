# Integration Evaluation: VibeShip Spark Intelligence

**Date:** 2026-02-22
**Verdict:** Low practical value as an integration into Timmy. Moderate value as a personal developer tool while working *on* Timmy.

---

## What Spark Is

[Spark Intelligence](https://spark.vibeship.co) is a self-evolving AI companion from the VibeShip ecosystem. It runs a 12-stage pipeline that captures events from coding agents (Claude Code, Cursor), distills insights, and surfaces guidance back to the developer. It stores state locally in `~/.spark/` as JSON/JSONL and requires no external API calls.

Key capabilities:
- Event capture via agent hooks (PreToolUse/PostToolUse)
- Memory capture with importance scoring
- Cognitive learning and insight extraction (EIDOS loop)
- Advisory system that surfaces context-appropriate guidance
- Obsidian Observatory (465+ auto-generated markdown pages)
- CLI tools (`spark status`, `spark learnings`, `spark promote`)

---

## Overlap With Existing Timmy Subsystems

| Capability | Timmy (existing) | Spark |
|---|---|---|
| Agent orchestration | Swarm coordinator with bidding, registry, task lifecycle | Event capture from external agents |
| Memory/persistence | SQLite via Agno + swarm.db | JSON/JSONL in ~/.spark/ |
| Learning from outcomes | Bid statistics, task completion tracking | EIDOS prediction-evaluation loop |
| Advisory/guidance | System prompts, persona definitions | Ranked recommendations to developer |
| Local-first | Yes (Ollama, SQLite, no cloud) | Yes (no external API calls) |

Significant overlap exists in memory, orchestration, and outcome tracking. The implementations differ in design goals and storage format, but the functional territory is largely the same.

---

## Why Integration Adds Little Value

### 1. Fundamental purpose mismatch

Spark is a **developer meta-tool** -- it watches how a human codes and offers guidance. Timmy is an **autonomous agent system** that runs tasks itself. Spark learns from developer interactions with code editors; Timmy *is* the agent doing the work. These are different audiences solving different problems.

### 2. No native hook for custom agent frameworks

Spark integrates with Claude Code (PreToolUse/PostToolUse hooks), Cursor (tasks.json), and OpenClaw (session JSONL tailers). It does not hook into custom agent frameworks like Timmy's Agno-based system. Integrating would require writing custom event emitters to bridge the two systems -- non-trivial work for unclear benefit.

### 3. Advisory system targets humans, not agents

Spark's advisory output is designed to surface guidance to a developer at their editor. Timmy's agents follow system prompts and bid on tasks autonomously. There's no consumption point in Timmy's architecture for "hey, last time you did X it went poorly" style recommendations.

### 4. Redundant persistence layer

Adding Spark would introduce a parallel persistence mechanism (JSON/JSONL files) alongside Timmy's existing SQLite databases. This creates data fragmentation without consolidating anything.

### 5. Complexity budget

Timmy already manages Ollama, SQLite (3 databases), optional Redis, optional LND, optional Telegram, WebSockets, and Docker orchestration. Adding another stateful subsystem with a 12-stage pipeline increases operational surface area for marginal gain.

---

## Where Spark Could Help (Outside of Timmy)

If you use Claude Code or Cursor to develop Timmy, Spark could learn your development patterns and surface useful reminders about past decisions, preferred patterns, and things that went wrong. This is a **developer workflow** benefit, not a **Timmy runtime** benefit.

The Obsidian Observatory feature could also be interesting for reviewing your own coding patterns over time.

---

## Recommendation

**Do not integrate Spark into Timmy's agent system.** The architectures serve fundamentally different purposes, the overlap with existing subsystems creates redundancy, and the integration effort would be non-trivial with no clear payoff.

If you want Spark's learning-from-outcomes concept inside Timmy, a better path would be extending the existing `src/swarm/stats.py` module to feed bid/task completion data back into agent persona tuning -- using the infrastructure you already have.
