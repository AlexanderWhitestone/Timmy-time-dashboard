"""Identity loader — stripped.

The persona/identity system has been removed. These functions remain
as no-op stubs so that call-sites don't break at import time.
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)


def get_canonical_identity(force_refresh: bool = False) -> str:
    """Return empty string — identity system removed."""
    return ""


def get_identity_section(section_name: str) -> str:
    """Return empty string — identity system removed."""
    return ""


def get_identity_for_prompt(include_sections: Optional[list[str]] = None) -> str:
    """Return empty string — identity system removed."""
    return ""


def get_agent_roster() -> list[dict[str, str]]:
    """Return empty list — identity system removed."""
    return []


_FALLBACK_IDENTITY = ""
