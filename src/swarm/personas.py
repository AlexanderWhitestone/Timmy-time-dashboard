"""Personas — DEPRECATED, to be removed.

This module is kept for backward compatibility during migration.
All persona functionality has been replaced by the distributed brain task queue.
"""

from typing import TypedDict, List


class PersonaMeta(TypedDict, total=False):
    id: str
    name: str
    role: str
    description: str
    capabilities: str
    rate_sats: int


# Empty personas list - functionality moved to brain task queue
PERSONAS: dict[str, PersonaMeta] = {}


def list_personas() -> List[PersonaMeta]:
    """Return empty list - personas deprecated."""
    return []
