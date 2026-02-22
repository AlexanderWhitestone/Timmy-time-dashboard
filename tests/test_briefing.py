"""Tests for timmy/briefing.py — morning briefing engine."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from timmy.briefing import (
    Briefing,
    BriefingEngine,
    _load_latest,
    _save_briefing,
    is_fresh,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def tmp_db(tmp_path):
    return tmp_path / "test_briefings.db"


@pytest.fixture()
def engine(tmp_db):
    return BriefingEngine(db_path=tmp_db)


def _make_briefing(offset_minutes: int = 0) -> Briefing:
    """Create a Briefing with generated_at offset by offset_minutes from now."""
    now = datetime.now(timezone.utc) - timedelta(minutes=offset_minutes)
    return Briefing(
        generated_at=now,
        summary="Good morning. All quiet on the swarm front.",
        approval_items=[],
        period_start=now - timedelta(hours=6),
        period_end=now,
    )


# ---------------------------------------------------------------------------
# Briefing dataclass
# ---------------------------------------------------------------------------

def test_briefing_fields():
    b = _make_briefing()
    assert isinstance(b.generated_at, datetime)
    assert isinstance(b.summary, str)
    assert isinstance(b.approval_items, list)
    assert isinstance(b.period_start, datetime)
    assert isinstance(b.period_end, datetime)


def test_briefing_default_period_is_6_hours():
    b = Briefing(generated_at=datetime.now(timezone.utc), summary="test")
    delta = b.period_end - b.period_start
    assert abs(delta.total_seconds() - 6 * 3600) < 5  # within 5 seconds


# ---------------------------------------------------------------------------
# is_fresh
# ---------------------------------------------------------------------------

def test_is_fresh_recent_briefing():
    b = _make_briefing(offset_minutes=5)
    assert is_fresh(b) is True


def test_is_fresh_stale_briefing():
    b = _make_briefing(offset_minutes=45)
    assert is_fresh(b) is False


def test_is_fresh_custom_max_age():
    b = _make_briefing(offset_minutes=10)
    assert is_fresh(b, max_age_minutes=5) is False
    assert is_fresh(b, max_age_minutes=15) is True


# ---------------------------------------------------------------------------
# SQLite cache (save/load round-trip)
# ---------------------------------------------------------------------------

def test_save_and_load_briefing(tmp_db):
    b = _make_briefing()
    _save_briefing(b, db_path=tmp_db)
    loaded = _load_latest(db_path=tmp_db)
    assert loaded is not None
    assert loaded.summary == b.summary


def test_load_latest_returns_none_when_empty(tmp_db):
    assert _load_latest(db_path=tmp_db) is None


def test_load_latest_returns_most_recent(tmp_db):
    old = _make_briefing(offset_minutes=60)
    new = _make_briefing(offset_minutes=5)
    _save_briefing(old, db_path=tmp_db)
    _save_briefing(new, db_path=tmp_db)
    loaded = _load_latest(db_path=tmp_db)
    assert loaded is not None
    # Should return the newer one (generated_at closest to now)
    assert abs((loaded.generated_at.replace(tzinfo=timezone.utc) - new.generated_at).total_seconds()) < 5


# ---------------------------------------------------------------------------
# BriefingEngine.needs_refresh
# ---------------------------------------------------------------------------

def test_needs_refresh_when_no_cache(engine, tmp_db):
    assert engine.needs_refresh() is True


def test_needs_refresh_false_when_fresh(engine, tmp_db):
    fresh = _make_briefing(offset_minutes=5)
    _save_briefing(fresh, db_path=tmp_db)
    assert engine.needs_refresh() is False


def test_needs_refresh_true_when_stale(engine, tmp_db):
    stale = _make_briefing(offset_minutes=45)
    _save_briefing(stale, db_path=tmp_db)
    assert engine.needs_refresh() is True


# ---------------------------------------------------------------------------
# BriefingEngine.get_cached
# ---------------------------------------------------------------------------

def test_get_cached_returns_none_when_empty(engine):
    assert engine.get_cached() is None


def test_get_cached_returns_briefing(engine, tmp_db):
    b = _make_briefing()
    _save_briefing(b, db_path=tmp_db)
    cached = engine.get_cached()
    assert cached is not None
    assert cached.summary == b.summary


# ---------------------------------------------------------------------------
# BriefingEngine.generate  (agent mocked)
# ---------------------------------------------------------------------------

def test_generate_returns_briefing(engine):
    with patch.object(engine, "_call_agent", return_value="All is well."):
        with patch.object(engine, "_load_pending_items", return_value=[]):
            b = engine.generate()
    assert isinstance(b, Briefing)
    assert b.summary == "All is well."
    assert b.approval_items == []


def test_generate_persists_to_cache(engine, tmp_db):
    with patch.object(engine, "_call_agent", return_value="Morning report."):
        with patch.object(engine, "_load_pending_items", return_value=[]):
            engine.generate()
    cached = _load_latest(db_path=tmp_db)
    assert cached is not None
    assert cached.summary == "Morning report."


def test_generate_handles_agent_failure(engine):
    with patch.object(engine, "_call_agent", side_effect=Exception("Ollama down")):
        with patch.object(engine, "_load_pending_items", return_value=[]):
            b = engine.generate()
    assert isinstance(b, Briefing)
    assert "offline" in b.summary.lower() or "Morning" in b.summary


# ---------------------------------------------------------------------------
# BriefingEngine.get_or_generate
# ---------------------------------------------------------------------------

def test_get_or_generate_uses_cache_when_fresh(engine, tmp_db):
    fresh = _make_briefing(offset_minutes=5)
    _save_briefing(fresh, db_path=tmp_db)

    with patch.object(engine, "generate") as mock_gen:
        with patch.object(engine, "_load_pending_items", return_value=[]):
            result = engine.get_or_generate()
    mock_gen.assert_not_called()
    assert result.summary == fresh.summary


def test_get_or_generate_generates_when_stale(engine, tmp_db):
    stale = _make_briefing(offset_minutes=45)
    _save_briefing(stale, db_path=tmp_db)

    with patch.object(engine, "_call_agent", return_value="New report."):
        with patch.object(engine, "_load_pending_items", return_value=[]):
            result = engine.get_or_generate()
    assert result.summary == "New report."


def test_get_or_generate_generates_when_no_cache(engine):
    with patch.object(engine, "_call_agent", return_value="Fresh report."):
        with patch.object(engine, "_load_pending_items", return_value=[]):
            result = engine.get_or_generate()
    assert result.summary == "Fresh report."


# ---------------------------------------------------------------------------
# BriefingEngine._call_agent  (unit — mocked agent)
# ---------------------------------------------------------------------------

def test_call_agent_returns_content(engine):
    mock_run = MagicMock()
    mock_run.content = "Agent said hello."
    mock_agent = MagicMock()
    mock_agent.run.return_value = mock_run

    with patch("timmy.briefing.BriefingEngine._call_agent", wraps=engine._call_agent):
        with patch("timmy.agent.create_timmy", return_value=mock_agent):
            result = engine._call_agent("Say hello.")
    # _call_agent calls create_timmy internally; result from content attr
    assert isinstance(result, str)


def test_call_agent_falls_back_on_exception(engine):
    with patch("timmy.agent.create_timmy", side_effect=Exception("no ollama")):
        result = engine._call_agent("prompt")
    assert "offline" in result.lower()


# ---------------------------------------------------------------------------
# Push notification hook
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_notify_briefing_ready_logs(caplog):
    """notify_briefing_ready should log and call notifier.notify."""
    from notifications.push import notify_briefing_ready, PushNotifier

    b = _make_briefing()

    with patch("notifications.push.notifier") as mock_notifier:
        await notify_briefing_ready(b)
        mock_notifier.notify.assert_called_once()
        call_kwargs = mock_notifier.notify.call_args
        assert "Briefing" in call_kwargs[1]["title"] or "Briefing" in call_kwargs[0][0]
