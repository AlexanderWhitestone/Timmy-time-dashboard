"""TimAgent Interface — The substrate-agnostic agent contract.

This is the foundation for embodiment. Whether Timmy runs on:
- A server with Ollama (today)
- A Raspberry Pi with sensors
- A Boston Dynamics Spot robot
- A VR avatar

The interface remains constant. Implementation varies.

Architecture:
    perceive()  →  reason  →  act()
         ↑                      ↓
         ←←← remember() ←←←←←←┘

All methods return effects that can be logged, audited, and replayed.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Any, Optional
import uuid


class PerceptionType(Enum):
    """Types of sensory input an agent can receive."""
    TEXT = auto()        # Natural language
    IMAGE = auto()       # Visual input
    AUDIO = auto()       # Sound/speech
    SENSOR = auto()      # Temperature, distance, etc.
    MOTION = auto()      # Accelerometer, gyroscope
    NETWORK = auto()     # API calls, messages
    INTERNAL = auto()    # Self-monitoring (battery, temp)


class ActionType(Enum):
    """Types of actions an agent can perform."""
    TEXT = auto()        # Generate text response
    SPEAK = auto()       # Text-to-speech
    MOVE = auto()        # Physical movement
    GRIP = auto()        # Manipulate objects
    CALL = auto()        # API/network call
    EMIT = auto()        # Signal/light/sound
    SLEEP = auto()       # Power management


class AgentCapability(Enum):
    """High-level capabilities a TimAgent may possess."""
    REASONING = "reasoning"
    CODING = "coding"
    WRITING = "writing"
    ANALYSIS = "analysis"
    VISION = "vision"
    SPEECH = "speech"
    NAVIGATION = "navigation"
    MANIPULATION = "manipulation"
    LEARNING = "learning"
    COMMUNICATION = "communication"


@dataclass(frozen=True)
class AgentIdentity:
    """Immutable identity for an agent instance.
    
    This persists across sessions and substrates. If Timmy moves
    from cloud to robot, the identity follows.
    """
    id: str
    name: str
    version: str
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    
    @classmethod
    def generate(cls, name: str, version: str = "1.0.0") -> "AgentIdentity":
        """Generate a new unique identity."""
        return cls(
            id=str(uuid.uuid4()),
            name=name,
            version=version,
        )


@dataclass
class Perception:
    """A sensory input to the agent.
    
    Substrate-agnostic representation. A camera image and a 
    LiDAR point cloud are both Perception instances.
    """
    type: PerceptionType
    data: Any  # Content depends on type
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    source: str = "unknown"  # e.g., "camera_1", "microphone", "user_input"
    metadata: dict = field(default_factory=dict)
    
    @classmethod
    def text(cls, content: str, source: str = "user") -> "Perception":
        """Factory for text perception."""
        return cls(
            type=PerceptionType.TEXT,
            data=content,
            source=source,
        )
    
    @classmethod
    def sensor(cls, kind: str, value: float, unit: str = "") -> "Perception":
        """Factory for sensor readings."""
        return cls(
            type=PerceptionType.SENSOR,
            data={"kind": kind, "value": value, "unit": unit},
            source=f"sensor_{kind}",
        )


@dataclass
class Action:
    """An action the agent intends to perform.
    
    Actions are effects — they describe what should happen,
    not how. The substrate implements the "how."
    """
    type: ActionType
    payload: Any  # Action-specific data
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    confidence: float = 1.0  # 0-1, agent's certainty
    deadline: Optional[str] = None  # When action must complete
    
    @classmethod
    def respond(cls, text: str, confidence: float = 1.0) -> "Action":
        """Factory for text response action."""
        return cls(
            type=ActionType.TEXT,
            payload=text,
            confidence=confidence,
        )
    
    @classmethod
    def move(cls, vector: tuple[float, float, float], speed: float = 1.0) -> "Action":
        """Factory for movement action (x, y, z meters)."""
        return cls(
            type=ActionType.MOVE,
            payload={"vector": vector, "speed": speed},
        )


@dataclass
class Memory:
    """A stored experience or fact.
    
    Memories are substrate-agnostic. A conversation history
    and a video recording are both Memory instances.
    """
    id: str
    content: Any
    created_at: str
    access_count: int = 0
    last_accessed: Optional[str] = None
    importance: float = 0.5  # 0-1, for pruning decisions
    tags: list[str] = field(default_factory=list)
    
    def touch(self) -> None:
        """Mark memory as accessed."""
        self.access_count += 1
        self.last_accessed = datetime.now(timezone.utc).isoformat()


@dataclass
class Communication:
    """A message to/from another agent or human."""
    sender: str
    recipient: str
    content: Any
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    protocol: str = "direct"  # e.g., "http", "websocket", "speech"
    encrypted: bool = False


class TimAgent(ABC):
    """Abstract base class for all Timmy agent implementations.
    
    This is the substrate-agnostic interface. Implementations:
    - OllamaAgent: LLM-based reasoning (today)
    - RobotAgent: Physical embodiment (future)
    - SimulationAgent: Virtual environment (future)
    
    Usage:
        agent = OllamaAgent(identity)  # Today's implementation
        
        perception = Perception.text("Hello Timmy")
        memory = agent.perceive(perception)
        
        action = agent.reason("How should I respond?")
        result = agent.act(action)
        
        agent.remember(memory)  # Store for future
    """
    
    def __init__(self, identity: AgentIdentity) -> None:
        self._identity = identity
        self._capabilities: set[AgentCapability] = set()
        self._state: dict[str, Any] = {}
    
    @property
    def identity(self) -> AgentIdentity:
        """Return this agent's immutable identity."""
        return self._identity
    
    @property
    def capabilities(self) -> set[AgentCapability]:
        """Return set of supported capabilities."""
        return self._capabilities.copy()
    
    def has_capability(self, capability: AgentCapability) -> bool:
        """Check if agent supports a capability."""
        return capability in self._capabilities
    
    @abstractmethod
    def perceive(self, perception: Perception) -> Memory:
        """Process sensory input and create a memory.
        
        This is the entry point for all agent interaction.
        A text message, camera frame, or temperature reading
        all enter through perceive().
        
        Args:
            perception: Sensory input
            
        Returns:
            Memory: Stored representation of the perception
        """
        pass
    
    @abstractmethod
    def reason(self, query: str, context: list[Memory]) -> Action:
        """Reason about a situation and decide on action.
        
        This is where "thinking" happens. The agent uses its
        substrate-appropriate reasoning (LLM, neural net, rules)
        to decide what to do.
        
        Args:
            query: What to reason about
            context: Relevant memories for context
            
        Returns:
            Action: What the agent decides to do
        """
        pass
    
    @abstractmethod
    def act(self, action: Action) -> Any:
        """Execute an action in the substrate.
        
        This is where the abstract action becomes concrete:
        - TEXT → Generate LLM response
        - MOVE → Send motor commands
        - SPEAK → Call TTS engine
        
        Args:
            action: The action to execute
            
        Returns:
            Result of the action (substrate-specific)
        """
        pass
    
    @abstractmethod
    def remember(self, memory: Memory) -> None:
        """Store a memory for future retrieval.
        
        The storage mechanism depends on substrate:
        - Cloud: SQLite, vector DB
        - Robot: Local flash storage
        - Hybrid: Synced with conflict resolution
        
        Args:
            memory: Experience to store
        """
        pass
    
    @abstractmethod
    def recall(self, query: str, limit: int = 5) -> list[Memory]:
        """Retrieve relevant memories.
        
        Args:
            query: What to search for
            limit: Maximum memories to return
            
        Returns:
            List of relevant memories, sorted by relevance
        """
        pass
    
    @abstractmethod
    def communicate(self, message: Communication) -> bool:
        """Send/receive communication with another agent.
        
        Args:
            message: Message to send
            
        Returns:
            True if communication succeeded
        """
        pass
    
    def get_state(self) -> dict[str, Any]:
        """Get current agent state for monitoring/debugging."""
        return {
            "identity": self._identity,
            "capabilities": list(self._capabilities),
            "state": self._state.copy(),
        }
    
    def shutdown(self) -> None:
        """Graceful shutdown. Persist state, close connections."""
        # Override in subclass for cleanup
        pass


class AgentEffect:
    """Log entry for agent actions — for audit and replay.
    
    The complete history of an agent's life can be captured
    as a sequence of AgentEffects. This enables:
    - Debugging: What did the agent see and do?
    - Audit: Why did it make that decision?
    - Replay: Reconstruct agent state from log
    - Training: Learn from agent experiences
    """
    
    def __init__(self, log_path: Optional[str] = None) -> None:
        self._effects: list[dict] = []
        self._log_path = log_path
    
    def log_perceive(self, perception: Perception, memory_id: str) -> None:
        """Log a perception event."""
        self._effects.append({
            "type": "perceive",
            "perception_type": perception.type.name,
            "source": perception.source,
            "memory_id": memory_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
    
    def log_reason(self, query: str, action_type: ActionType) -> None:
        """Log a reasoning event."""
        self._effects.append({
            "type": "reason",
            "query": query,
            "action_type": action_type.name,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
    
    def log_act(self, action: Action, result: Any) -> None:
        """Log an action event."""
        self._effects.append({
            "type": "act",
            "action_type": action.type.name,
            "confidence": action.confidence,
            "result_type": type(result).__name__,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
    
    def export(self) -> list[dict]:
        """Export effect log for analysis."""
        return self._effects.copy()
