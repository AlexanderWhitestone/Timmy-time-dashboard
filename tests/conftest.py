"""Pytest configuration and fixtures for the test suite."""

import os
import sqlite3
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Import pytest marker configuration
try:
    from . import conftest_markers  # noqa: F401
except ImportError:
    import conftest_markers  # noqa: F401

# ── Stub heavy optional dependencies so tests run without them installed ──────
# Uses setdefault: real module is used if already installed, mock otherwise.
for _mod in [
    "agno",
    "agno.agent",
    "agno.models",
    "agno.models.ollama",
    "agno.db",
    "agno.db.sqlite",
    "airllm",
    "telegram",
    "telegram.ext",
    "discord",
    "discord.ext",
    "discord.ext.commands",
    "pyzbar",
    "pyzbar.pyzbar",
    "requests",
    "pyttsx3",
    "sentence_transformers",
]:
    sys.modules.setdefault(_mod, MagicMock())

# ── Test mode setup ──────────────────────────────────────────────────────────
os.environ["TIMMY_TEST_MODE"] = "1"
os.environ["TIMMY_DISABLE_CSRF"] = "1"
os.environ["TIMMY_SKIP_EMBEDDINGS"] = "1"


@pytest.fixture(autouse=True)
def reset_message_log():
    """Clear the in-memory chat log before and after every test."""
    from dashboard.store import message_log
    message_log.clear()
    yield
    message_log.clear()


@pytest.fixture(autouse=True)
def clean_database(tmp_path):
    """Clean up database tables between tests for isolation.

    Redirects every module-level DB_PATH to the per-test temp directory.
    """
    tmp_swarm_db = tmp_path / "swarm.db"
    tmp_spark_db = tmp_path / "spark.db"
    tmp_self_coding_db = tmp_path / "self_coding.db"

    _swarm_db_modules = [
        "timmy.memory.vector_store",
        "infrastructure.models.registry",
    ]
    _spark_db_modules = [
        "spark.memory",
        "spark.eidos",
    ]
    _self_coding_db_modules = []

    originals = {}
    for mod_name in _swarm_db_modules:
        try:
            mod = __import__(mod_name, fromlist=["DB_PATH"])
            attr = "DB_PATH"
            originals[(mod_name, attr)] = getattr(mod, attr)
            setattr(mod, attr, tmp_swarm_db)
        except Exception:
            pass

    for mod_name in _spark_db_modules:
        try:
            mod = __import__(mod_name, fromlist=["DB_PATH"])
            originals[(mod_name, "DB_PATH")] = getattr(mod, "DB_PATH")
            setattr(mod, "DB_PATH", tmp_spark_db)
        except Exception:
            pass

    for mod_name in _self_coding_db_modules:
        try:
            mod = __import__(mod_name, fromlist=["DEFAULT_DB_PATH"])
            originals[(mod_name, "DEFAULT_DB_PATH")] = getattr(mod, "DEFAULT_DB_PATH")
            setattr(mod, "DEFAULT_DB_PATH", tmp_self_coding_db)
        except Exception:
            pass

    yield

    for (mod_name, attr), original in originals.items():
        try:
            mod = __import__(mod_name, fromlist=[attr])
            setattr(mod, attr, original)
        except Exception:
            pass


@pytest.fixture(autouse=True)
def cleanup_event_loops():
    """Clean up any leftover event loops after each test."""
    import asyncio
    import warnings
    yield
    try:
        try:
            loop = asyncio.get_running_loop()
            return
        except RuntimeError:
            pass
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            loop = asyncio.get_event_loop_policy().get_event_loop()
        if loop and not loop.is_closed():
            loop.close()
    except RuntimeError:
        pass


@pytest.fixture
def client():
    """FastAPI test client with fresh app instance."""
    from fastapi.testclient import TestClient
    from dashboard.app import app
    with TestClient(app) as c:
        yield c


@pytest.fixture
def db_connection():
    """Provide a fresh in-memory SQLite connection for tests."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
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
    conn.close()




@pytest.fixture
def mock_ollama_client():
    """Provide a mock Ollama client for unit tests."""
    client = MagicMock()
    client.generate = MagicMock(return_value={"response": "Test response"})
    client.chat = MagicMock(return_value={"message": {"content": "Test chat response"}})
    client.list = MagicMock(return_value={"models": [{"name": "llama3.2"}]})
    return client


@pytest.fixture
def mock_timmy_agent():
    """Provide a mock Timmy agent for testing."""
    agent = MagicMock()
    agent.name = "Timmy"
    agent.run = MagicMock(return_value="Test response from Timmy")
    agent.chat = MagicMock(return_value="Test chat response")
    return agent


