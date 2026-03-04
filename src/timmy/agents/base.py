"""Base agent class for all sub-agents.

All sub-agents inherit from BaseAgent and get:
- MCP tool registry access
- Event bus integration
- Memory integration
- Structured logging
"""

import logging
from abc import ABC, abstractmethod
from typing import Any, Optional

from agno.agent import Agent
from agno.models.ollama import Ollama

from config import settings
from infrastructure.events.bus import EventBus, Event

try:
    from mcp.registry import tool_registry
except ImportError:
    tool_registry = None

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """Base class for all sub-agents."""
    
    def __init__(
        self,
        agent_id: str,
        name: str,
        role: str,
        system_prompt: str,
        tools: list[str] | None = None,
    ) -> None:
        self.agent_id = agent_id
        self.name = name
        self.role = role
        self.tools = tools or []
        
        # Create Agno agent
        self.agent = self._create_agent(system_prompt)
        
        # Event bus for communication
        self.event_bus: Optional[EventBus] = None
        
        logger.info("%s agent initialized (id: %s)", name, agent_id)
    
    def _create_agent(self, system_prompt: str) -> Agent:
        """Create the underlying Agno agent."""
        # Get tools from registry
        tool_instances = []
        for tool_name in self.tools:
            handler = tool_registry.get_handler(tool_name)
            if handler:
                tool_instances.append(handler)
        
        return Agent(
            name=self.name,
            model=Ollama(id=settings.ollama_model, host=settings.ollama_url),
            description=system_prompt,
            tools=tool_instances if tool_instances else None,
            add_history_to_context=True,
            num_history_runs=10,
            markdown=True,
            telemetry=settings.telemetry_enabled,
        )
    
    def connect_event_bus(self, bus: EventBus) -> None:
        """Connect to the event bus for inter-agent communication."""
        self.event_bus = bus
        
        # Subscribe to relevant events
        bus.subscribe(f"agent.{self.agent_id}.*")(self._handle_direct_message)
        bus.subscribe("agent.task.assigned")(self._handle_task_assignment)
    
    async def _handle_direct_message(self, event: Event) -> None:
        """Handle direct messages to this agent."""
        logger.debug("%s received message: %s", self.name, event.type)
    
    async def _handle_task_assignment(self, event: Event) -> None:
        """Handle task assignment events."""
        assigned_agent = event.data.get("agent_id")
        if assigned_agent == self.agent_id:
            task_id = event.data.get("task_id")
            description = event.data.get("description", "")
            logger.info("%s assigned task %s: %s", self.name, task_id, description[:50])
            
            # Execute the task
            await self.execute_task(task_id, description, event.data)
    
    @abstractmethod
    async def execute_task(self, task_id: str, description: str, context: dict) -> Any:
        """Execute a task assigned to this agent.
        
        Must be implemented by subclasses.
        """
        pass
    
    async def run(self, message: str) -> str:
        """Run the agent with a message.
        
        Returns:
            Agent response
        """
        result = self.agent.run(message, stream=False)
        response = result.content if hasattr(result, "content") else str(result)
        
        # Emit completion event
        if self.event_bus:
            await self.event_bus.publish(Event(
                type=f"agent.{self.agent_id}.response",
                source=self.agent_id,
                data={"input": message, "output": response},
            ))
        
        return response
    
    def get_capabilities(self) -> list[str]:
        """Get list of capabilities this agent provides."""
        return self.tools
    
    def get_status(self) -> dict:
        """Get current agent status."""
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "role": self.role,
            "status": "ready",
            "tools": self.tools,
        }
