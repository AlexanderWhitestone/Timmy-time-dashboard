"""Hands — DEPRECATED. Use brain task queue instead.

This module is kept for backward compatibility during migration.
All functionality has been moved to the distributed brain task queue.
"""

from typing import Any, Optional
import logging

logger = logging.getLogger(__name__)

# Simple stub models for compatibility
class HandConfig:
    """Deprecated - use brain task queue."""
    def __init__(self, *args, **kwargs):
        self.name = kwargs.get("name", "unknown")
        self.enabled = False

class HandState:
    """Deprecated."""
    pass

class HandExecution:
    """Deprecated."""
    pass

class HandStatus:
    """Deprecated."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"

class HandOutcome:
    """Deprecated."""
    pass

class TriggerType:
    """Deprecated."""
    CRON = "cron"
    EVENT = "event"
    MANUAL = "manual"

class ApprovalGate:
    """Deprecated."""
    pass

class ApprovalRequest:
    """Deprecated."""
    pass

class ApprovalStatus:
    """Deprecated."""
    pass

class ScheduleConfig:
    """Deprecated."""
    pass

class OutputConfig:
    """Deprecated."""
    pass

class ToolRequirement:
    """Deprecated."""
    pass


class HandRegistry:
    """Deprecated - use brain task queue."""
    
    def __init__(self, hands_dir: Optional[str] = None, db_path: Optional[str] = None):
        self.hands_dir = hands_dir
        self.db_path = db_path
        logger.warning("HandRegistry is deprecated. Use brain.BrainClient instead.")
    
    def list_hands(self):
        return []
    
    def get_hand(self, name: str):
        raise NotImplementedError("Hands deprecated - use brain task queue")
    
    def get_state(self, name: str):
        return HandState()
    
    def get_scheduled_hands(self):
        return []
    
    async def load_all(self):
        pass


class HandScheduler:
    """Deprecated - use brain worker."""
    
    def __init__(self, registry: Any):
        self.registry = registry
        logger.warning("HandScheduler is deprecated. Use brain.DistributedWorker instead.")
    
    async def start(self):
        pass
    
    async def stop(self):
        pass
    
    async def schedule_hand(self, hand: Any):
        pass


class HandRunner:
    """Deprecated - use brain worker."""
    
    def __init__(self, registry: Any, llm_adapter: Any = None):
        self.registry = registry
        logger.warning("HandRunner is deprecated. Use brain.DistributedWorker instead.")
    
    async def run_hand(self, name: str, context: Any = None):
        raise NotImplementedError("Hands deprecated - use brain task queue")


class HandNotFoundError(Exception):
    pass

class HandValidationError(Exception):
    pass


__all__ = [
    "HandConfig", "HandState", "HandExecution", "HandStatus", "HandOutcome",
    "TriggerType", "ApprovalGate", "ApprovalRequest", "ApprovalStatus",
    "ScheduleConfig", "OutputConfig", "ToolRequirement",
    "HandRegistry", "HandScheduler", "HandRunner",
    "HandNotFoundError", "HandValidationError",
]
