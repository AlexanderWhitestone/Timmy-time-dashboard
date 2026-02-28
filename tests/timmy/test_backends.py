"""Tests for src/timmy/backends.py — AirLLM wrapper and helpers."""

import sys
from unittest.mock import MagicMock, patch

import pytest


# ── is_apple_silicon ──────────────────────────────────────────────────────────

def test_is_apple_silicon_true_on_arm_darwin():
    with patch("timmy.backends.platform.system", return_value="Darwin"), \
         patch("timmy.backends.platform.machine", return_value="arm64"):
        from timmy.backends import is_apple_silicon
        assert is_apple_silicon() is True


def test_is_apple_silicon_false_on_linux():
    with patch("timmy.backends.platform.system", return_value="Linux"), \
         patch("timmy.backends.platform.machine", return_value="x86_64"):
        from timmy.backends import is_apple_silicon
        assert is_apple_silicon() is False


def test_is_apple_silicon_false_on_intel_mac():
    with patch("timmy.backends.platform.system", return_value="Darwin"), \
         patch("timmy.backends.platform.machine", return_value="x86_64"):
        from timmy.backends import is_apple_silicon
        assert is_apple_silicon() is False


# ── airllm_available ─────────────────────────────────────────────────────────

def test_airllm_available_true_when_stub_in_sys_modules():
    # conftest already stubs 'airllm' — importable → True.
    from timmy.backends import airllm_available
    assert airllm_available() is True


def test_airllm_available_false_when_not_importable():
    # Temporarily remove the stub to simulate airllm not installed.
    saved = sys.modules.pop("airllm", None)
    try:
        from timmy.backends import airllm_available
        assert airllm_available() is False
    finally:
        if saved is not None:
            sys.modules["airllm"] = saved


# ── TimmyAirLLMAgent construction ────────────────────────────────────────────

def test_airllm_agent_raises_on_unknown_size():
    from timmy.backends import TimmyAirLLMAgent
    with pytest.raises(ValueError, match="Unknown model size"):
        TimmyAirLLMAgent(model_size="3b")


def test_airllm_agent_uses_automodel_on_non_apple():
    """Non-Apple-Silicon path uses AutoModel.from_pretrained."""
    with patch("timmy.backends.is_apple_silicon", return_value=False):
        from timmy.backends import TimmyAirLLMAgent
        agent = TimmyAirLLMAgent(model_size="8b")
    # sys.modules["airllm"] is a MagicMock; AutoModel.from_pretrained was called.
    assert sys.modules["airllm"].AutoModel.from_pretrained.called


def test_airllm_agent_uses_mlx_on_apple_silicon():
    """Apple Silicon path uses AirLLMMLX, not AutoModel."""
    with patch("timmy.backends.is_apple_silicon", return_value=True):
        from timmy.backends import TimmyAirLLMAgent
        agent = TimmyAirLLMAgent(model_size="8b")
    assert sys.modules["airllm"].AirLLMMLX.called


def test_airllm_agent_resolves_correct_model_id_for_70b():
    with patch("timmy.backends.is_apple_silicon", return_value=False):
        from timmy.backends import TimmyAirLLMAgent, _AIRLLM_MODELS
        TimmyAirLLMAgent(model_size="70b")
    sys.modules["airllm"].AutoModel.from_pretrained.assert_called_with(
        _AIRLLM_MODELS["70b"]
    )


# ── TimmyAirLLMAgent.print_response ──────────────────────────────────────────

def _make_agent(model_size: str = "8b") -> "TimmyAirLLMAgent":
    """Helper: create an agent with a fully mocked underlying model."""
    with patch("timmy.backends.is_apple_silicon", return_value=False):
        from timmy.backends import TimmyAirLLMAgent
        agent = TimmyAirLLMAgent(model_size=model_size)

    # Replace the underlying model with a clean mock that returns predictable output.
    mock_model = MagicMock()
    mock_tokenizer = MagicMock()
    # tokenizer() returns a dict-like object with an "input_ids" tensor mock.
    input_ids_mock = MagicMock()
    input_ids_mock.shape = [1, 10]  # shape[1] = prompt token count = 10
    token_dict = {"input_ids": input_ids_mock}
    mock_tokenizer.return_value = token_dict
    # generate() returns a list of token sequences.
    mock_tokenizer.decode.return_value = "Sir, affirmative."
    mock_model.tokenizer = mock_tokenizer
    mock_model.generate.return_value = [list(range(15))]  # 15 tokens total
    agent._model = mock_model
    return agent


def test_print_response_calls_generate():
    agent = _make_agent()
    agent.print_response("What is sovereignty?", stream=True)
    agent._model.generate.assert_called_once()


def test_print_response_decodes_only_generated_tokens():
    agent = _make_agent()
    agent.print_response("Hello", stream=False)
    # decode should be called with tokens starting at index 10 (prompt length).
    decode_call = agent._model.tokenizer.decode.call_args
    token_slice = decode_call[0][0]
    assert list(token_slice) == list(range(10, 15))


def test_print_response_updates_history():
    agent = _make_agent()
    agent.print_response("First message")
    assert any("First message" in turn for turn in agent._history)
    assert any("Timmy:" in turn for turn in agent._history)


def test_print_response_history_included_in_second_prompt():
    agent = _make_agent()
    agent.print_response("First")
    # Build the prompt for the second call — history should appear.
    prompt = agent._build_prompt("Second")
    assert "First" in prompt
    assert "Second" in prompt


def test_print_response_stream_flag_accepted():
    """stream=False should not raise — it's accepted for API compatibility."""
    agent = _make_agent()
    agent.print_response("hello", stream=False)  # no error


# ── ClaudeBackend ─────────────────────────────────────────────────────────


def test_claude_available_false_when_no_key():
    """claude_available() returns False when ANTHROPIC_API_KEY is empty."""
    with patch("config.settings") as mock_settings:
        mock_settings.anthropic_api_key = ""
        from timmy.backends import claude_available
        assert claude_available() is False


def test_claude_available_true_when_key_set():
    """claude_available() returns True when ANTHROPIC_API_KEY is set."""
    with patch("config.settings") as mock_settings:
        mock_settings.anthropic_api_key = "sk-ant-test-key"
        from timmy.backends import claude_available
        assert claude_available() is True


def test_claude_backend_init_with_explicit_params():
    """ClaudeBackend can be created with explicit api_key and model."""
    from timmy.backends import ClaudeBackend
    backend = ClaudeBackend(api_key="sk-ant-test", model="haiku")
    assert backend._api_key == "sk-ant-test"
    assert "haiku" in backend._model


def test_claude_backend_init_resolves_short_names():
    """ClaudeBackend resolves short model names to full IDs."""
    from timmy.backends import ClaudeBackend, CLAUDE_MODELS
    backend = ClaudeBackend(api_key="sk-test", model="sonnet")
    assert backend._model == CLAUDE_MODELS["sonnet"]


def test_claude_backend_init_passes_through_full_model_id():
    """ClaudeBackend passes through full model IDs unchanged."""
    from timmy.backends import ClaudeBackend
    backend = ClaudeBackend(api_key="sk-test", model="claude-haiku-4-5-20251001")
    assert backend._model == "claude-haiku-4-5-20251001"


def test_claude_backend_run_no_key_returns_error():
    """run() gracefully returns error message when no API key."""
    from timmy.backends import ClaudeBackend
    backend = ClaudeBackend(api_key="", model="haiku")
    result = backend.run("hello")
    assert "not configured" in result.content


def test_claude_backend_run_success():
    """run() returns content from the Anthropic API on success."""
    from timmy.backends import ClaudeBackend

    backend = ClaudeBackend(api_key="sk-ant-test", model="haiku")

    mock_content = MagicMock()
    mock_content.text = "Sir, affirmative. I am Timmy."

    mock_response = MagicMock()
    mock_response.content = [mock_content]

    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_response

    with patch.object(backend, "_get_client", return_value=mock_client):
        result = backend.run("Who are you?")

    assert "Timmy" in result.content
    assert len(backend._history) == 2  # user + assistant


def test_claude_backend_run_handles_api_error():
    """run() returns a graceful error when the API raises."""
    from timmy.backends import ClaudeBackend

    backend = ClaudeBackend(api_key="sk-ant-test", model="haiku")

    mock_client = MagicMock()
    mock_client.messages.create.side_effect = ConnectionError("network down")

    with patch.object(backend, "_get_client", return_value=mock_client):
        result = backend.run("hello")

    assert "unavailable" in result.content


def test_claude_backend_history_rolling_window():
    """History should be capped at 20 entries (10 exchanges)."""
    from timmy.backends import ClaudeBackend

    backend = ClaudeBackend(api_key="sk-ant-test", model="haiku")

    mock_content = MagicMock()
    mock_content.text = "OK."
    mock_response = MagicMock()
    mock_response.content = [mock_content]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_response

    with patch.object(backend, "_get_client", return_value=mock_client):
        for i in range(15):
            backend.run(f"message {i}")

    assert len(backend._history) <= 20
