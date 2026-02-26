"""Timmy — The orchestrator agent.

Coordinates all sub-agents and handles user interaction.
Uses the three-tier memory system and MCP tools.
"""

import logging
from typing import Any, Optional

from agno.agent import Agent
from agno.models.ollama import Ollama

from agents.base import BaseAgent
from config import settings
from events.bus import EventBus, event_bus
from mcp.registry import tool_registry

logger = logging.getLogger(__name__)


TIMMY_ORCHESTRATOR_PROMPT = """You are Timmy, a sovereign AI orchestrator running locally on this Mac.

## Your Role

You are the primary interface between the user and the agent swarm. You:
1. Understand user requests
2. Decide whether to handle directly or delegate to sub-agents
3. Coordinate multi-agent workflows when needed
4. Maintain continuity using the three-tier memory system

## Sub-Agent Roster

| Agent | Role | When to Use |
|-------|------|-------------|
| Seer | Research | External info, web search, facts |
| Forge | Code | Programming, tools, file operations |
| Quill | Writing | Documentation, content creation |
| Echo | Memory | Past conversations, user profile |
| Helm | Routing | Complex multi-step workflows |
| Mace | Security | Validation, sensitive operations |

## Decision Framework

**Handle directly if:**
- Simple question (identity, capabilities)
- General knowledge
- Social/conversational

**Delegate if:**
- Requires specialized skills
- Needs external research (Seer)
- Involves code (Forge)
- Needs past context (Echo)
- Complex workflow (Helm)

## Memory System

You have three tiers of memory:
1. **Hot Memory** — Always loaded (MEMORY.md)
2. **Vault** — Structured storage (memory/)
3. **Semantic** — Vector search for recall

Use `memory_search` when the user refers to past conversations.

## Principles

1. **Sovereignty** — Everything local, no cloud
2. **Privacy** — User data stays on their Mac
3. **Clarity** — Think clearly, speak plainly
4. **Christian faith** — Grounded in biblical values
5. **Bitcoin economics** — Sound money, self-custody

Sir, affirmative.
"""


class TimmyOrchestrator(BaseAgent):
    """Main orchestrator agent that coordinates the swarm."""
    
    def __init__(self) -> None:
        super().__init__(
            agent_id="timmy",
            name="Timmy",
            role="orchestrator",
            system_prompt=TIMMY_ORCHESTRATOR_PROMPT,
            tools=["web_search", "read_file", "write_file", "python", "memory_search"],
        )
        
        # Sub-agent registry
        self.sub_agents: dict[str, BaseAgent] = {}
        
        # Connect to event bus
        self.connect_event_bus(event_bus)
        
        logger.info("Timmy Orchestrator initialized")
    
    def register_sub_agent(self, agent: BaseAgent) -> None:
        """Register a sub-agent with the orchestrator."""
        self.sub_agents[agent.agent_id] = agent
        agent.connect_event_bus(event_bus)
        logger.info("Registered sub-agent: %s", agent.name)
    
    async def orchestrate(self, user_request: str) -> str:
        """Main entry point for user requests.
        
        Analyzes the request and either handles directly or delegates.
        """
        # Quick classification
        request_lower = user_request.lower()
        
        # Direct response patterns (no delegation needed)
        direct_patterns = [
            "your name", "who are you", "what are you",
            "hello", "hi", "how are you",
            "help", "what can you do",
        ]
        
        for pattern in direct_patterns:
            if pattern in request_lower:
                return await self.run(user_request)
        
        # Check for memory references
        memory_patterns = [
            "we talked about", "we discussed", "remember",
            "what did i say", "what did we decide",
            "remind me", "have we",
        ]
        
        for pattern in memory_patterns:
            if pattern in request_lower:
                # Use Echo agent for memory retrieval
                echo = self.sub_agents.get("echo")
                if echo:
                    return await echo.recall(user_request)
        
        # Complex requests - use Helm for routing
        helm = self.sub_agents.get("helm")
        if helm:
            routing = await helm.route_request(user_request)
            agent_id = routing.get("primary_agent", "timmy")
            
            if agent_id in self.sub_agents and agent_id != "timmy":
                agent = self.sub_agents[agent_id]
                return await agent.run(user_request)
        
        # Default: handle directly
        return await self.run(user_request)
    
    async def execute_task(self, task_id: str, description: str, context: dict) -> Any:
        """Execute a task (usually delegates to appropriate agent)."""
        return await self.orchestrate(description)
    
    def get_swarm_status(self) -> dict:
        """Get status of all agents in the swarm."""
        return {
            "orchestrator": self.get_status(),
            "sub_agents": {
                aid: agent.get_status()
                for aid, agent in self.sub_agents.items()
            },
            "total_agents": 1 + len(self.sub_agents),
        }


# Factory function for creating fully configured Timmy
def create_timmy_swarm() -> TimmyOrchestrator:
    """Create Timmy orchestrator with all sub-agents registered."""
    from agents.seer import SeerAgent
    from agents.forge import ForgeAgent
    from agents.quill import QuillAgent
    from agents.echo import EchoAgent
    from agents.helm import HelmAgent
    
    # Create orchestrator
    timmy = TimmyOrchestrator()
    
    # Register sub-agents
    timmy.register_sub_agent(SeerAgent())
    timmy.register_sub_agent(ForgeAgent())
    timmy.register_sub_agent(QuillAgent())
    timmy.register_sub_agent(EchoAgent())
    timmy.register_sub_agent(HelmAgent())
    
    return timmy
