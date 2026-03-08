"""Conversation context management for Timmy.

Tracks conversation state, intent, and context to improve:
- Contextual understanding across multi-turn conversations
- Smarter tool usage decisions
- Natural reference to prior exchanges
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class ConversationContext:
    """Tracks the current conversation state."""
    user_name: Optional[str] = None
    current_topic: Optional[str] = None
    last_intent: Optional[str] = None
    turn_count: int = 0
    started_at: datetime = field(default_factory=datetime.now)
    
    def update_topic(self, topic: str) -> None:
        """Update the current conversation topic."""
        self.current_topic = topic
        self.turn_count += 1
    
    def set_user_name(self, name: str) -> None:
        """Remember the user's name."""
        self.user_name = name
        logger.info("User name set to: %s", name)
    
    def get_context_summary(self) -> str:
        """Generate a context summary for the prompt."""
        parts = []
        if self.user_name:
            parts.append(f"User's name is {self.user_name}")
        if self.current_topic:
            parts.append(f"Current topic: {self.current_topic}")
        if self.turn_count > 0:
            parts.append(f"Conversation turn: {self.turn_count}")
        return " | ".join(parts) if parts else ""


class ConversationManager:
    """Manages conversation context across sessions."""
    
    def __init__(self) -> None:
        self._contexts: dict[str, ConversationContext] = {}
    
    def get_context(self, session_id: str) -> ConversationContext:
        """Get or create context for a session."""
        if session_id not in self._contexts:
            self._contexts[session_id] = ConversationContext()
        return self._contexts[session_id]
    
    def clear_context(self, session_id: str) -> None:
        """Clear context for a session."""
        if session_id in self._contexts:
            del self._contexts[session_id]
    
    # Words that look like names but are actually verbs/UI states
    _NAME_BLOCKLIST = frozenset({
        "sending", "loading", "pending", "processing", "typing",
        "working", "going", "trying", "looking", "getting", "doing",
        "waiting", "running", "checking", "coming", "leaving",
        "thinking", "reading", "writing", "watching", "listening",
        "playing", "eating", "sleeping", "sitting", "standing",
        "walking", "talking", "asking", "telling", "feeling",
        "hoping", "wondering", "glad", "happy", "sorry", "sure",
        "fine", "good", "great", "okay", "here", "there", "back",
        "done", "ready", "busy", "free", "available", "interested",
        "confused", "lost", "stuck", "curious", "excited", "tired",
        "not", "also", "just", "still", "already", "currently",
    })

    def extract_user_name(self, message: str) -> Optional[str]:
        """Try to extract user's name from message."""
        message_lower = message.lower()

        # Common patterns
        patterns = [
            "my name is ",
            "i'm ",
            "i am ",
            "call me ",
        ]

        for pattern in patterns:
            if pattern in message_lower:
                idx = message_lower.find(pattern) + len(pattern)
                remainder = message[idx:].strip()
                if not remainder:
                    continue
                # Take first word as name
                name = remainder.split()[0].strip(".,!?;:")
                if not name:
                    continue
                # Reject common verbs, adjectives, and UI-state words
                if name.lower() in self._NAME_BLOCKLIST:
                    continue
                # Capitalize first letter
                return name.capitalize()

        return None
    
    def should_use_tools(self, message: str, context: ConversationContext) -> bool:
        """Determine if this message likely requires tools.
        
        Returns True if tools are likely needed, False for simple chat.
        """
        message_lower = message.lower().strip()
        
        # Tool keywords that suggest tool usage is needed
        tool_keywords = [
            "search", "look up", "find", "google", "current price",
            "latest", "today's", "news", "weather", "stock price",
            "read file", "write file", "save", "calculate", "compute",
            "run ", "execute", "shell", "command", "install",
        ]
        
        # Chat-only keywords that definitely don't need tools
        chat_only = [
            "hello", "hi ", "hey", "how are you", "what's up",
            "your name", "who are you", "what are you",
            "thanks", "thank you", "bye", "goodbye",
            "tell me about yourself", "what can you do",
        ]
        
        # Check for chat-only patterns first
        for pattern in chat_only:
            if pattern in message_lower:
                return False
        
        # Check for tool keywords
        for keyword in tool_keywords:
            if keyword in message_lower:
                return True
        
        # Simple questions (starting with what, who, how, why, when, where)
        # usually don't need tools unless about current/real-time info
        simple_question_words = ["what is", "who is", "how does", "why is", "when did", "where is"]
        for word in simple_question_words:
            if message_lower.startswith(word):
                # Check if it's asking about current/real-time info
                time_words = ["today", "now", "current", "latest", "this week", "this month"]
                if any(t in message_lower for t in time_words):
                    return True
                return False
        
        # Default: don't use tools for unclear cases
        return False


# Module-level singleton
conversation_manager = ConversationManager()
