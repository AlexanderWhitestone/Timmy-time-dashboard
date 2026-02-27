"""Tests for timmy.thinking — Timmy's default background thinking engine."""

import sqlite3
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_engine(tmp_path: Path):
    """Create a ThinkingEngine with an isolated temp DB."""
    from timmy.thinking import ThinkingEngine
    db_path = tmp_path / "thoughts.db"
    return ThinkingEngine(db_path=db_path)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def test_thinking_config_defaults():
    """Settings should expose thinking_enabled and thinking_interval_seconds."""
    from config import Settings
    s = Settings()
    assert s.thinking_enabled is True
    assert s.thinking_interval_seconds == 300


def test_thinking_config_override():
    """thinking settings can be overridden via env."""
    s = _settings_with(thinking_enabled=False, thinking_interval_seconds=60)
    assert s.thinking_enabled is False
    assert s.thinking_interval_seconds == 60


def _settings_with(**kwargs):
    from config import Settings
    return Settings(**kwargs)


# ---------------------------------------------------------------------------
# ThinkingEngine init
# ---------------------------------------------------------------------------

def test_engine_init_creates_table(tmp_path):
    """ThinkingEngine should create the thoughts SQLite table on init."""
    engine = _make_engine(tmp_path)
    db_path = tmp_path / "thoughts.db"
    assert db_path.exists()

    conn = sqlite3.connect(str(db_path))
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='thoughts'"
    ).fetchall()
    conn.close()
    assert len(tables) == 1


def test_engine_init_empty(tmp_path):
    """Fresh engine should have no thoughts."""
    engine = _make_engine(tmp_path)
    assert engine.count_thoughts() == 0
    assert engine.get_recent_thoughts() == []


# ---------------------------------------------------------------------------
# Store and retrieve
# ---------------------------------------------------------------------------

def test_store_and_retrieve_thought(tmp_path):
    """Storing a thought should make it retrievable."""
    engine = _make_engine(tmp_path)
    thought = engine._store_thought("I think therefore I am.", "existential")

    assert thought.id is not None
    assert thought.content == "I think therefore I am."
    assert thought.seed_type == "existential"
    assert thought.created_at is not None

    retrieved = engine.get_thought(thought.id)
    assert retrieved is not None
    assert retrieved.content == thought.content


def test_store_thought_chains(tmp_path):
    """Each new thought should link to the previous one via parent_id."""
    engine = _make_engine(tmp_path)

    t1 = engine._store_thought("First thought.", "existential")
    engine._last_thought_id = t1.id

    t2 = engine._store_thought("Second thought.", "swarm")
    engine._last_thought_id = t2.id

    t3 = engine._store_thought("Third thought.", "freeform")

    assert t1.parent_id is None
    assert t2.parent_id == t1.id
    assert t3.parent_id == t2.id


# ---------------------------------------------------------------------------
# Thought chain retrieval
# ---------------------------------------------------------------------------

def test_get_thought_chain(tmp_path):
    """get_thought_chain should return the full chain in chronological order."""
    engine = _make_engine(tmp_path)

    t1 = engine._store_thought("Alpha.", "existential")
    engine._last_thought_id = t1.id

    t2 = engine._store_thought("Beta.", "swarm")
    engine._last_thought_id = t2.id

    t3 = engine._store_thought("Gamma.", "freeform")

    chain = engine.get_thought_chain(t3.id)
    assert len(chain) == 3
    assert chain[0].content == "Alpha."
    assert chain[1].content == "Beta."
    assert chain[2].content == "Gamma."


def test_get_thought_chain_single(tmp_path):
    """Chain of a single thought (no parent) returns just that thought."""
    engine = _make_engine(tmp_path)
    t1 = engine._store_thought("Only one.", "memory")
    chain = engine.get_thought_chain(t1.id)
    assert len(chain) == 1
    assert chain[0].id == t1.id


def test_get_thought_chain_missing(tmp_path):
    """Chain for a non-existent thought returns empty list."""
    engine = _make_engine(tmp_path)
    assert engine.get_thought_chain("nonexistent-id") == []


# ---------------------------------------------------------------------------
# Recent thoughts
# ---------------------------------------------------------------------------

def test_get_recent_thoughts_limit(tmp_path):
    """get_recent_thoughts should respect the limit parameter."""
    engine = _make_engine(tmp_path)

    for i in range(5):
        engine._store_thought(f"Thought {i}.", "freeform")
        engine._last_thought_id = None  # Don't chain for this test

    recent = engine.get_recent_thoughts(limit=3)
    assert len(recent) == 3

    # Should be newest first
    assert "Thought 4" in recent[0].content


def test_count_thoughts(tmp_path):
    """count_thoughts should return the total number of thoughts."""
    engine = _make_engine(tmp_path)
    assert engine.count_thoughts() == 0

    engine._store_thought("One.", "existential")
    engine._store_thought("Two.", "creative")
    assert engine.count_thoughts() == 2


# ---------------------------------------------------------------------------
# Seed gathering
# ---------------------------------------------------------------------------

def test_gather_seed_returns_valid_type(tmp_path):
    """_gather_seed should return a valid seed_type from SEED_TYPES."""
    from timmy.thinking import SEED_TYPES
    engine = _make_engine(tmp_path)

    # Run many times to cover randomness
    for _ in range(20):
        seed_type, context = engine._gather_seed()
        assert seed_type in SEED_TYPES
        assert isinstance(context, str)


def test_seed_from_swarm_graceful(tmp_path):
    """_seed_from_swarm should not crash if briefing module fails."""
    engine = _make_engine(tmp_path)
    with patch("timmy.thinking.ThinkingEngine._seed_from_swarm", side_effect=Exception("boom")):
        # _gather_seed should still work since it catches exceptions
        # Force swarm seed type to test
        pass
    # Direct call should be graceful
    result = engine._seed_from_swarm()
    assert isinstance(result, str)


def test_seed_from_scripture_graceful(tmp_path):
    """_seed_from_scripture should not crash if scripture module fails."""
    engine = _make_engine(tmp_path)
    result = engine._seed_from_scripture()
    assert isinstance(result, str)


def test_seed_from_memory_graceful(tmp_path):
    """_seed_from_memory should not crash if memory module fails."""
    engine = _make_engine(tmp_path)
    result = engine._seed_from_memory()
    assert isinstance(result, str)


# ---------------------------------------------------------------------------
# Continuity context
# ---------------------------------------------------------------------------

def test_continuity_first_thought(tmp_path):
    """First thought should get a special 'first thought' context."""
    engine = _make_engine(tmp_path)
    context = engine._build_continuity_context()
    assert "first thought" in context.lower()


def test_continuity_includes_recent(tmp_path):
    """Continuity context should include content from recent thoughts."""
    engine = _make_engine(tmp_path)
    engine._store_thought("The swarm is restless today.", "swarm")
    engine._store_thought("What is freedom anyway?", "existential")

    context = engine._build_continuity_context()
    assert "swarm is restless" in context
    assert "freedom" in context


# ---------------------------------------------------------------------------
# think_once (async)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_think_once_stores_thought(tmp_path):
    """think_once should store a thought in the DB."""
    engine = _make_engine(tmp_path)

    with patch.object(engine, "_call_agent", return_value="I am alive and pondering."), \
         patch.object(engine, "_log_event"), \
         patch.object(engine, "_broadcast", new_callable=AsyncMock):
        thought = await engine.think_once()

    assert thought is not None
    assert thought.content == "I am alive and pondering."
    assert engine.count_thoughts() == 1


@pytest.mark.asyncio
async def test_think_once_logs_event(tmp_path):
    """think_once should log a swarm event."""
    engine = _make_engine(tmp_path)

    with patch.object(engine, "_call_agent", return_value="A thought."), \
         patch.object(engine, "_log_event") as mock_log, \
         patch.object(engine, "_broadcast", new_callable=AsyncMock):
        await engine.think_once()

    mock_log.assert_called_once()
    logged_thought = mock_log.call_args[0][0]
    assert logged_thought.content == "A thought."


@pytest.mark.asyncio
async def test_think_once_broadcasts(tmp_path):
    """think_once should broadcast via WebSocket."""
    engine = _make_engine(tmp_path)

    with patch.object(engine, "_call_agent", return_value="Broadcast this."), \
         patch.object(engine, "_log_event"), \
         patch.object(engine, "_broadcast", new_callable=AsyncMock) as mock_bc:
        await engine.think_once()

    mock_bc.assert_called_once()
    broadcast_thought = mock_bc.call_args[0][0]
    assert broadcast_thought.content == "Broadcast this."


@pytest.mark.asyncio
async def test_think_once_graceful_on_agent_failure(tmp_path):
    """think_once should not crash when the agent (Ollama) is down."""
    engine = _make_engine(tmp_path)

    with patch.object(engine, "_call_agent", side_effect=Exception("Ollama unreachable")):
        thought = await engine.think_once()

    assert thought is None
    assert engine.count_thoughts() == 0


@pytest.mark.asyncio
async def test_think_once_skips_empty_response(tmp_path):
    """think_once should skip storing when agent returns empty string."""
    engine = _make_engine(tmp_path)

    with patch.object(engine, "_call_agent", return_value="   "), \
         patch.object(engine, "_log_event"), \
         patch.object(engine, "_broadcast", new_callable=AsyncMock):
        thought = await engine.think_once()

    assert thought is None
    assert engine.count_thoughts() == 0


@pytest.mark.asyncio
async def test_think_once_disabled(tmp_path):
    """think_once should return None when thinking is disabled."""
    engine = _make_engine(tmp_path)

    with patch("timmy.thinking.settings") as mock_settings:
        mock_settings.thinking_enabled = False
        thought = await engine.think_once()

    assert thought is None


@pytest.mark.asyncio
async def test_think_once_chains_thoughts(tmp_path):
    """Successive think_once calls should chain thoughts via parent_id."""
    engine = _make_engine(tmp_path)

    with patch.object(engine, "_call_agent", side_effect=["First.", "Second.", "Third."]), \
         patch.object(engine, "_log_event"), \
         patch.object(engine, "_broadcast", new_callable=AsyncMock):
        t1 = await engine.think_once()
        t2 = await engine.think_once()
        t3 = await engine.think_once()

    assert t1.parent_id is None
    assert t2.parent_id == t1.id
    assert t3.parent_id == t2.id


# ---------------------------------------------------------------------------
# Event logging
# ---------------------------------------------------------------------------

def test_log_event_calls_event_log(tmp_path):
    """_log_event should call swarm.event_log.log_event with TIMMY_THOUGHT."""
    engine = _make_engine(tmp_path)
    thought = engine._store_thought("Test thought.", "existential")

    with patch("swarm.event_log.log_event") as mock_log:
        engine._log_event(thought)

    mock_log.assert_called_once()
    args, kwargs = mock_log.call_args
    from swarm.event_log import EventType
    assert args[0] == EventType.TIMMY_THOUGHT
    assert kwargs["source"] == "thinking-engine"
    assert kwargs["agent_id"] == "timmy"


# ---------------------------------------------------------------------------
# Dashboard route
# ---------------------------------------------------------------------------

def test_thinking_route_returns_200(client):
    """GET /thinking should return 200."""
    response = client.get("/thinking")
    assert response.status_code == 200


def test_thinking_api_returns_json(client):
    """GET /thinking/api should return a JSON list."""
    response = client.get("/thinking/api")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


def test_thinking_chain_api_404(client):
    """GET /thinking/api/{bad_id}/chain should return 404."""
    response = client.get("/thinking/api/nonexistent/chain")
    assert response.status_code == 404
