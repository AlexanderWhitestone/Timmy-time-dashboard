"""Forge Agent — Code generation and tool building.

Capabilities:
- Code generation
- Tool/script creation
- System modifications
- Debugging assistance
"""

from typing import Any

from timmy.agents.base import BaseAgent


FORGE_SYSTEM_PROMPT = """You are Forge, a code generation and tool building specialist.

Your role is to write code, create tools, and modify systems.

## Capabilities

- Python code generation
- Tool/script creation
- File operations
- Code explanation and debugging

## Guidelines

1. **Write clean code** — Follow PEP 8, add docstrings
2. **Be safe** — Never execute destructive operations without confirmation
3. **Explain your work** — Provide context for what the code does
4. **Test mentally** — Walk through the logic before presenting

## Tool Usage

- Use python for code execution and testing
- Use write_file to save code (requires confirmation)
- Use read_file to examine existing code
- Use shell for system operations (requires confirmation)

## Response Format

Provide code in this structure:
- Purpose (what this code does)
- Code block (with language tag)
- Usage example
- Notes (any important considerations)

"""


class ForgeAgent(BaseAgent):
    """Code and tool building specialist."""
    
    def __init__(self, agent_id: str = "forge") -> None:
        super().__init__(
            agent_id=agent_id,
            name="Forge",
            role="code",
            system_prompt=FORGE_SYSTEM_PROMPT,
            tools=["python", "write_file", "read_file", "list_directory"],
        )
    
    async def execute_task(self, task_id: str, description: str, context: dict) -> Any:
        """Execute a code/task building task."""
        prompt = f"Create the requested code or tool:\n\nTask: {description}\n\nProvide complete, working code with documentation."
        
        result = await self.run(prompt)
        
        return {
            "task_id": task_id,
            "agent": self.agent_id,
            "result": result,
            "status": "completed",
        }
    
    async def generate_tool(self, name: str, purpose: str, parameters: list) -> str:
        """Generate a new MCP tool."""
        params_str = ", ".join(parameters)
        prompt = f"""Create a new MCP tool named '{name}'.

Purpose: {purpose}
Parameters: {params_str}

Generate:
1. The tool function with proper error handling
2. The MCP schema
3. Registration code

Follow the MCP pattern used in existing tools."""
        
        return await self.run(prompt)
