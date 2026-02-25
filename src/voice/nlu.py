"""Natural Language Understanding — intent detection for voice commands.

Uses regex patterns and keyword matching to classify user utterances
into actionable intents.  This is a lightweight, local-first NLU that
runs without any cloud API — just pattern matching.

Intents:
  - chat:       General conversation with Timmy
  - status:     Request system/agent status
  - swarm:      Swarm management commands
  - task:       Task creation/management
  - help:       Request help or list commands
  - voice:      Voice settings (volume, rate, etc.)
  - code:       Code modification / self-modify commands
  - unknown:    Unrecognized intent
"""

import re
import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class Intent:
    name: str
    confidence: float  # 0.0 to 1.0
    entities: dict
    raw_text: str


# ── Pattern definitions ─────────────────────────────────────────────────────

_PATTERNS: list[tuple[str, re.Pattern, float]] = [
    # Status queries
    ("status", re.compile(
        r"\b(status|health|how are you|are you (running|online|alive)|check)\b",
        re.IGNORECASE,
    ), 0.9),

    # Swarm commands
    ("swarm", re.compile(
        r"\b(swarm|spawn|agents?|sub-?agents?|workers?)\b",
        re.IGNORECASE,
    ), 0.85),

    # Task commands
    ("task", re.compile(
        r"\b(task|assign|create task|new task|post task|bid)\b",
        re.IGNORECASE,
    ), 0.85),

    # Help
    ("help", re.compile(
        r"\b(help|commands?|what can you do|capabilities)\b",
        re.IGNORECASE,
    ), 0.9),

    # Voice settings
    ("voice", re.compile(
        r"\b(voice|speak|volume|rate|speed|louder|quieter|faster|slower|mute|unmute)\b",
        re.IGNORECASE,
    ), 0.85),

    # Code modification / self-modify
    ("code", re.compile(
        r"\b(modify|edit|change|update|fix|refactor|implement|patch)\s+(the\s+)?(code|file|function|class|module|source)\b"
        r"|\bself[- ]?modify\b"
        r"|\b(update|change|edit)\s+(your|the)\s+(code|source)\b",
        re.IGNORECASE,
    ), 0.9),
]

# Keywords for entity extraction
_ENTITY_PATTERNS = {
    "agent_name": re.compile(r"(?:spawn|start)\s+(?:agent\s+)?(\w+)|(?:agent)\s+(\w+)", re.IGNORECASE),
    "task_description": re.compile(r"(?:task|assign)[:;]?\s+(.+)", re.IGNORECASE),
    "number": re.compile(r"\b(\d+)\b"),
    "target_file": re.compile(r"(?:in|file|modify)\s+(?:the\s+)?([/\w._-]+\.py)", re.IGNORECASE),
}


def detect_intent(text: str) -> Intent:
    """Classify a text utterance into an intent with entities.

    Returns the highest-confidence matching intent, or 'chat' as the
    default fallback (everything is a conversation with Timmy).
    """
    text = text.strip()
    if not text:
        return Intent(name="unknown", confidence=0.0, entities={}, raw_text=text)

    best_intent = "chat"
    best_confidence = 0.5  # Default chat confidence

    for intent_name, pattern, confidence in _PATTERNS:
        if pattern.search(text):
            if confidence > best_confidence:
                best_intent = intent_name
                best_confidence = confidence

    # Extract entities
    entities = {}
    for entity_name, pattern in _ENTITY_PATTERNS.items():
        match = pattern.search(text)
        if match:
            # Pick the first non-None capture group (handles alternation)
            value = next((g for g in match.groups() if g is not None), None)
            if value:
                entities[entity_name] = value

    intent = Intent(
        name=best_intent,
        confidence=best_confidence,
        entities=entities,
        raw_text=text,
    )
    logger.debug("NLU: '%s' → %s (%.2f)", text[:50], intent.name, intent.confidence)
    return intent


def extract_command(text: str) -> Optional[str]:
    """Extract a direct command from text, if present.

    Commands are prefixed with '/' or 'timmy,' — e.g.:
      /status
      timmy, spawn agent Echo
    """
    text = text.strip()

    # Slash commands
    if text.startswith("/"):
        return text[1:].strip().split()[0] if len(text) > 1 else None

    # "timmy," prefix
    match = re.match(r"timmy[,:]?\s+(.+)", text, re.IGNORECASE)
    if match:
        return match.group(1).strip()

    return None
