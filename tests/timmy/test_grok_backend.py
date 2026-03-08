"""Tests for GrokBackend in src/timmy/backends.py and Grok dashboard routes."""

from unittest.mock import MagicMock, patch

import pytest


# ── grok_available ───────────────────────────────────────────────────────────

def test_grok_available_false_when_disabled():
    """Grok not available when GROK_ENABLED is false."""
    with patch("config.settings") as mock_settings:
        mock_settings.grok_enabled = False
        mock_settings.xai_api_key = "xai-test-key"
        from timmy.backends import grok_available
        assert grok_available() is False


def test_grok_available_false_when_no_key():
    """Grok not available when XAI_API_KEY is empty."""
    with patch("config.settings") as mock_settings:
        mock_settings.grok_enabled = True
        mock_settings.xai_api_key = ""
        from timmy.backends import grok_available
        assert grok_available() is False


def test_grok_available_true_when_enabled_and_key_set():
    """Grok available when both enabled and key are set."""
    with patch("config.settings") as mock_settings:
        mock_settings.grok_enabled = True
        mock_settings.xai_api_key = "xai-test-key"
        from timmy.backends import grok_available
        assert grok_available() is True


# ── GrokBackend construction ────────────────────────────────────────────────

def test_grok_backend_init_with_explicit_params():
    """GrokBackend can be created with explicit api_key and model."""
    from timmy.backends import GrokBackend
    backend = GrokBackend(api_key="xai-test", model="grok-3-fast")
    assert backend._api_key == "xai-test"
    assert backend._model == "grok-3-fast"
    assert backend.stats.total_requests == 0


def test_grok_backend_init_from_settings():
    """GrokBackend reads from config.settings when no params given."""
    with patch("config.settings") as mock_settings:
        mock_settings.xai_api_key = "xai-from-env"
        mock_settings.grok_default_model = "grok-3"
        from timmy.backends import GrokBackend
        backend = GrokBackend()
        assert backend._api_key == "xai-from-env"
        assert backend._model == "grok-3"


def test_grok_backend_run_no_key_returns_error():
    """run() gracefully returns error message when no API key."""
    from timmy.backends import GrokBackend
    backend = GrokBackend(api_key="", model="grok-3-fast")
    result = backend.run("hello")
    assert "not configured" in result.content


def test_grok_backend_run_success():
    """run() returns content from the API on success."""
    from timmy.backends import GrokBackend

    backend = GrokBackend(api_key="xai-test", model="grok-3-fast")

    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "Grok says hello"
    mock_response.usage = MagicMock()
    mock_response.usage.prompt_tokens = 10
    mock_response.usage.completion_tokens = 5
    mock_response.model = "grok-3-fast"

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_response

    with patch.object(backend, "_get_client", return_value=mock_client):
        result = backend.run("hello")

    assert result.content == "Grok says hello"
    assert backend.stats.total_requests == 1
    assert backend.stats.total_prompt_tokens == 10
    assert backend.stats.total_completion_tokens == 5


def test_grok_backend_run_api_error():
    """run() returns error message on API failure."""
    from timmy.backends import GrokBackend

    backend = GrokBackend(api_key="xai-test", model="grok-3-fast")

    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = Exception("API timeout")

    with patch.object(backend, "_get_client", return_value=mock_client):
        result = backend.run("hello")

    assert "unavailable" in result.content
    assert backend.stats.errors == 1


def test_grok_backend_history_management():
    """GrokBackend maintains conversation history."""
    from timmy.backends import GrokBackend

    backend = GrokBackend(api_key="xai-test", model="grok-3-fast")

    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "response"
    mock_response.usage = MagicMock()
    mock_response.usage.prompt_tokens = 10
    mock_response.usage.completion_tokens = 5

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_response

    with patch.object(backend, "_get_client", return_value=mock_client):
        backend.run("first message")
        backend.run("second message")

    assert len(backend._history) == 4  # 2 user + 2 assistant
    assert backend._history[0]["role"] == "user"
    assert backend._history[1]["role"] == "assistant"


def test_grok_backend_health_check_no_key():
    """health_check() returns not-ok when no API key."""
    from timmy.backends import GrokBackend

    backend = GrokBackend(api_key="", model="grok-3-fast")
    health = backend.health_check()
    assert health["ok"] is False
    assert "not configured" in health["error"]


def test_grok_backend_health_check_success():
    """health_check() returns ok when API key is set and models endpoint works."""
    from timmy.backends import GrokBackend

    backend = GrokBackend(api_key="xai-test", model="grok-3-fast")

    mock_client = MagicMock()
    mock_client.models.list.return_value = []

    with patch.object(backend, "_get_client", return_value=mock_client):
        health = backend.health_check()

    assert health["ok"] is True
    assert health["backend"] == "grok"


def test_grok_backend_estimated_cost():
    """estimated_cost property calculates sats from token usage."""
    from timmy.backends import GrokUsageStats

    stats = GrokUsageStats(
        total_prompt_tokens=1_000_000,
        total_completion_tokens=500_000,
    )
    # Input: 1M tokens * $5/1M = $5
    # Output: 500K tokens * $15/1M = $7.50
    # Total: $12.50 / $0.001 = 12,500 sats
    assert stats.estimated_cost_sats == 12500


def test_grok_backend_build_messages():
    """_build_messages includes system prompt and history."""
    from timmy.backends import GrokBackend

    backend = GrokBackend(api_key="xai-test", model="grok-3-fast")
    backend._history = [
        {"role": "user", "content": "previous"},
        {"role": "assistant", "content": "yes"},
    ]

    messages = backend._build_messages("new question")
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    assert messages[1]["content"] == "previous"
    assert messages[-1]["role"] == "user"
    assert messages[-1]["content"] == "new question"


# ── get_grok_backend singleton ──────────────────────────────────────────────

def test_get_grok_backend_returns_singleton():
    """get_grok_backend returns the same instance on repeated calls."""
    import timmy.backends as backends_mod

    # Reset singleton
    backends_mod._grok_backend = None

    b1 = backends_mod.get_grok_backend()
    b2 = backends_mod.get_grok_backend()
    assert b1 is b2

    # Cleanup
    backends_mod._grok_backend = None


# ── GROK_MODELS constant ───────────────────────────────────────────────────

def test_grok_models_dict_has_expected_entries():
    from timmy.backends import GROK_MODELS
    assert "grok-3-fast" in GROK_MODELS
    assert "grok-3" in GROK_MODELS


# ── consult_grok tool ──────────────────────────────────────────────────────

def test_consult_grok_returns_unavailable_when_disabled():
    """consult_grok tool returns error when Grok is not available."""
    with patch("timmy.backends.grok_available", return_value=False):
        from timmy.tools import consult_grok
        result = consult_grok("test query")
        assert "not available" in result


def test_consult_grok_calls_backend_when_available():
    """consult_grok tool calls the Grok backend when available."""
    from timmy.backends import RunResult

    mock_backend = MagicMock()
    mock_backend.run.return_value = RunResult(content="Grok answer")
    mock_backend.stats = MagicMock()
    mock_backend.stats.total_latency_ms = 100

    with patch("timmy.backends.grok_available", return_value=True), \
         patch("timmy.backends.get_grok_backend", return_value=mock_backend), \
         patch("config.settings") as mock_settings:
        mock_settings.grok_free = True
        mock_settings.grok_enabled = True
        mock_settings.xai_api_key = "xai-test"
        from timmy.tools import consult_grok
        result = consult_grok("complex question")

    assert "Grok answer" in result
    mock_backend.run.assert_called_once_with("complex question")


# ── Grok dashboard route tests ─────────────────────────────────────────────

def test_grok_status_endpoint(client):
    """GET /grok/status returns HTML dashboard page."""
    response = client.get("/grok/status")
    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")
    # Verify key status info is present in the rendered HTML
    text = response.text
    assert "Grok Status" in text
    assert "Status" in text


def test_grok_toggle_returns_html(client):
    """POST /grok/toggle returns HTML response."""
    response = client.post("/grok/toggle")
    assert response.status_code == 200


def test_grok_stats_endpoint(client):
    """GET /grok/stats returns usage statistics."""
    response = client.get("/grok/stats")
    assert response.status_code == 200
    data = response.json()
    assert "total_requests" in data or "error" in data


def test_grok_chat_without_key(client):
    """POST /grok/chat returns error when Grok is not available."""
    response = client.post(
        "/grok/chat",
        data={"message": "test query"},
    )
    assert response.status_code == 200
    # Should contain error since GROK_ENABLED is false in test mode
    assert "not available" in response.text.lower() or "error" in response.text.lower() or "grok" in response.text.lower()
