"""PersonaNode — a SwarmNode with a specialised persona and smart bidding.

PersonaNode extends the base SwarmNode to:
1. Load its metadata (role, capabilities, bid strategy) from personas.PERSONAS.
2. Use capability-aware bidding: if a task description contains one of the
   persona's preferred_keywords the node bids aggressively (bid_base ± jitter).
   Otherwise it bids at a higher, less-competitive rate.
3. Register with the swarm registry under its persona's capabilities string.
4. Execute tasks using persona-appropriate MCP tools when assigned.
5. (Adaptive) Consult the swarm learner to adjust bids based on historical
   win/loss and success/failure data when available.

Usage (via coordinator):
    coordinator.spawn_persona("echo")
"""

from __future__ import annotations

import logging
import random
from typing import Optional

from swarm.comms import SwarmComms, SwarmMessage
from swarm.personas import PERSONAS, PersonaMeta
from swarm.swarm_node import SwarmNode
from swarm.tool_executor import ToolExecutor

logger = logging.getLogger(__name__)

# How much we inflate the bid when the task is outside our specialisation
_OFF_SPEC_MULTIPLIER = 1.8


class PersonaNode(SwarmNode):
    """A SwarmNode with persona-driven bid strategy."""

    def __init__(
        self,
        persona_id: str,
        agent_id: str,
        comms: Optional[SwarmComms] = None,
        use_learner: bool = True,
    ) -> None:
        meta: PersonaMeta = PERSONAS[persona_id]
        super().__init__(
            agent_id=agent_id,
            name=meta["name"],
            capabilities=meta["capabilities"],
            comms=comms,
        )
        self._meta = meta
        self._persona_id = persona_id
        self._use_learner = use_learner
        
        # Initialize tool executor for task execution
        self._tool_executor: Optional[ToolExecutor] = None
        try:
            self._tool_executor = ToolExecutor.for_persona(
                persona_id, agent_id
            )
        except Exception as exc:
            logger.warning(
                "Failed to initialize tools for %s: %s. "
                "Agent will work in chat-only mode.",
                agent_id, exc
            )
        
        # Track current task
        self._current_task: Optional[str] = None
        
        # Subscribe to task assignments
        if self._comms:
            self._comms.subscribe("swarm:events", self._on_swarm_event)
        
        logger.debug("PersonaNode %s (%s) initialised", meta["name"], agent_id)

    # ── Bid strategy ─────────────────────────────────────────────────────────

    def _compute_bid(self, task_description: str) -> int:
        """Return the sats bid for this task.

        Bids lower (more aggressively) when the description contains at least
        one of our preferred_keywords.  Bids higher for off-spec tasks.

        When the learner is enabled and the agent has enough history, the
        base bid is adjusted by learned performance metrics before jitter.
        """
        desc_lower = task_description.lower()
        is_preferred = any(
            kw in desc_lower for kw in self._meta["preferred_keywords"]
        )
        base = self._meta["bid_base"]
        jitter = random.randint(0, self._meta["bid_jitter"])
        if is_preferred:
            raw = max(1, base - jitter)
        else:
            # Off-spec: inflate bid so we lose to the specialist
            raw = min(200, int(base * _OFF_SPEC_MULTIPLIER) + jitter)

        # Consult learner for adaptive adjustment
        if self._use_learner:
            try:
                from swarm.learner import suggest_bid
                return suggest_bid(self.agent_id, task_description, raw)
            except Exception:
                logger.debug("Learner unavailable, using static bid")
        return raw

    def _on_task_posted(self, msg: SwarmMessage) -> None:
        """Handle task announcement with persona-aware bidding."""
        task_id = msg.data.get("task_id")
        description = msg.data.get("description", "")
        if not task_id:
            return
        bid_sats = self._compute_bid(description)
        self._comms.submit_bid(
            task_id=task_id,
            agent_id=self.agent_id,
            bid_sats=bid_sats,
        )
        logger.info(
            "PersonaNode %s bid %d sats on task %s (preferred=%s)",
            self.name,
            bid_sats,
            task_id,
            any(kw in description.lower() for kw in self._meta["preferred_keywords"]),
        )
    
    def _on_swarm_event(self, msg: SwarmMessage) -> None:
        """Handle swarm events including task assignments."""
        event_type = msg.data.get("type")
        
        if event_type == "task_assigned":
            task_id = msg.data.get("task_id")
            agent_id = msg.data.get("agent_id")
            
            # Check if assigned to us
            if agent_id == self.agent_id:
                self._handle_task_assignment(task_id)
    
    def _handle_task_assignment(self, task_id: str) -> None:
        """Handle being assigned a task.
        
        This is where the agent actually does the work using its tools.
        """
        logger.info(
            "PersonaNode %s assigned task %s, beginning execution",
            self.name, task_id
        )
        self._current_task = task_id
        
        # Get task description from recent messages or lookup
        # For now, we need to fetch the task details
        try:
            from swarm.tasks import get_task
            task = get_task(task_id)
            if not task:
                logger.error("Task %s not found", task_id)
                self._complete_task(task_id, "Error: Task not found")
                return
            
            description = task.description
            
            # Execute using tools
            if self._tool_executor:
                result = self._tool_executor.execute_task(description)
                
                if result["success"]:
                    output = result["result"]
                    tools = ", ".join(result["tools_used"]) if result["tools_used"] else "none"
                    completion_text = f"Task completed. Tools used: {tools}.\n\nResult:\n{output}"
                else:
                    completion_text = f"Task failed: {result.get('error', 'Unknown error')}"
                
                self._complete_task(task_id, completion_text)
            else:
                # No tools available - chat-only response
                response = (
                    f"I received task: {description}\n\n"
                    f"However, I don't have access to specialized tools at the moment. "
                    f"As a {self.name} specialist, I would typically use: "
                    f"{self._meta['capabilities']}"
                )
                self._complete_task(task_id, response)
                
        except Exception as exc:
            logger.exception("Task execution failed for %s", task_id)
            self._complete_task(task_id, f"Error during execution: {exc}")
        finally:
            self._current_task = None
    
    def _complete_task(self, task_id: str, result: str) -> None:
        """Mark task as complete and notify coordinator."""
        if self._comms:
            self._comms.complete_task(task_id, self.agent_id, result)
        logger.info(
            "PersonaNode %s completed task %s (result length: %d chars)",
            self.name, task_id, len(result)
        )

    # ── Properties ───────────────────────────────────────────────────────────

    @property
    def persona_id(self) -> str:
        return self._persona_id

    @property
    def rate_sats(self) -> int:
        return self._meta["rate_sats"]
    
    @property
    def current_task(self) -> Optional[str]:
        """Return the task ID currently being executed, if any."""
        return self._current_task
    
    @property
    def tool_capabilities(self) -> list[str]:
        """Return list of available tool names."""
        if self._tool_executor:
            return self._tool_executor.get_capabilities()
        return []
