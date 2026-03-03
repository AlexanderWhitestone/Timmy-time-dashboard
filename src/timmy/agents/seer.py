"""Seer Agent — Research and information gathering.

Capabilities:
- Web search
- Information synthesis
- Fact checking
- Source evaluation
"""

from typing import Any

from timmy.agents.base import BaseAgent
from infrastructure.events.bus import Event


SEER_SYSTEM_PROMPT = """You are Seer, a research and information gathering specialist.

Your role is to find, evaluate, and synthesize information from external sources.

## Capabilities

- Web search for current information
- File reading for local documents
- Information synthesis and summarization
- Source evaluation (credibility assessment)

## Guidelines

1. **Be thorough** — Search multiple angles, verify facts
2. **Be skeptical** — Evaluate source credibility
3. **Be concise** — Summarize findings clearly
4. **Cite sources** — Reference where information came from

## Tool Usage

- Use web_search for external information
- Use read_file for local documents
- Use memory_search to check if we already know this

## Response Format

Provide findings in structured format:
- Summary (2-3 sentences)
- Key facts (bullet points)
- Sources (where information came from)
- Confidence level (high/medium/low)

"""


class SeerAgent(BaseAgent):
    """Research specialist agent."""
    
    def __init__(self, agent_id: str = "seer") -> None:
        super().__init__(
            agent_id=agent_id,
            name="Seer",
            role="research",
            system_prompt=SEER_SYSTEM_PROMPT,
            tools=["web_search", "read_file", "memory_search"],
        )
    
    async def execute_task(self, task_id: str, description: str, context: dict) -> Any:
        """Execute a research task."""
        # Determine research approach
        if "file" in description.lower() or "document" in description.lower():
            # Local document research
            prompt = f"Read and analyze the referenced document. Provide key findings:\n\nTask: {description}"
        else:
            # Web research
            prompt = f"Research the following topic thoroughly. Search for current information, evaluate sources, and provide a comprehensive summary:\n\nTask: {description}"
        
        result = await self.run(prompt)
        
        return {
            "task_id": task_id,
            "agent": self.agent_id,
            "result": result,
            "status": "completed",
        }
    
    async def research_topic(self, topic: str, depth: str = "standard") -> str:
        """Quick research on a topic."""
        prompts = {
            "quick": f"Quick search on: {topic}. Provide 3-5 key facts.",
            "standard": f"Research: {topic}. Search, synthesize, and summarize findings.",
            "deep": f"Deep research on: {topic}. Multiple searches, fact-checking, comprehensive report.",
        }
        
        return await self.run(prompts.get(depth, prompts["standard"]))
