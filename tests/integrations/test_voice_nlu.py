"""Tests for voice/nlu.py — intent detection and command extraction."""

from voice.nlu import detect_intent, extract_command


# ── Intent detection ─────────────────────────────────────────────────────────

def test_status_intent():
    intent = detect_intent("What is your status?")
    assert intent.name == "status"
    assert intent.confidence >= 0.8


def test_status_intent_health():
    intent = detect_intent("health check")
    assert intent.name == "status"


def test_swarm_intent():
    intent = detect_intent("Show me the swarm agents")
    assert intent.name == "swarm"


def test_task_intent():
    intent = detect_intent("Create a new task for research")
    assert intent.name == "task"


def test_help_intent():
    intent = detect_intent("What commands do you support?")
    assert intent.name == "help"


def test_voice_intent():
    intent = detect_intent("Set the volume louder")
    assert intent.name == "voice"


def test_chat_fallback():
    intent = detect_intent("Tell me about Bitcoin sovereignty")
    assert intent.name == "chat"
    assert intent.confidence == 0.5


def test_empty_input():
    intent = detect_intent("")
    assert intent.name == "unknown"
    assert intent.confidence == 0.0


def test_intent_has_raw_text():
    intent = detect_intent("hello world")
    assert intent.raw_text == "hello world"


# ── Entity extraction ────────────────────────────────────────────────────────

def test_entity_agent_name():
    intent = detect_intent("spawn agent Echo")
    assert "agent_name" in intent.entities
    assert intent.entities["agent_name"] == "Echo"


def test_entity_number():
    intent = detect_intent("set volume to 80")
    assert "number" in intent.entities
    assert intent.entities["number"] == "80"


# ── Command extraction ──────────────────────────────────────────────────────

def test_slash_command():
    cmd = extract_command("/status")
    assert cmd == "status"


def test_timmy_prefix_command():
    cmd = extract_command("timmy, spawn agent Echo")
    assert cmd is not None
    assert "spawn" in cmd


def test_no_command():
    cmd = extract_command("just a regular sentence")
    assert cmd is None


def test_empty_slash():
    cmd = extract_command("/")
    assert cmd is None
