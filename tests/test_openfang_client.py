"""Chunk 2: OpenFang HTTP client — test first, implement second.

Tests cover:
- Health check returns False when unreachable
- Health check TTL caching
- execute_hand() rejects unknown hands
- execute_hand() success with mocked HTTP
- execute_hand() graceful degradation on error
- Convenience wrappers call the correct hand
"""

import asyncio
import json
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Health checks
# ---------------------------------------------------------------------------

def test_health_check_false_when_unreachable():
    """Client should report unhealthy when OpenFang is not running."""
    from infrastructure.openfang.client import OpenFangClient

    client = OpenFangClient(base_url="http://localhost:19999")
    assert client._check_health() is False


def test_health_check_caching():
    """Repeated .healthy calls within TTL should not re-check."""
    from infrastructure.openfang.client import OpenFangClient

    client = OpenFangClient(base_url="http://localhost:19999")
    client._health_cache_ttl = 9999  # very long TTL
    # Force a first check (will be False)
    _ = client.healthy
    assert client._healthy is False

    # Manually flip the cached value — next access should use cache
    client._healthy = True
    assert client.healthy is True  # still cached, no re-check


# ---------------------------------------------------------------------------
# execute_hand — unknown hand
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_execute_hand_unknown_hand():
    """Requesting an unknown hand returns success=False immediately."""
    from infrastructure.openfang.client import OpenFangClient

    client = OpenFangClient(base_url="http://localhost:19999")
    result = await client.execute_hand("nonexistent_hand", {})
    assert result.success is False
    assert "Unknown hand" in result.error


# ---------------------------------------------------------------------------
# execute_hand — success path (mocked HTTP)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_execute_hand_success_mocked():
    """When OpenFang returns 200 with output, HandResult.success is True."""
    from infrastructure.openfang.client import OpenFangClient

    response_body = json.dumps({
        "success": True,
        "output": "Page loaded successfully",
        "metadata": {"url": "https://example.com"},
    }).encode()

    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.read.return_value = response_body
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_resp):
        client = OpenFangClient(base_url="http://localhost:8080")
        result = await client.execute_hand("browser", {"url": "https://example.com"})

    assert result.success is True
    assert result.output == "Page loaded successfully"
    assert result.hand == "browser"
    assert result.latency_ms > 0


# ---------------------------------------------------------------------------
# execute_hand — graceful degradation on connection error
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_execute_hand_connection_error():
    """When OpenFang is unreachable, HandResult.success is False (no crash)."""
    from infrastructure.openfang.client import OpenFangClient

    client = OpenFangClient(base_url="http://localhost:19999")
    result = await client.execute_hand("browser", {"url": "https://example.com"})

    assert result.success is False
    assert result.error  # non-empty error message
    assert result.hand == "browser"


# ---------------------------------------------------------------------------
# Convenience wrappers
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_browse_calls_browser_hand():
    """browse() should delegate to execute_hand('browser', ...)."""
    from infrastructure.openfang.client import OpenFangClient

    client = OpenFangClient(base_url="http://localhost:19999")

    calls = []
    original = client.execute_hand

    async def spy(hand, params, **kw):
        calls.append((hand, params))
        return await original(hand, params, **kw)

    client.execute_hand = spy
    await client.browse("https://example.com", "click button")

    assert len(calls) == 1
    assert calls[0][0] == "browser"
    assert calls[0][1]["url"] == "https://example.com"


@pytest.mark.asyncio
async def test_collect_calls_collector_hand():
    """collect() should delegate to execute_hand('collector', ...)."""
    from infrastructure.openfang.client import OpenFangClient

    client = OpenFangClient(base_url="http://localhost:19999")

    calls = []
    original = client.execute_hand

    async def spy(hand, params, **kw):
        calls.append((hand, params))
        return await original(hand, params, **kw)

    client.execute_hand = spy
    await client.collect("example.com", depth="deep")

    assert len(calls) == 1
    assert calls[0][0] == "collector"
    assert calls[0][1]["target"] == "example.com"


@pytest.mark.asyncio
async def test_predict_calls_predictor_hand():
    """predict() should delegate to execute_hand('predictor', ...)."""
    from infrastructure.openfang.client import OpenFangClient

    client = OpenFangClient(base_url="http://localhost:19999")

    calls = []
    original = client.execute_hand

    async def spy(hand, params, **kw):
        calls.append((hand, params))
        return await original(hand, params, **kw)

    client.execute_hand = spy
    await client.predict("Will BTC hit 100k?", horizon="1m")

    assert len(calls) == 1
    assert calls[0][0] == "predictor"
    assert calls[0][1]["question"] == "Will BTC hit 100k?"


# ---------------------------------------------------------------------------
# HandResult dataclass
# ---------------------------------------------------------------------------

def test_hand_result_defaults():
    """HandResult should have sensible defaults."""
    from infrastructure.openfang.client import HandResult

    r = HandResult(hand="browser", success=True)
    assert r.output == ""
    assert r.error == ""
    assert r.latency_ms == 0.0
    assert r.metadata == {}


# ---------------------------------------------------------------------------
# OPENFANG_HANDS constant
# ---------------------------------------------------------------------------

def test_openfang_hands_tuple():
    """The OPENFANG_HANDS constant should list all 7 hands."""
    from infrastructure.openfang.client import OPENFANG_HANDS

    assert len(OPENFANG_HANDS) == 7
    assert "browser" in OPENFANG_HANDS
    assert "collector" in OPENFANG_HANDS
    assert "predictor" in OPENFANG_HANDS
    assert "lead" in OPENFANG_HANDS
    assert "twitter" in OPENFANG_HANDS
    assert "researcher" in OPENFANG_HANDS
    assert "clip" in OPENFANG_HANDS


# ---------------------------------------------------------------------------
# status() summary
# ---------------------------------------------------------------------------

def test_status_returns_summary():
    """status() should return a dict with url, healthy flag, and hands list."""
    from infrastructure.openfang.client import OpenFangClient

    client = OpenFangClient(base_url="http://localhost:19999")
    s = client.status()

    assert "url" in s
    assert "healthy" in s
    assert "available_hands" in s
    assert len(s["available_hands"]) == 7
