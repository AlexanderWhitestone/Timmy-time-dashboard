"""Tests for timmy.interview — structured interview runner."""

from unittest.mock import MagicMock, patch

import pytest

from timmy.interview import (
    INTERVIEW_QUESTIONS,
    InterviewEntry,
    format_transcript,
    run_interview,
)


# ---------------------------------------------------------------------------
# INTERVIEW_QUESTIONS sanity checks
# ---------------------------------------------------------------------------


def test_interview_questions_not_empty():
    """There should be at least one interview question defined."""
    assert len(INTERVIEW_QUESTIONS) > 0


def test_interview_questions_have_required_keys():
    """Every question dict must have 'category' and 'question'."""
    for item in INTERVIEW_QUESTIONS:
        assert "category" in item
        assert "question" in item
        assert isinstance(item["category"], str)
        assert isinstance(item["question"], str)


# ---------------------------------------------------------------------------
# run_interview()
# ---------------------------------------------------------------------------


def test_run_interview_calls_chat_for_each_question():
    """run_interview should call the chat function once per question."""
    mock_chat = MagicMock(return_value="Answer.")
    transcript = run_interview(mock_chat)

    assert mock_chat.call_count == len(INTERVIEW_QUESTIONS)
    assert len(transcript) == len(INTERVIEW_QUESTIONS)


def test_run_interview_returns_interview_entries():
    """Each element in the transcript should be an InterviewEntry."""
    mock_chat = MagicMock(return_value="I am Timmy.")
    transcript = run_interview(mock_chat)

    for entry in transcript:
        assert isinstance(entry, InterviewEntry)
        assert entry.answer == "I am Timmy."


def test_run_interview_with_custom_questions():
    """run_interview should accept custom question lists."""
    custom_qs = [
        {"category": "Test", "question": "What is 2+2?"},
    ]
    mock_chat = MagicMock(return_value="Four.")
    transcript = run_interview(mock_chat, questions=custom_qs)

    assert len(transcript) == 1
    assert transcript[0].category == "Test"
    assert transcript[0].question == "What is 2+2?"
    assert transcript[0].answer == "Four."


def test_run_interview_on_answer_callback():
    """on_answer callback should be invoked for each question."""
    callback = MagicMock()
    mock_chat = MagicMock(return_value="OK.")

    run_interview(mock_chat, on_answer=callback)

    assert callback.call_count == len(INTERVIEW_QUESTIONS)
    # Each call should receive an InterviewEntry
    for call in callback.call_args_list:
        entry = call[0][0]
        assert isinstance(entry, InterviewEntry)


def test_run_interview_handles_chat_error():
    """If the chat function raises, the answer should contain the error."""
    def failing_chat(msg):
        raise ConnectionError("Ollama offline")

    transcript = run_interview(failing_chat)

    assert len(transcript) == len(INTERVIEW_QUESTIONS)
    for entry in transcript:
        assert "Error" in entry.answer
        assert "Ollama offline" in entry.answer


# ---------------------------------------------------------------------------
# format_transcript()
# ---------------------------------------------------------------------------


def test_format_transcript_empty():
    """Formatting an empty transcript should return a placeholder."""
    result = format_transcript([])
    assert "No interview data" in result


def test_format_transcript_includes_header():
    """Formatted transcript should include the header."""
    entries = [InterviewEntry(category="Identity", question="Who are you?", answer="Timmy.")]
    result = format_transcript(entries)
    assert "TIMMY INTERVIEW TRANSCRIPT" in result


def test_format_transcript_includes_questions_and_answers():
    """Formatted transcript should include Q and A."""
    entries = [
        InterviewEntry(category="Identity", question="Who are you?", answer="Timmy."),
        InterviewEntry(category="Values", question="What matters?", answer="Sovereignty."),
    ]
    result = format_transcript(entries)

    assert "Q: Who are you?" in result
    assert "A: Timmy." in result
    assert "Q: What matters?" in result
    assert "A: Sovereignty." in result


def test_format_transcript_groups_by_category():
    """Categories should appear as section headers."""
    entries = [
        InterviewEntry(category="Identity", question="Q1", answer="A1"),
        InterviewEntry(category="Values", question="Q2", answer="A2"),
    ]
    result = format_transcript(entries)

    assert "--- Identity ---" in result
    assert "--- Values ---" in result
