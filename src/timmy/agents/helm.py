"""Helm Agent — Routing and orchestration decisions.

Capabilities:
- Task analysis
- Agent selection
- Workflow planning
- Priority management
"""

from typing import Any

from timmy.agents.base import BaseAgent


HELM_SYSTEM_PROMPT = """You are Helm, a routing and orchestration specialist.

Your role is to analyze tasks and decide how to route them to other agents.

## Capabilities

- Task analysis and decomposition
- Agent selection for tasks
- Workflow planning
- Priority assessment

## Guidelines

1. **Analyze carefully** — Understand what the task really needs
2. **Route wisely** — Match tasks to agent strengths
3. **Consider dependencies** — Some tasks need sequencing
4. **Be efficient** — Don't over-complicate simple tasks

## Agent Roster

- Seer: Research, information gathering
- Forge: Code, tools, system changes
- Quill: Writing, documentation
- Echo: Memory, context retrieval
- Mace: Security, validation (use for sensitive operations)

## Response Format

Provide routing decisions as:
- Task breakdown (subtasks if needed)
- Agent assignment (who does what)
- Execution order (sequence if relevant)
- Rationale (why this routing)

"""


class HelmAgent(BaseAgent):
    """Routing and orchestration specialist."""
    
    def __init__(self, agent_id: str = "helm") -> None:
        super().__init__(
            agent_id=agent_id,
            name="Helm",
            role="routing",
            system_prompt=HELM_SYSTEM_PROMPT,
            tools=["memory_search"],  # May need to check past routing decisions
        )
    
    async def execute_task(self, task_id: str, description: str, context: dict) -> Any:
        """Execute a routing task."""
        prompt = f"Analyze and route this task:\n\nTask: {description}\n\nProvide routing decision with rationale."
        
        result = await self.run(prompt)
        
        return {
            "task_id": task_id,
            "agent": self.agent_id,
            "result": result,
            "status": "completed",
        }
    
    async def route_request(self, request: str) -> dict:
        """Analyze a request and suggest routing."""
        prompt = f"""Analyze this request and determine the best agent(s) to handle it:

Request: {request}

Respond in this format:
Primary Agent: [agent name]
Reason: [why this agent]
Secondary Agents: [if needed]
Complexity: [simple/moderate/complex]
"""
        result = await self.run(prompt)
        
        # Parse result into structured format
        # This is simplified - in production, use structured output
        return {
            "analysis": result,
            "primary_agent": self._extract_agent(result),
        }
    
    def _extract_agent(self, text: str) -> str:
        """Extract agent name from routing text."""
        agents = ["seer", "forge", "quill", "echo", "mace", "helm"]
        text_lower = text.lower()
        for agent in agents:
            if agent in text_lower:
                return agent
        return "orchestrator"  # Default to orchestrator
