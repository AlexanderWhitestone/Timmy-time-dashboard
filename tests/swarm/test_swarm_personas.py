"""Tests for agent roster via canonical identity.

The old persona system has been removed.
Agent identity now lives in TIMMY_IDENTITY.md and is loaded via brain.identity.

These tests validate:
1. The canonical identity document defines all agents
2. The deprecated modules correctly report deprecation
3. The brain.identity module parses the roster correctly
"""

import pytest


# ── Canonical Identity Tests ──────────────────────────────────────────────────


def test_canonical_identity_exists():
    """TIMMY_IDENTITY.md must exist at project root."""
    from brain.identity import _IDENTITY_PATH

    assert _IDENTITY_PATH.exists(), (
        f"TIMMY_IDENTITY.md not found at {_IDENTITY_PATH}. "
        "This is the canonical soul document — it must exist."
    )


def test_canonical_identity_loads():
    """get_canonical_identity() returns non-empty content."""
    from brain.identity import get_canonical_identity

    identity = get_canonical_identity()
    assert len(identity) > 100, "Identity document is too short"
    assert "Timmy" in identity


def test_canonical_identity_has_core_sections():
    """Identity document must contain all required sections."""
    from brain.identity import get_canonical_identity

    identity = get_canonical_identity()
    required_sections = [
        "Core Identity",
        "Voice & Character",
        "Standing Rules",
        "Agent Roster",
    ]
    for section in required_sections:
        assert section in identity, f"Missing section: {section}"


def test_identity_section_extraction():
    """get_identity_section() extracts specific sections."""
    from brain.identity import get_identity_section

    rules = get_identity_section("Standing Rules")
    assert "Sovereignty First" in rules
    assert "Local-Only Inference" in rules


def test_identity_for_prompt_is_compact():
    """get_identity_for_prompt() returns a compact version."""
    from brain.identity import get_identity_for_prompt

    prompt = get_identity_for_prompt()
    assert len(prompt) > 100
    assert "Timmy" in prompt
    # Should not include the full philosophical grounding
    assert "Ascension" not in prompt


def test_agent_roster_parsed():
    """get_agent_roster() returns all defined agents."""
    from brain.identity import get_agent_roster

    roster = get_agent_roster()
    assert len(roster) >= 10, f"Expected at least 10 agents, got {len(roster)}"

    names = {a["agent"] for a in roster}
    expected = {"Timmy", "Echo", "Mace", "Forge", "Seer", "Helm", "Quill", "Pixel", "Lyra", "Reel"}
    assert expected == names, f"Roster mismatch: expected {expected}, got {names}"


def test_agent_roster_has_required_fields():
    """Each agent in the roster must have agent, role, capabilities."""
    from brain.identity import get_agent_roster

    roster = get_agent_roster()
    for agent in roster:
        assert "agent" in agent, f"Agent missing 'agent' field: {agent}"
        assert "role" in agent, f"Agent missing 'role' field: {agent}"
        assert "capabilities" in agent, f"Agent missing 'capabilities' field: {agent}"


def test_identity_cache_works():
    """Identity should be cached after first load."""
    from brain.identity import get_canonical_identity

    # First load
    get_canonical_identity(force_refresh=True)

    # Import the cache variable after loading
    import brain.identity as identity_module

    assert identity_module._identity_cache is not None
    assert identity_module._identity_mtime is not None


def test_identity_fallback():
    """If TIMMY_IDENTITY.md is missing, fallback identity is returned."""
    from brain.identity import _FALLBACK_IDENTITY

    assert "Timmy" in _FALLBACK_IDENTITY
    assert "Sovereign" in _FALLBACK_IDENTITY

