from unittest.mock import MagicMock, patch


def test_create_timmy_returns_agent():
    """create_timmy should delegate to Agno Agent with correct config."""
    with patch("timmy.agent.Agent") as MockAgent, \
         patch("timmy.agent.Ollama"), \
         patch("timmy.agent.SqliteDb"):

        mock_instance = MagicMock()
        MockAgent.return_value = mock_instance

        from timmy.agent import create_timmy
        result = create_timmy()

        assert result is mock_instance
        MockAgent.assert_called_once()


def test_create_timmy_agent_name():
    with patch("timmy.agent.Agent") as MockAgent, \
         patch("timmy.agent.Ollama"), \
         patch("timmy.agent.SqliteDb"):

        from timmy.agent import create_timmy
        create_timmy()

        kwargs = MockAgent.call_args.kwargs
        assert kwargs["name"] == "Agent"


def test_create_timmy_history_config():
    with patch("timmy.agent.Agent") as MockAgent, \
         patch("timmy.agent.Ollama"), \
         patch("timmy.agent.SqliteDb"):

        from timmy.agent import create_timmy
        create_timmy()

        kwargs = MockAgent.call_args.kwargs
        assert kwargs["add_history_to_context"] is True
        assert kwargs["num_history_runs"] == 20
        assert kwargs["markdown"] is True


def test_create_timmy_custom_db_file():
    with patch("timmy.agent.Agent"), \
         patch("timmy.agent.Ollama"), \
         patch("timmy.agent.SqliteDb") as MockDb:

        from timmy.agent import create_timmy
        create_timmy(db_file="custom.db")

        MockDb.assert_called_once_with(db_file="custom.db")


def test_create_timmy_embeds_system_prompt():
    from timmy.prompts import TIMMY_SYSTEM_PROMPT

    with patch("timmy.agent.Agent") as MockAgent, \
         patch("timmy.agent.Ollama"), \
         patch("timmy.agent.SqliteDb"):

        from timmy.agent import create_timmy
        create_timmy()

        kwargs = MockAgent.call_args.kwargs
        # Prompt should contain base system prompt (may have memory context appended)
        # Default model (llama3.2) uses the lite prompt
        assert "local AI assistant" in kwargs["description"]


# ── Ollama host regression (container connectivity) ─────────────────────────

def test_create_timmy_passes_ollama_url_to_model():
    """Regression: Ollama model must receive settings.ollama_url as host.

    Without this, containers default to localhost:11434 which is unreachable
    when Ollama runs on the Docker host.
    """
    with patch("timmy.agent.Agent"), \
         patch("timmy.agent.Ollama") as MockOllama, \
         patch("timmy.agent.SqliteDb"):

        from timmy.agent import create_timmy
        create_timmy()

        kwargs = MockOllama.call_args.kwargs
        assert "host" in kwargs, "Ollama() must receive host= parameter"
        assert kwargs["host"] == "http://localhost:11434"  # default from config


def test_create_timmy_respects_custom_ollama_url():
    """Ollama host should follow OLLAMA_URL when overridden in config."""
    custom_url = "http://host.docker.internal:11434"
    with patch("timmy.agent.Agent"), \
         patch("timmy.agent.Ollama") as MockOllama, \
         patch("timmy.agent.SqliteDb"), \
         patch("timmy.agent.settings") as mock_settings:

        mock_settings.ollama_model = "llama3.2"
        mock_settings.ollama_url = custom_url
        mock_settings.timmy_model_backend = "ollama"
        mock_settings.airllm_model_size = "70b"

        from timmy.agent import create_timmy
        create_timmy()

        kwargs = MockOllama.call_args.kwargs
        assert kwargs["host"] == custom_url


# ── AirLLM path ──────────────────────────────────────────────────────────────

def test_create_timmy_airllm_returns_airllm_agent():
    """backend='airllm' must return a TimmyAirLLMAgent, not an Agno Agent."""
    with patch("timmy.backends.is_apple_silicon", return_value=False):
        from timmy.agent import create_timmy
        from timmy.backends import TimmyAirLLMAgent

        result = create_timmy(backend="airllm", model_size="8b")

    assert isinstance(result, TimmyAirLLMAgent)


def test_create_timmy_airllm_does_not_call_agno_agent():
    """When using the airllm backend, Agno Agent should never be instantiated."""
    with patch("timmy.agent.Agent") as MockAgent, \
         patch("timmy.backends.is_apple_silicon", return_value=False):

        from timmy.agent import create_timmy
        create_timmy(backend="airllm", model_size="8b")

    MockAgent.assert_not_called()


def test_create_timmy_explicit_ollama_ignores_autodetect():
    """backend='ollama' must always use Ollama, even on Apple Silicon."""
    with patch("timmy.agent.Agent") as MockAgent, \
         patch("timmy.agent.Ollama"), \
         patch("timmy.agent.SqliteDb"):

        from timmy.agent import create_timmy
        create_timmy(backend="ollama")

    MockAgent.assert_called_once()


# ── _resolve_backend ─────────────────────────────────────────────────────────

def test_resolve_backend_explicit_takes_priority():
    from timmy.agent import _resolve_backend
    assert _resolve_backend("airllm") == "airllm"
    assert _resolve_backend("ollama") == "ollama"


def test_resolve_backend_defaults_to_ollama_without_config():
    """Default config (timmy_model_backend='ollama') → 'ollama'."""
    from timmy.agent import _resolve_backend
    assert _resolve_backend(None) == "ollama"


def test_resolve_backend_auto_uses_airllm_on_apple_silicon():
    """'auto' on Apple Silicon with airllm stubbed → 'airllm'."""
    with patch("timmy.backends.is_apple_silicon", return_value=True), \
         patch("timmy.agent.settings") as mock_settings:
        mock_settings.timmy_model_backend = "auto"
        mock_settings.airllm_model_size = "70b"
        mock_settings.ollama_model = "llama3.2"

        from timmy.agent import _resolve_backend
        assert _resolve_backend(None) == "airllm"


def test_resolve_backend_auto_falls_back_on_non_apple():
    """'auto' on non-Apple Silicon → 'ollama'."""
    with patch("timmy.backends.is_apple_silicon", return_value=False), \
         patch("timmy.agent.settings") as mock_settings:
        mock_settings.timmy_model_backend = "auto"
        mock_settings.airllm_model_size = "70b"
        mock_settings.ollama_model = "llama3.2"

        from timmy.agent import _resolve_backend
        assert _resolve_backend(None) == "ollama"


# ── _model_supports_tools ────────────────────────────────────────────────────

def test_model_supports_tools_llama32_returns_false():
    """llama3.2 (3B) is too small for reliable tool calling."""
    from timmy.agent import _model_supports_tools
    assert _model_supports_tools("llama3.2") is False
    assert _model_supports_tools("llama3.2:latest") is False


def test_model_supports_tools_llama31_returns_true():
    """llama3.1 (8B+) can handle tool calling."""
    from timmy.agent import _model_supports_tools
    assert _model_supports_tools("llama3.1") is True
    assert _model_supports_tools("llama3.3") is True


def test_model_supports_tools_other_small_models():
    """Other known small models should not get tools."""
    from timmy.agent import _model_supports_tools
    assert _model_supports_tools("phi-3") is False
    assert _model_supports_tools("tinyllama") is False


def test_model_supports_tools_unknown_model_gets_tools():
    """Unknown models default to tool-capable (optimistic)."""
    from timmy.agent import _model_supports_tools
    assert _model_supports_tools("mistral") is True
    assert _model_supports_tools("qwen2.5:72b") is True


# ── Tool gating in create_timmy ──────────────────────────────────────────────

def test_create_timmy_no_tools_for_small_model():
    """llama3.2 should get no tools."""
    with patch("timmy.agent.Agent") as MockAgent, \
         patch("timmy.agent.Ollama"), \
         patch("timmy.agent.SqliteDb"):

        from timmy.agent import create_timmy
        create_timmy()

        kwargs = MockAgent.call_args.kwargs
        # Default model is llama3.2 → tools should be None
        assert kwargs["tools"] is None


def test_create_timmy_includes_tools_for_large_model():
    """A tool-capable model (e.g. llama3.1) should attempt to include tools."""
    mock_toolkit = MagicMock()

    with patch("timmy.agent.Agent") as MockAgent, \
         patch("timmy.agent.Ollama"), \
         patch("timmy.agent.SqliteDb"), \
         patch("timmy.agent.create_full_toolkit", return_value=mock_toolkit), \
         patch("timmy.agent.settings") as mock_settings:

        mock_settings.ollama_model = "llama3.1"
        mock_settings.ollama_url = "http://localhost:11434"
        mock_settings.timmy_model_backend = "ollama"
        mock_settings.airllm_model_size = "70b"
        mock_settings.telemetry_enabled = False

        from timmy.agent import create_timmy
        create_timmy()

        kwargs = MockAgent.call_args.kwargs
        assert kwargs["tools"] == [mock_toolkit]


def test_create_timmy_no_show_tool_calls():
    """show_tool_calls must NOT be passed — Agno 2.5.3 doesn't support it."""
    with patch("timmy.agent.Agent") as MockAgent, \
         patch("timmy.agent.Ollama"), \
         patch("timmy.agent.SqliteDb"):

        from timmy.agent import create_timmy
        create_timmy()

        kwargs = MockAgent.call_args.kwargs
        assert "show_tool_calls" not in kwargs
