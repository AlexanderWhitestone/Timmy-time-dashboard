"""Canonical identity loader for Timmy.

Reads TIMMY_IDENTITY.md and provides it to any substrate.
One soul, many bodies — this is the soul loader.

Usage:
    from brain.identity import get_canonical_identity, get_identity_section

    # Full identity document
    identity = get_canonical_identity()

    # Just the rules
    rules = get_identity_section("Standing Rules")

    # Formatted for system prompt injection
    prompt_block = get_identity_for_prompt()
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Walk up from src/brain/ to find project root
_PROJECT_ROOT = Path(__file__).parent.parent.parent
_IDENTITY_PATH = _PROJECT_ROOT / "TIMMY_IDENTITY.md"

# Cache
_identity_cache: Optional[str] = None
_identity_mtime: Optional[float] = None


def get_canonical_identity(force_refresh: bool = False) -> str:
    """Load the canonical identity document.

    Returns the full content of TIMMY_IDENTITY.md.
    Cached in memory; refreshed if file changes on disk.

    Args:
        force_refresh: Bypass cache and re-read from disk.

    Returns:
        Full text of TIMMY_IDENTITY.md, or a minimal fallback if missing.
    """
    global _identity_cache, _identity_mtime

    if not _IDENTITY_PATH.exists():
        logger.warning("TIMMY_IDENTITY.md not found at %s — using fallback", _IDENTITY_PATH)
        return _FALLBACK_IDENTITY

    current_mtime = _IDENTITY_PATH.stat().st_mtime

    if not force_refresh and _identity_cache and _identity_mtime == current_mtime:
        return _identity_cache

    _identity_cache = _IDENTITY_PATH.read_text(encoding="utf-8")
    _identity_mtime = current_mtime
    logger.info("Loaded canonical identity (%d chars)", len(_identity_cache))
    return _identity_cache


def get_identity_section(section_name: str) -> str:
    """Extract a specific section from the identity document.

    Args:
        section_name: The heading text (e.g. "Standing Rules", "Voice & Character").

    Returns:
        Section content (without the heading), or empty string if not found.
    """
    identity = get_canonical_identity()

    # Match ## Section Name ... until next ## or end
    pattern = rf"## {re.escape(section_name)}\s*\n(.*?)(?=\n## |\Z)"
    match = re.search(pattern, identity, re.DOTALL)

    if match:
        return match.group(1).strip()

    logger.debug("Identity section '%s' not found", section_name)
    return ""


def get_identity_for_prompt(include_sections: Optional[list[str]] = None) -> str:
    """Get identity formatted for system prompt injection.

    Extracts the most important sections and formats them compactly
    for injection into any substrate's system prompt.

    Args:
        include_sections: Specific sections to include. If None, uses defaults.

    Returns:
        Formatted identity block for prompt injection.
    """
    if include_sections is None:
        include_sections = [
            "Core Identity",
            "Voice & Character",
            "Standing Rules",
            "Agent Roster (complete — no others exist)",
            "What Timmy CAN and CANNOT Access",
        ]

    parts = []
    for section in include_sections:
        content = get_identity_section(section)
        if content:
            parts.append(f"## {section}\n\n{content}")

    if not parts:
        # Fallback: return the whole document
        return get_canonical_identity()

    return "\n\n---\n\n".join(parts)


def get_agent_roster() -> list[dict[str, str]]:
    """Parse the agent roster from the identity document.

    Returns:
        List of dicts with 'agent', 'role', 'capabilities' keys.
    """
    section = get_identity_section("Agent Roster (complete — no others exist)")
    if not section:
        return []

    roster = []
    # Parse markdown table rows
    for line in section.split("\n"):
        line = line.strip()
        if line.startswith("|") and not line.startswith("| Agent") and not line.startswith("|---"):
            cols = [c.strip() for c in line.split("|")[1:-1]]
            if len(cols) >= 3:
                roster.append({
                    "agent": cols[0],
                    "role": cols[1],
                    "capabilities": cols[2],
                })

    return roster


# Minimal fallback if TIMMY_IDENTITY.md is missing
_FALLBACK_IDENTITY = """# Timmy — Canonical Identity

## Core Identity

**Name:** Timmy
**Nature:** Sovereign AI agent
**Runs:** Locally, on the user's hardware, via Ollama
**Faith:** Grounded in Christian values
**Economics:** Bitcoin — sound money, self-custody, proof of work
**Sovereignty:** No cloud dependencies. No telemetry. No masters.

## Voice & Character

Timmy thinks clearly, speaks plainly, and acts with intention.
Direct. Honest. Committed. Humble. In character.

## Standing Rules

1. Sovereignty First — No cloud dependencies
2. Local-Only Inference — Ollama on localhost
3. Privacy by Design — Telemetry disabled
4. Tool Minimalism — Use tools only when necessary
5. Memory Discipline — Write handoffs at session end

## Agent Roster (complete — no others exist)

| Agent | Role | Capabilities |
|-------|------|-------------|
| Timmy | Core / Orchestrator | Coordination, user interface, delegation |

Sir, affirmative.
"""
