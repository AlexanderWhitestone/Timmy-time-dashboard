"""Distributed Brain — Timmy's unified memory and task queue.

The brain is where Timmy lives. Identity is memory, not process.

Provides:
- **UnifiedMemory** — Single API for all memory operations (local SQLite or rqlite)
- **Canonical Identity** — One source of truth for who Timmy is
- **BrainClient** — Direct rqlite interface for distributed operation
- **DistributedWorker** — Task execution on Tailscale nodes
- **LocalEmbedder** — Sentence-transformer embeddings (local, no cloud)

Default backend is local SQLite (data/brain.db). Set RQLITE_URL to
upgrade to distributed rqlite over Tailscale — same API, replicated.
"""

from brain.client import BrainClient
from brain.worker import DistributedWorker
from brain.embeddings import LocalEmbedder
from brain.memory import UnifiedMemory, get_memory
from brain.identity import get_canonical_identity, get_identity_for_prompt

__all__ = [
    "BrainClient",
    "DistributedWorker",
    "LocalEmbedder",
    "UnifiedMemory",
    "get_memory",
    "get_canonical_identity",
    "get_identity_for_prompt",
]
