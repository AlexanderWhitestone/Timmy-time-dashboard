import sys
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

# ── Stub heavy optional dependencies so tests run without them installed ──────
for _mod in [
    "agno",
    "agno.agent",
    "agno.models",
    "agno.models.ollama",
    "agno.db",
    "agno.db.sqlite",
    "airllm",
]:
    sys.modules.setdefault(_mod, MagicMock())


@pytest.fixture(autouse=True)
def tmp_swarm_db(tmp_path, monkeypatch):
    """Point all SQLite databases to a temp directory for test isolation."""
    # 1. Define temp paths
    swarm_db = tmp_path / "swarm.db"
    timmy_db = tmp_path / "timmy.db"

    # 2. Patch DB_PATH in all relevant modules
    # Swarm subsystem
    monkeypatch.setattr("swarm.tasks.DB_PATH", swarm_db)
    monkeypatch.setattr("swarm.registry.DB_PATH", swarm_db)
    monkeypatch.setattr("swarm.bidder.DB_PATH", swarm_db)
    # Dashboard store (Chat)
    monkeypatch.setattr("dashboard.store.DB_PATH", timmy_db)

    yield swarm_db


@pytest.fixture(autouse=True)
def reset_databases():
    """Clear persistent stores before and after every test."""
    from dashboard.store import message_log
    message_log.clear()

    # Note: tmp_swarm_db fixture handles file isolation, 
    # but we clear just in case of shared process state.
    yield

    message_log.clear()


@pytest.fixture
def client():
    from dashboard.app import app
    with TestClient(app) as c:
        yield c
