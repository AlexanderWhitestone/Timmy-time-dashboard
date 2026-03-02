"""PersonaNode — DEPRECATED, to be removed.

Replaced by distributed brain worker queue.
"""

from typing import Any


class PersonaNode:
    """Deprecated - use brain worker instead."""
    
    def __init__(self, *args, **kwargs):
        raise NotImplementedError(
            "PersonaNode is deprecated. Use brain.DistributedWorker instead."
        )
