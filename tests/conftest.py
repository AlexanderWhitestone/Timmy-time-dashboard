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
]:
    sys.modules.setdefault(_mod, MagicMock())


@pytest.fixture(autouse=True)
def reset_databases():
    """Clear persistent stores before and after every test."""
    # Reset MessageLog
    from dashboard.store import message_log
    message_log.clear()

    # Reset Swarm Registry & Tasks
    import sqlite3
    from pathlib import Path
    swarm_db = Path("data/swarm.db")
    if swarm_db.exists():
        conn = sqlite3.connect(str(swarm_db))
        conn.execute("DELETE FROM agents")
        conn.execute("DELETE FROM tasks")
        conn.execute("DELETE FROM auctions")
        conn.execute("DELETE FROM bids")
        conn.commit()
        conn.close()

    yield

    message_log.clear()
    if swarm_db.exists():
        conn = sqlite3.connect(str(swarm_db))
        conn.execute("DELETE FROM agents")
        conn.execute("DELETE FROM tasks")
        conn.execute("DELETE FROM auctions")
        conn.execute("DELETE FROM bids")
        conn.commit()
        conn.close()


@pytest.fixture
def client():
    from dashboard.app import app
    with TestClient(app) as c:
        yield c
