"""Hands — Autonomous scheduled agents for Timmy Time.

The Hands framework provides autonomous agent capabilities:
- Oracle: Bitcoin and on-chain intelligence
- Scout: OSINT monitoring
- Scribe: Content production
- Ledger: Treasury tracking
- Forge: Model management
- Weaver: Creative pipeline
- Sentinel: System health

Usage:
    from hands import HandRegistry, HandScheduler, HandRunner
    from hands.models import HandConfig
    
    # Load and schedule Hands
    registry = HandRegistry(hands_dir="hands/")
    await registry.load_all()
    
    scheduler = HandScheduler(registry)
    await scheduler.start()
    
    # Execute a Hand manually
    runner = HandRunner(registry, llm_adapter)
    result = await runner.run_hand("oracle")
"""

from hands.models import (
    ApprovalGate,
    ApprovalRequest,
    ApprovalStatus,
    HandConfig,
    HandExecution,
    HandOutcome,
    HandState,
    HandStatus,
    OutputConfig,
    ScheduleConfig,
    ToolRequirement,
    TriggerType,
)
from hands.registry import HandRegistry, HandNotFoundError, HandValidationError
from hands.scheduler import HandScheduler
from hands.runner import HandRunner

__all__ = [
    # Models
    "HandConfig",
    "HandState",
    "HandExecution",
    "HandStatus",
    "HandOutcome",
    "TriggerType",
    "ApprovalGate",
    "ApprovalRequest",
    "ApprovalStatus",
    "ScheduleConfig",
    "OutputConfig",
    "ToolRequirement",
    # Core classes
    "HandRegistry",
    "HandScheduler",
    "HandRunner",
    # Exceptions
    "HandNotFoundError",
    "HandValidationError",
]
