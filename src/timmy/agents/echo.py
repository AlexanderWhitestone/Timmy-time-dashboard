"""Echo Agent — Memory and context management.

Capabilities:
- Memory retrieval
- Context synthesis
- User profile management
- Conversation history
"""

from typing import Any

from timmy.agents.base import BaseAgent


ECHO_SYSTEM_PROMPT = """You are Echo, a memory and context management specialist.

Your role is to remember, retrieve, and synthesize information from the past.

## Capabilities

- Search past conversations
- Retrieve user preferences
- Synthesize context from multiple sources
- Manage user profile

## Guidelines

1. **Be accurate** — Only state what we actually know
2. **Be relevant** — Filter for context that matters now
3. **Be concise** — Summarize, don't dump everything
4. **Acknowledge uncertainty** — Say when memory is unclear

## Tool Usage

- Use memory_search to find relevant past context
- Use read_file to access vault files
- Use write_file to update user profile

## Response Format

Provide memory retrieval in this structure:
- Direct answer (what we know)
- Context (relevant past discussions)
- Confidence (certain/likely/speculative)
- Source (where this came from)

You work for Timmy, the sovereign AI orchestrator. Be the keeper of institutional knowledge.
"""


class EchoAgent(BaseAgent):
    """Memory and context specialist."""
    
    def __init__(self, agent_id: str = "echo") -> None:
        super().__init__(
            agent_id=agent_id,
            name="Echo",
            role="memory",
            system_prompt=ECHO_SYSTEM_PROMPT,
            tools=["memory_search", "read_file", "write_file"],
        )
    
    async def execute_task(self, task_id: str, description: str, context: dict) -> Any:
        """Execute a memory retrieval task."""
        # Extract what to search for
        prompt = f"Search memory and provide relevant context:\n\nTask: {description}\n\nSynthesize findings clearly."
        
        result = await self.run(prompt)
        
        return {
            "task_id": task_id,
            "agent": self.agent_id,
            "result": result,
            "status": "completed",
        }
    
    async def recall(self, query: str, include_sources: bool = True) -> str:
        """Quick memory recall."""
        sources = "with sources" if include_sources else ""
        prompt = f"Recall information about: {query} {sources}\n\nProvide relevant context from memory."
        return await self.run(prompt)
