"""PersonaNode — a SwarmNode with a specialised persona and smart bidding.

PersonaNode extends the base SwarmNode to:
1. Load its metadata (role, capabilities, bid strategy) from personas.PERSONAS.
2. Use capability-aware bidding: if a task description contains one of the
   persona's preferred_keywords the node bids aggressively (bid_base ± jitter).
   Otherwise it bids at a higher, less-competitive rate.
3. Register with the swarm registry under its persona's capabilities string.
4. (Adaptive) Consult the swarm learner to adjust bids based on historical
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

    # ── Properties ───────────────────────────────────────────────────────────

    @property
    def persona_id(self) -> str:
        return self._persona_id

    @property
    def rate_sats(self) -> int:
        return self._meta["rate_sats"]
