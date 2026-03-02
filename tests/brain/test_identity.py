"""Tests for brain.identity — Canonical identity loader.

TDD: These tests define the contract for identity loading.
Any substrate that needs to know who Timmy is calls these functions.
"""

from __future__ import annotations

import pytest

from brain.identity import (
    get_canonical_identity,
    get_identity_section,
    get_identity_for_prompt,
    get_agent_roster,
    _IDENTITY_PATH,
    _FALLBACK_IDENTITY,
)


# ── File Existence ────────────────────────────────────────────────────────────


class TestIdentityFile:
    """Validate the canonical identity file exists and is well-formed."""

    def test_identity_file_exists(self):
        """TIMMY_IDENTITY.md must exist at project root."""
        assert _IDENTITY_PATH.exists(), (
            f"TIMMY_IDENTITY.md not found at {_IDENTITY_PATH}"
        )

    def test_identity_file_is_markdown(self):
        """File should be valid markdown (starts with # heading)."""
        content = _IDENTITY_PATH.read_text(encoding="utf-8")
        assert content.startswith("# "), "Identity file should start with a # heading"

    def test_identity_file_not_empty(self):
        """File should have substantial content."""
        content = _IDENTITY_PATH.read_text(encoding="utf-8")
        assert len(content) > 500, "Identity file is too short"


# ── Loading ───────────────────────────────────────────────────────────────────


class TestGetCanonicalIdentity:
    """Test the identity loader."""

    def test_returns_string(self):
        """Should return a string."""
        identity = get_canonical_identity()
        assert isinstance(identity, str)

    def test_contains_timmy(self):
        """Should contain 'Timmy'."""
        identity = get_canonical_identity()
        assert "Timmy" in identity

    def test_contains_sovereignty(self):
        """Should mention sovereignty — core value."""
        identity = get_canonical_identity()
        assert "Sovereign" in identity or "sovereignty" in identity.lower()

    def test_force_refresh(self):
        """force_refresh should re-read from disk."""
        id1 = get_canonical_identity()
        id2 = get_canonical_identity(force_refresh=True)
        assert id1 == id2  # Same file, same content

    def test_caching(self):
        """Second call should use cache (same object)."""
        import brain.identity as mod

        mod._identity_cache = None
        id1 = get_canonical_identity()
        id2 = get_canonical_identity()
        # Cache should be populated
        assert mod._identity_cache is not None


# ── Section Extraction ────────────────────────────────────────────────────────


class TestGetIdentitySection:
    """Test section extraction from the identity document."""

    def test_core_identity_section(self):
        """Should extract Core Identity section."""
        section = get_identity_section("Core Identity")
        assert len(section) > 0
        assert "Timmy" in section

    def test_voice_section(self):
        """Should extract Voice & Character section."""
        section = get_identity_section("Voice & Character")
        assert len(section) > 0
        assert "Direct" in section or "Honest" in section

    def test_standing_rules_section(self):
        """Should extract Standing Rules section."""
        section = get_identity_section("Standing Rules")
        assert "Sovereignty First" in section

    def test_nonexistent_section(self):
        """Should return empty string for missing section."""
        section = get_identity_section("This Section Does Not Exist")
        assert section == ""

    def test_memory_architecture_section(self):
        """Should extract Memory Architecture section."""
        section = get_identity_section("Memory Architecture")
        assert len(section) > 0
        assert "remember" in section.lower() or "recall" in section.lower()


# ── Prompt Formatting ─────────────────────────────────────────────────────────


class TestGetIdentityForPrompt:
    """Test prompt-ready identity formatting."""

    def test_returns_string(self):
        """Should return a string."""
        prompt = get_identity_for_prompt()
        assert isinstance(prompt, str)

    def test_includes_core_sections(self):
        """Should include core identity sections."""
        prompt = get_identity_for_prompt()
        assert "Core Identity" in prompt
        assert "Standing Rules" in prompt

    def test_excludes_philosophical_grounding(self):
        """Should not include the full philosophical section."""
        prompt = get_identity_for_prompt()
        # The philosophical grounding is verbose — prompt version should be compact
        assert "Ascension" not in prompt

    def test_custom_sections(self):
        """Should support custom section selection."""
        prompt = get_identity_for_prompt(include_sections=["Core Identity"])
        assert "Core Identity" in prompt
        assert "Standing Rules" not in prompt

    def test_compact_enough_for_prompt(self):
        """Prompt version should be shorter than full document."""
        full = get_canonical_identity()
        prompt = get_identity_for_prompt()
        assert len(prompt) < len(full)


# ── Agent Roster ──────────────────────────────────────────────────────────────


class TestGetAgentRoster:
    """Test agent roster parsing."""

    def test_returns_list(self):
        """Should return a list."""
        roster = get_agent_roster()
        assert isinstance(roster, list)

    def test_has_ten_agents(self):
        """Should have exactly 10 agents."""
        roster = get_agent_roster()
        assert len(roster) == 10

    def test_timmy_is_first(self):
        """Timmy should be in the roster."""
        roster = get_agent_roster()
        names = [a["agent"] for a in roster]
        assert "Timmy" in names

    def test_all_expected_agents(self):
        """All canonical agents should be present."""
        roster = get_agent_roster()
        names = {a["agent"] for a in roster}
        expected = {"Timmy", "Echo", "Mace", "Forge", "Seer", "Helm", "Quill", "Pixel", "Lyra", "Reel"}
        assert expected == names

    def test_agent_has_role(self):
        """Each agent should have a role."""
        roster = get_agent_roster()
        for agent in roster:
            assert agent["role"], f"{agent['agent']} has no role"

    def test_agent_has_capabilities(self):
        """Each agent should have capabilities."""
        roster = get_agent_roster()
        for agent in roster:
            assert agent["capabilities"], f"{agent['agent']} has no capabilities"


# ── Fallback ──────────────────────────────────────────────────────────────────


class TestFallback:
    """Test the fallback identity."""

    def test_fallback_is_valid(self):
        """Fallback should be a valid identity document."""
        assert "Timmy" in _FALLBACK_IDENTITY
        assert "Sovereign" in _FALLBACK_IDENTITY
        assert "Standing Rules" in _FALLBACK_IDENTITY

    def test_fallback_has_minimal_roster(self):
        """Fallback should have at least Timmy in the roster."""
        assert "Timmy" in _FALLBACK_IDENTITY
        assert "Orchestrator" in _FALLBACK_IDENTITY
