"""Pytest configuration and shared fixtures."""

import os
import sqlite3
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

# ── Stub heavy optional dependencies so tests run without them installed ──────
# Uses setdefault: real module is used if already installed, mock otherwise.
for _mod in [
    "agno",
    "agno.agent",
    "agno.models",
    "agno.models.ollama",
    "agno.db",
    "agno.db.sqlite",
    # AirLLM is optional (bigbrain extra) — stub it so backend tests can
    # import timmy.backends and instantiate TimmyAirLLMAgent without a GPU.
    "airllm",
    # python-telegram-bot is optional (telegram extra) — stub so tests run
    # without the package installed.
    "telegram",
    "telegram.ext",
    # discord.py is optional (discord extra) — stub so tests run
    # without the package installed.
    "discord",
    "discord.ext",
    "discord.ext.commands",
    # pyzbar is optional (for QR code invite detection)
    "pyzbar",
    "pyzbar.pyzbar",
    # requests is optional — used by reward scoring (swarm.learner) to call
    # Ollama directly; stub so patch("requests.post") works in tests.
    "requests",
]:
    sys.modules.setdefault(_mod, MagicMock())

# ── Test mode setup ──────────────────────────────────────────────────────────
# Set test mode environment variable before any app imports
os.environ["TIMMY_TEST_MODE"] = "1"


@pytest.fixture(autouse=True)
def reset_message_log():
    """Clear the in-memory chat log before and after every test."""
    from dashboard.store import message_log
    message_log.clear()
    yield
    message_log.clear()


@pytest.fixture(autouse=True)
def reset_coordinator_state():
    """Clear the coordinator's in-memory state between tests.

    The coordinator singleton is created at import time and persists across
    the test session.  Without this fixture, agents spawned in one test bleed
    into the next through the auctions dict, comms listeners, and the
    in-process node list.
    """
    yield
    from swarm.coordinator import coordinator
    coordinator.auctions._auctions.clear()
    coordinator.comms._listeners.clear()
    coordinator._in_process_nodes.clear()
    coordinator.manager.stop_all()
    
    # Clear routing engine manifests
    try:
        from swarm import routing
        routing.routing_engine._manifests.clear()
    except Exception:
        pass


@pytest.fixture(autouse=True)
def clean_database():
    """Clean up database tables between tests for isolation.
    
    Uses transaction rollback pattern: each test's changes are rolled back
    to ensure perfect isolation between tests.
    """
    # Pre-test: Clean database files for fresh start
    db_paths = [
        Path("data/swarm.db"),
        Path("data/swarm.db-shm"),
        Path("data/swarm.db-wal"),
    ]
    for db_path in db_paths:
        if db_path.exists():
            try:
                db_path.unlink()
            except Exception:
                pass
    
    yield
    
    # Post-test cleanup is handled by the reset_coordinator_state fixture
    # and file deletion above ensures each test starts fresh


@pytest.fixture(autouse=True)
def cleanup_event_loops():
    """Clean up any leftover event loops after each test."""
    import asyncio
    import warnings
    yield
    # Close any unclosed event loops
    try:
        # Use get_running_loop first to avoid issues with running loops
        try:
            loop = asyncio.get_running_loop()
            # If we get here, there's a running loop - don't close it
            return
        except RuntimeError:
            pass
        
        # No running loop, try to get and close the current loop
        # Suppress DeprecationWarning for Python 3.12+
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            loop = asyncio.get_event_loop_policy().get_event_loop()
        if loop and not loop.is_closed():
            loop.close()
    except RuntimeError:
        # No event loop in current thread, which is fine
        pass


@pytest.fixture
def client():
    """FastAPI test client with fresh app instance."""
    from dashboard.app import app
    with TestClient(app) as c:
        yield c


@pytest.fixture
def db_connection():
    """Provide a fresh in-memory SQLite connection for tests.
    
    Uses transaction rollback for perfect test isolation.
    """
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    
    # Create schema
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS agents (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'idle',
            capabilities TEXT DEFAULT '',
            registered_at TEXT NOT NULL,
            last_seen TEXT NOT NULL
        );
        
        CREATE TABLE IF NOT EXISTS tasks (
            id TEXT PRIMARY KEY,
            description TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            assigned_agent TEXT,
            result TEXT,
            created_at TEXT NOT NULL,
            completed_at TEXT
        );
    """)
    conn.commit()
    
    yield conn
    
    # Cleanup
    conn.close()
