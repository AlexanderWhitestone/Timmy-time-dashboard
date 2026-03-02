"""Distributed Brain — Rqlite-based memory and task queue.

A distributed SQLite (rqlite) cluster that runs across all Tailscale devices.
Provides:
- Semantic memory with local embeddings
- Distributed task queue with work stealing
- Automatic replication and failover
"""

from brain.client import BrainClient
from brain.worker import DistributedWorker
from brain.embeddings import LocalEmbedder

__all__ = ["BrainClient", "DistributedWorker", "LocalEmbedder"]
