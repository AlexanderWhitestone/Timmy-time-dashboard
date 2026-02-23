"""Ollama-based implementation of TimAgent interface.

This adapter wraps the existing Timmy Ollama agent to conform
to the substrate-agnostic TimAgent interface. It's the bridge
between the old codebase and the new embodiment-ready architecture.

Usage:
    from agent_core import AgentIdentity, Perception
    from agent_core.ollama_adapter import OllamaAgent
    
    identity = AgentIdentity.generate("Timmy")
    agent = OllamaAgent(identity)
    
    perception = Perception.text("Hello!")
    memory = agent.perceive(perception)
    action = agent.reason("How should I respond?", [memory])
    result = agent.act(action)
"""

from typing import Any, Optional

from agent_core.interface import (
    AgentCapability,
    AgentIdentity,
    Perception,
    PerceptionType,
    Action,
    ActionType,
    Memory,
    Communication,
    TimAgent,
    AgentEffect,
)
from timmy.agent import create_timmy


class OllamaAgent(TimAgent):
    """TimAgent implementation using local Ollama LLM.
    
    This is the production agent for Timmy Time v2. It uses
    Ollama for reasoning and SQLite for memory persistence.
    
    Capabilities:
    - REASONING: LLM-based inference
    - CODING: Code generation and analysis
    - WRITING: Long-form content creation
    - ANALYSIS: Data processing and insights
    - COMMUNICATION: Multi-agent messaging
    """
    
    def __init__(
        self,
        identity: AgentIdentity,
        model: Optional[str] = None,
        effect_log: Optional[str] = None,
    ) -> None:
        """Initialize Ollama-based agent.
        
        Args:
            identity: Agent identity (persistent across sessions)
            model: Ollama model to use (default from config)
            effect_log: Path to log agent effects (optional)
        """
        super().__init__(identity)
        
        # Initialize underlying Ollama agent
        self._timmy = create_timmy(model=model)
        
        # Set capabilities based on what Ollama can do
        self._capabilities = {
            AgentCapability.REASONING,
            AgentCapability.CODING,
            AgentCapability.WRITING,
            AgentCapability.ANALYSIS,
            AgentCapability.COMMUNICATION,
        }
        
        # Effect logging for audit/replay
        self._effect_log = AgentEffect(effect_log) if effect_log else None
        
        # Simple in-memory working memory (short term)
        self._working_memory: list[Memory] = []
        self._max_working_memory = 10
    
    def perceive(self, perception: Perception) -> Memory:
        """Process perception and store in memory.
        
        For text perceptions, we might do light preprocessing
        (summarization, keyword extraction) before storage.
        """
        # Create memory from perception
        memory = Memory(
            id=f"mem_{len(self._working_memory)}",
            content={
                "type": perception.type.name,
                "data": perception.data,
                "source": perception.source,
            },
            created_at=perception.timestamp,
            tags=self._extract_tags(perception),
        )
        
        # Add to working memory
        self._working_memory.append(memory)
        if len(self._working_memory) > self._max_working_memory:
            self._working_memory.pop(0)  # FIFO eviction
        
        # Log effect
        if self._effect_log:
            self._effect_log.log_perceive(perception, memory.id)
        
        return memory
    
    def reason(self, query: str, context: list[Memory]) -> Action:
        """Use LLM to reason and decide on action.
        
        This is where the Ollama agent does its work. We construct
        a prompt from the query and context, then interpret the
        response as an action.
        """
        # Build context string from memories
        context_str = self._format_context(context)
        
        # Construct prompt
        prompt = f"""You are {self._identity.name}, an AI assistant.

Context from previous interactions:
{context_str}

Current query: {query}

Respond naturally and helpfully."""
        
        # Run LLM inference
        result = self._timmy.run(prompt, stream=False)
        response_text = result.content if hasattr(result, "content") else str(result)
        
        # Create text response action
        action = Action.respond(response_text, confidence=0.9)
        
        # Log effect
        if self._effect_log:
            self._effect_log.log_reason(query, action.type)
        
        return action
    
    def act(self, action: Action) -> Any:
        """Execute action in the Ollama substrate.
        
        For text actions, the "execution" is just returning the
        text (already generated during reasoning). For future
        action types (MOVE, SPEAK), this would trigger the
        appropriate Ollama tool calls.
        """
        result = None
        
        if action.type == ActionType.TEXT:
            result = action.payload
        elif action.type == ActionType.SPEAK:
            # Would call TTS here
            result = {"spoken": action.payload, "tts_engine": "pyttsx3"}
        elif action.type == ActionType.CALL:
            # Would make API call
            result = {"status": "not_implemented", "payload": action.payload}
        else:
            result = {"error": f"Action type {action.type} not supported by OllamaAgent"}
        
        # Log effect
        if self._effect_log:
            self._effect_log.log_act(action, result)
        
        return result
    
    def remember(self, memory: Memory) -> None:
        """Store memory persistently.
        
        For now, working memory is sufficient. In the future,
        this would write to SQLite or vector DB for long-term
        memory across sessions.
        """
        # Mark as accessed to update importance
        memory.touch()
        
        # TODO: Persist to SQLite for long-term memory
        # This would integrate with the existing briefing system
        pass
    
    def recall(self, query: str, limit: int = 5) -> list[Memory]:
        """Retrieve relevant memories.
        
        Simple keyword matching for now. Future: vector similarity.
        """
        query_lower = query.lower()
        scored = []
        
        for memory in self._working_memory:
            score = 0
            content_str = str(memory.content).lower()
            
            # Simple keyword overlap
            query_words = set(query_lower.split())
            content_words = set(content_str.split())
            overlap = len(query_words & content_words)
            score += overlap
            
            # Boost recent memories
            score += memory.importance
            
            scored.append((score, memory))
        
        # Sort by score descending
        scored.sort(key=lambda x: x[0], reverse=True)
        
        # Return top N
        return [m for _, m in scored[:limit]]
    
    def communicate(self, message: Communication) -> bool:
        """Send message to another agent.
        
        This would use the swarm comms layer for inter-agent
        messaging. For now, it's a stub.
        """
        # TODO: Integrate with swarm.comms
        return True
    
    def _extract_tags(self, perception: Perception) -> list[str]:
        """Extract searchable tags from perception."""
        tags = [perception.type.name, perception.source]
        
        if perception.type == PerceptionType.TEXT:
            # Simple keyword extraction
            text = str(perception.data).lower()
            keywords = ["code", "bug", "help", "question", "task"]
            for kw in keywords:
                if kw in text:
                    tags.append(kw)
        
        return tags
    
    def _format_context(self, memories: list[Memory]) -> str:
        """Format memories into context string for prompt."""
        if not memories:
            return "No previous context."
        
        parts = []
        for mem in memories[-5:]:  # Last 5 memories
            if isinstance(mem.content, dict):
                data = mem.content.get("data", "")
                parts.append(f"- {data}")
            else:
                parts.append(f"- {mem.content}")
        
        return "\n".join(parts)
    
    def get_effect_log(self) -> Optional[list[dict]]:
        """Export effect log if logging is enabled."""
        if self._effect_log:
            return self._effect_log.export()
        return None
