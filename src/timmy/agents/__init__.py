"""Agents package — Timmy orchestrator and toolsets.

Sub-agents (Seer, Forge, Quill, Echo, Helm) are kept for backwards
compatibility but Timmy now handles all requests directly using
toolset-based classification (see toolsets.py).
"""

from timmy.agents.timmy import TimmyOrchestrator, create_timmy_swarm
from timmy.agents.base import BaseAgent
from timmy.agents.toolsets import get_toolsets, classify_request

# Sub-agents kept for backwards compat — lazy import only
from timmy.agents.seer import SeerAgent
from timmy.agents.forge import ForgeAgent
from timmy.agents.quill import QuillAgent
from timmy.agents.echo import EchoAgent
from timmy.agents.helm import HelmAgent

__all__ = [
    "BaseAgent",
    "TimmyOrchestrator",
    "create_timmy_swarm",
    "get_toolsets",
    "classify_request",
    "SeerAgent",
    "ForgeAgent",
    "QuillAgent",
    "EchoAgent",
    "HelmAgent",
]
