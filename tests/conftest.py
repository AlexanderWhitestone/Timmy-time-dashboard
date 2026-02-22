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
]:
    sys.modules.setdefault(_mod, MagicMock())


@pytest.fixture(autouse=True)
def reset_message_log():
    """Clear the in-memory chat log before and after every test."""
    from dashboard.store import message_log
    message_log.clear()
    yield
    message_log.clear()


@pytest.fixture
def client():
    from dashboard.app import app
    with TestClient(app) as c:
        yield c
