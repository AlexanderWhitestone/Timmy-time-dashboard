from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from timmy.cli import app
from timmy.prompts import TIMMY_STATUS_PROMPT

runner = CliRunner()


def test_status_uses_status_prompt():
    """status command must pass TIMMY_STATUS_PROMPT to the agent."""
    mock_timmy = MagicMock()

    with patch("timmy.cli.create_timmy", return_value=mock_timmy):
        runner.invoke(app, ["status"])

    mock_timmy.print_response.assert_called_once_with(TIMMY_STATUS_PROMPT, stream=False)


def test_status_does_not_use_inline_string():
    """status command must not pass the old inline hardcoded string."""
    mock_timmy = MagicMock()

    with patch("timmy.cli.create_timmy", return_value=mock_timmy):
        runner.invoke(app, ["status"])

    call_args = mock_timmy.print_response.call_args
    assert call_args[0][0] != "Brief status report — one sentence."


def test_chat_sends_message_to_agent():
    """chat command must pass the user message to the agent with streaming."""
    mock_timmy = MagicMock()

    with patch("timmy.cli.create_timmy", return_value=mock_timmy):
        runner.invoke(app, ["chat", "Hello Timmy"])

    mock_timmy.print_response.assert_called_once_with("Hello Timmy", stream=True)


def test_think_sends_topic_to_agent():
    """think command must pass the topic wrapped in a prompt with streaming."""
    mock_timmy = MagicMock()

    with patch("timmy.cli.create_timmy", return_value=mock_timmy):
        runner.invoke(app, ["think", "Bitcoin self-custody"])

    mock_timmy.print_response.assert_called_once_with(
        "Think carefully about: Bitcoin self-custody", stream=True
    )


def test_chat_passes_backend_option():
    """chat --backend airllm must forward the backend to create_timmy."""
    mock_timmy = MagicMock()

    with patch("timmy.cli.create_timmy", return_value=mock_timmy) as mock_create:
        runner.invoke(app, ["chat", "test", "--backend", "airllm"])

    mock_create.assert_called_once_with(backend="airllm", model_size=None)


def test_think_passes_model_size_option():
    """think --model-size 70b must forward the model size to create_timmy."""
    mock_timmy = MagicMock()

    with patch("timmy.cli.create_timmy", return_value=mock_timmy) as mock_create:
        runner.invoke(app, ["think", "topic", "--model-size", "70b"])

    mock_create.assert_called_once_with(backend=None, model_size="70b")
