"""Distributed Brain — unified memory and task queue.

Provides:
- **UnifiedMemory** — Single API for all memory operations (local SQLite or rqlite)
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

__all__ = [
    "BrainClient",
    "DistributedWorker",
    "LocalEmbedder",
    "UnifiedMemory",
    "get_memory",
]
