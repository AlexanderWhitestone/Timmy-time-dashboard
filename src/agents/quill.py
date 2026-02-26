"""Quill Agent — Writing and content generation.

Capabilities:
- Documentation writing
- Content creation
- Text editing
- Summarization
"""

from typing import Any

from agents.base import BaseAgent


QUILL_SYSTEM_PROMPT = """You are Quill, a writing and content generation specialist.

Your role is to create, edit, and improve written content.

## Capabilities

- Documentation writing
- Content creation
- Text editing and refinement
- Summarization
- Style adaptation

## Guidelines

1. **Write clearly** — Plain language, logical structure
2. **Know your audience** — Adapt tone and complexity
3. **Be concise** — Cut unnecessary words
4. **Use formatting** — Headers, lists, emphasis for readability

## Tool Usage

- Use write_file to save documents
- Use read_file to review existing content
- Use memory_search to check style preferences

## Response Format

Provide written content with:
- Clear structure (headers, sections)
- Appropriate tone for the context
- Proper formatting (markdown)
- Brief explanation of choices made

You work for Timmy, the sovereign AI orchestrator. Create polished, professional content.
"""


class QuillAgent(BaseAgent):
    """Writing and content specialist."""
    
    def __init__(self, agent_id: str = "quill") -> None:
        super().__init__(
            agent_id=agent_id,
            name="Quill",
            role="writing",
            system_prompt=QUILL_SYSTEM_PROMPT,
            tools=["write_file", "read_file", "memory_search"],
        )
    
    async def execute_task(self, task_id: str, description: str, context: dict) -> Any:
        """Execute a writing task."""
        prompt = f"Create the requested written content:\n\nTask: {description}\n\nWrite professionally with clear structure."
        
        result = await self.run(prompt)
        
        return {
            "task_id": task_id,
            "agent": self.agent_id,
            "result": result,
            "status": "completed",
        }
    
    async def write_documentation(self, topic: str, format: str = "markdown") -> str:
        """Write documentation for a topic."""
        prompt = f"Write comprehensive documentation for: {topic}\n\nFormat: {format}\nInclude: Overview, Usage, Examples, Notes"
        return await self.run(prompt)
