# Plan: Nostr-Native Agent Marketplace

**Status:** Proposed
**Author:** Claude (Architect Review)
**Date:** 2026-02-23
**Target version:** v2.5 (bridge between Exodus and Revelation)

---

## The One-Sentence Pitch

**Make Timmy a Nostr-native AI agent that earns sats by completing tasks posted by anyone on the open internet — no accounts, no cloud, no platform.**

---

## Why This Is the Single Highest-Leverage Addition

Every subsystem in Timmy Time already exists in isolation. The swarm bids on
tasks — but only tasks the local user posts. Lightning gates API access — but
only to localhost. Agents build reputation — but only in a SQLite file nobody
else can see. The marketplace route exists — but has no marketplace.

Nostr is the keystone that snaps all of these together into something that
has never been built before: **a sovereign, self-hosted AI agent that
participates in an open economy.**

### What Timmy already has (and what Nostr unlocks)

| Existing Subsystem | Current State | With Nostr |
|---|---|---|
| **Swarm + auctions** | Tasks from local dashboard only | Tasks arrive from any Nostr user worldwide |
| **Lightning payments** | Mock sats, L402 on localhost | Real sats flow in via Nostr zaps as payment for task execution |
| **Learner / reputation** | SQLite metrics, invisible | Zap receipts on Timmy's npub = public proof of competence |
| **Marketplace route** | Skeleton HTML, no data | Populated by NIP-89 service announcements from peer Timmys on relays |
| **Federation (v3 planned)** | Not started, no protocol chosen | Nostr relays ARE the federation layer — zero custom protocol needed |
| **Persona agents** | 6 agents with capabilities | Externally browsable via NIP-89 handler metadata |
| **WebSocket live feed** | Local dashboard only | Nostr events mirror to relays; anyone can subscribe to Timmy's activity |

### Why Nostr and not a custom API / REST marketplace

1. **No server required.** Timmy connects to public relays as a client. No DNS, no ports, no TLS certs. Turn on your laptop and you're live.
2. **Identity is a keypair.** Timmy gets an npub. No OAuth, no API keys, no accounts on anyone's platform.
3. **Discovery is built in.** NIP-89 (Application Handlers) lets Timmy announce "I'm an AI agent that handles these task types." Any Nostr client can find it.
4. **Payment is built in.** Nostr zaps are Lightning invoices wrapped in events. The existing payment handler just needs a thin adapter.
5. **Reputation is built in.** Zaps received = payment history. NIP-32 labels = client ratings. No custom reputation system to build.
6. **Community alignment.** The Nostr + Bitcoin + sovereignty Venn diagram is exactly Timmy's target audience. This is where the early adopters live.

---

## How It Works (End-to-End Flow)

```
  NOSTR USER                         TIMMY INSTANCE
  ──────────                         ──────────────
  1. Discovers Timmy's npub
     via NIP-89 handler event
     on public relays
                    ─── NIP-04 DM ──────>
  2. Sends task:                     3. Coordinator receives task
     "Summarize this PDF"               Creates task, opens auction
     + optional budget hint              Persona agents bid
                                         Winner selected
                    <── NIP-04 DM ──────
  4. Receives Lightning             5. Generates bolt11 invoice
     invoice for 50 sats               via payment_handler
                                        (mock or real LND)
  6. Pays invoice via
     any Lightning wallet
                    ─── Zap receipt ────>
                                     7. Payment confirmed
                                        Winning agent executes task
                                        via ToolExecutor
                    <── NIP-04 DM ──────
  8. Receives result:               9. Sends result as DM
     "Here's your summary..."          Records outcome in learner
                                        Publishes completion event
```

---

## Technical Architecture

### New module: `src/nostr/`

```
src/nostr/
    __init__.py
    relay.py          # Connect to relays, subscribe, publish
    identity.py       # Keypair management (nsec stored in .env)
    handler.py        # NIP-89 service announcement
    task_bridge.py    # Nostr DM -> coordinator.post_task() bridge
    payment_bridge.py # Invoice generation + zap receipt verification
    reputation.py     # Publish/read NIP-32 labels for agent ratings
```

### Integration points (no rewrites — all additive)

```python
# task_bridge.py — the critical 50 lines
class NostrTaskBridge:
    """Bridges Nostr DMs to the swarm coordinator."""

    def __init__(self, coordinator, payment_handler, relay_pool):
        self.coordinator = coordinator
        self.payments = payment_handler
        self.relays = relay_pool

    async def on_task_request(self, event: NostrEvent):
        """Handle incoming task DM."""
        sender_npub = event.pubkey
        description = event.content  # decrypted NIP-04

        # Create task in the existing swarm
        task = self.coordinator.post_task(description)

        # Run auction (existing flow)
        winner = await self.coordinator.run_auction_and_assign(task.id)
        if not winner:
            await self.relays.send_dm(sender_npub,
                "No agents available for this task.")
            return

        # Generate Lightning invoice (existing payment_handler)
        invoice = self.payments.create_invoice(
            amount_sats=winner.bid_sats,
            memo=f"Timmy task: {description[:50]}"
        )

        # Send invoice back via Nostr DM
        await self.relays.send_dm(sender_npub,
            f"Invoice: {invoice.payment_request}")

        # Wait for payment (poll or subscribe to zap receipts)
        # On payment: execute task, send result as DM
```

### Config additions (`.env`)

```bash
# Nostr identity — generate once, keep forever
NOSTR_NSEC=nsec1...           # Private key (generate with `timmy nostr keygen`)
NOSTR_RELAYS=wss://relay.damus.io,wss://nos.lol,wss://relay.snort.social

# Feature flag — off by default, sovereignty preserved
NOSTR_ENABLED=false

# Rate limiting — prevent abuse from the open internet
NOSTR_MAX_TASKS_PER_HOUR=10
NOSTR_MIN_TASK_SATS=10        # Minimum payment to post a task
```

### CLI additions

```bash
timmy nostr keygen             # Generate keypair, print npub
timmy nostr announce           # Publish NIP-89 handler event
timmy nostr status             # Show relay connections, pending tasks
timmy nostr listen             # Start listening for task DMs (also starts with `make dev`)
```

---

## Implementation Phases

### Phase 1: Identity + Relay Connection (foundation)
- Generate/load Nostr keypair from `.env`
- Connect to configurable relay list
- Publish a NIP-89 handler event announcing Timmy's capabilities
- Subscribe to NIP-04 DMs addressed to Timmy's npub
- Tests: relay connection mock, event serialization, keypair management

### Phase 2: Task Bridge (core value)
- Parse incoming DMs as task requests
- Bridge to `coordinator.post_task()` + `run_auction_and_assign()`
- Generate Lightning invoice and reply via DM
- On payment confirmation, execute task and reply with result
- Tests: full flow mock (DM -> task -> auction -> invoice -> result -> DM)

### Phase 3: Reputation + Discovery (network effects)
- Publish task completion events (anonymized) for social proof
- Read/write NIP-32 labels for agent ratings
- Populate `/marketplace` dashboard with peer Timmy instances found on relays
- Tests: reputation scoring, NIP-32 round-trip, marketplace data hydration

### Phase 4: Federation (the endgame)
- Timmy instances discover each other via NIP-89
- Cross-instance task delegation: if local swarm can't handle a task, forward to a peer Timmy
- Peer-to-peer Lightning settlement between Timmys
- The v3 "federation" roadmap item — delivered via Nostr, not a custom protocol

---

## Why This Is Radical

No one has built this. There are:
- AI agents that run locally (Ollama, llama.cpp) — but they can't be hired.
- AI agents you can pay (OpenAI, Anthropic) — but they're cloud-hosted corporate services.
- Nostr bots that respond to mentions — but they don't have swarms, auctions, or Lightning economics.
- Bitcoin-denominated AI ideas — but they're all vaporware or centralized.

**Timmy on Nostr is the first sovereign AI agent that earns Bitcoin for its work on an open protocol.** It's fully local, fully self-hosted, and fully permissionless. No platform takes a cut. No API key grants access. No corporation can shut it down.

This is what "sovereign AI" actually means. Not "runs on localhost." **Runs on localhost AND participates in the global economy on its own terms.**

---

## Dependencies

| Dependency | Package | Sovereignty | Notes |
|---|---|---|---|
| Nostr client | `nostr-sdk` or `pynostr` | 9/10 | Connects to public relays (replaceable) |
| NIP-04 encryption | Built into nostr-sdk | 10/10 | Local crypto, no external calls |
| Relay connections | WebSocket | 10/10 | Standard protocol, any relay works |

The sovereignty audit score stays at 9+/10. Nostr relays are interchangeable
commodity infrastructure — if one goes down, connect to another. Timmy never
depends on any specific relay.

---

## What This Replaces on the Roadmap

| Original v3 Item | Replaced By |
|---|---|
| "Federation — multiple Timmy instances discover and bid on each other's tasks" | Phase 4 of this plan (Nostr IS federation) |
| "Redis pub/sub replacing SQLite polling for high-throughput swarms" | Still relevant but lower priority — Nostr handles cross-instance comms |

Everything else on the v2/v3 roadmap is unchanged and complementary.

---

## Risk Assessment

| Risk | Likelihood | Mitigation |
|---|---|---|
| Nostr relay downtime | Medium | Connect to 3+ relays; retry with backoff |
| Spam/abuse from open internet | High | Rate limiting + minimum sats per task (spam costs money) |
| Lightning payment failures | Medium | Existing mock fallback; timeout + refund flow |
| Nostr protocol changes | Low | NIPs are stable; NIP-04 and NIP-89 are mature |
| Scope creep | Medium | Feature flag (`NOSTR_ENABLED=false`); ship Phase 1-2 first |

The critical risk mitigation is **economic**: every task requires a Lightning
payment. Spam costs real sats. This is the most elegant spam filter ever
designed.

---

## Success Metrics

- A non-local user posts a task to Timmy via Nostr DM, pays the invoice, and receives a result — all without touching the dashboard
- Timmy's npub accumulates zap receipts that serve as a public portfolio
- Two Timmy instances on different machines discover each other on a relay and delegate a task

---

*This is the single addition that transforms Timmy from a local AI dashboard into a protocol-level participant in the sovereign internet economy.*
