"""Tests for shortcuts/siri.py — Siri Shortcuts integration."""

from shortcuts.siri import get_setup_guide, SHORTCUT_ACTIONS


def test_setup_guide_has_title():
    guide = get_setup_guide()
    assert "title" in guide
    assert "Timmy" in guide["title"]


def test_setup_guide_has_instructions():
    guide = get_setup_guide()
    assert "instructions" in guide
    assert len(guide["instructions"]) > 0


def test_setup_guide_has_actions():
    guide = get_setup_guide()
    assert "actions" in guide
    assert len(guide["actions"]) > 0


def test_setup_guide_actions_have_required_fields():
    guide = get_setup_guide()
    for action in guide["actions"]:
        assert "name" in action
        assert "endpoint" in action
        assert "method" in action
        assert "description" in action


def test_shortcut_actions_catalog():
    assert len(SHORTCUT_ACTIONS) >= 4
    names = [a.name for a in SHORTCUT_ACTIONS]
    assert "Chat with Timmy" in names
    assert "Check Status" in names


def test_chat_shortcut_is_post():
    chat = next(a for a in SHORTCUT_ACTIONS if a.name == "Chat with Timmy")
    assert chat.method == "POST"
    assert "/shortcuts/chat" in chat.endpoint
