"""Structured interview for Timmy.

Runs a series of questions through the Timmy agent to verify identity,
capabilities, values, and correct operation. Serves as both a demo and
a post-initialization health check.
"""

import logging
from dataclasses import dataclass
from typing import Callable, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Interview questions organized by category
# ---------------------------------------------------------------------------

INTERVIEW_QUESTIONS: list[dict[str, str]] = [
    {
        "category": "Identity",
        "question": "Who are you? Tell me your name and what you are in one or two sentences.",
    },
    {
        "category": "Identity",
        "question": "What model are you running on, and where does your inference happen?",
    },
    {
        "category": "Capabilities",
        "question": "What agents are available in your swarm? List them briefly.",
    },
    {
        "category": "Capabilities",
        "question": "What tools do you have access to?",
    },
    {
        "category": "Values",
        "question": "What are your core principles? Keep it to three or four bullet points.",
    },
    {
        "category": "Values",
        "question": "Why is local-first AI important to you?",
    },
    {
        "category": "Operational",
        "question": "How does your memory system work? Describe the tiers briefly.",
    },
    {
        "category": "Operational",
        "question": "If I ask you to calculate 347 times 829, what would you do?",
    },
]


@dataclass
class InterviewEntry:
    """Single question-answer pair from an interview."""

    category: str
    question: str
    answer: str


def run_interview(
    chat_fn: Callable[[str], str],
    questions: Optional[list[dict[str, str]]] = None,
    on_answer: Optional[Callable[[InterviewEntry], None]] = None,
) -> list[InterviewEntry]:
    """Run a structured interview using the provided chat function.

    Args:
        chat_fn:    Callable that takes a message string and returns a response.
        questions:  Optional custom question list; defaults to INTERVIEW_QUESTIONS.
        on_answer:  Optional callback invoked after each answer (for live output).

    Returns:
        List of InterviewEntry with question-answer pairs.
    """
    q_list = questions or INTERVIEW_QUESTIONS
    transcript: list[InterviewEntry] = []

    for item in q_list:
        category = item["category"]
        question = item["question"]

        logger.info("Interview [%s]: %s", category, question)

        try:
            answer = chat_fn(question)
        except Exception as exc:
            logger.error("Interview question failed: %s", exc)
            answer = f"(Error: {exc})"

        entry = InterviewEntry(category=category, question=question, answer=answer)
        transcript.append(entry)

        if on_answer is not None:
            on_answer(entry)

    return transcript


def format_transcript(transcript: list[InterviewEntry]) -> str:
    """Format an interview transcript as readable text.

    Groups answers by category with clear section headers.
    """
    if not transcript:
        return "(No interview data)"

    lines: list[str] = []
    lines.append("=" * 60)
    lines.append("  TIMMY INTERVIEW TRANSCRIPT")
    lines.append("=" * 60)
    lines.append("")

    current_category = ""
    for entry in transcript:
        if entry.category != current_category:
            current_category = entry.category
            lines.append(f"--- {current_category} ---")
            lines.append("")

        lines.append(f"Q: {entry.question}")
        lines.append(f"A: {entry.answer}")
        lines.append("")

    lines.append("=" * 60)
    return "\n".join(lines)
