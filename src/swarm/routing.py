"""Intelligent swarm routing with capability-based task dispatch.

Routes tasks to the most suitable agents based on:
- Capability matching (what can the agent do?)
- Historical performance (who's good at this?)
- Current load (who's available?)
- Bid competitiveness (who's cheapest?)

All routing decisions are logged for audit and improvement.
"""

import hashlib
import json
import logging
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from swarm.personas import PERSONAS, PersonaMeta

logger = logging.getLogger(__name__)

# SQLite storage for routing audit logs
DB_PATH = Path("data/swarm.db")


@dataclass
class CapabilityManifest:
    """Describes what an agent can do and how well it does it.
    
    This is the foundation of intelligent routing. Each agent
    (persona) declares its capabilities, and the router scores
    tasks against these declarations.
    """
    agent_id: str
    agent_name: str
    capabilities: list[str]  # e.g., ["coding", "debugging", "python"]
    keywords: list[str]      # Words that trigger this agent
    rate_sats: int          # Base rate for this agent type
    success_rate: float = 0.0   # Historical success (0-1)
    avg_completion_time: float = 0.0  # Seconds
    total_tasks: int = 0
    
    def score_task_match(self, task_description: str) -> float:
        """Score how well this agent matches a task (0-1).
        
        Higher score = better match = should bid lower.
        """
        desc_lower = task_description.lower()
        words = set(desc_lower.split())
        
        score = 0.0
        
        # Keyword matches (strong signal)
        for kw in self.keywords:
            if kw.lower() in desc_lower:
                score += 0.3
        
        # Capability matches (moderate signal)
        for cap in self.capabilities:
            if cap.lower() in desc_lower:
                score += 0.2
        
        # Related word matching (weak signal)
        related_words = {
            "code": ["function", "class", "bug", "fix", "implement"],
            "write": ["document", "draft", "content", "article"],
            "analyze": ["data", "report", "metric", "insight"],
            "security": ["vulnerability", "threat", "audit", "scan"],
        }
        for cap in self.capabilities:
            if cap.lower() in related_words:
                for related in related_words[cap.lower()]:
                    if related in desc_lower:
                        score += 0.1
        
        # Cap at 1.0
        return min(score, 1.0)


@dataclass
class RoutingDecision:
    """Record of a routing decision for audit and learning.
    
    Immutable once created — the log of truth for what happened.
    """
    task_id: str
    task_description: str
    candidate_agents: list[str]  # Who was considered
    selected_agent: Optional[str]  # Who won (None if no bids)
    selection_reason: str  # Why this agent was chosen
    capability_scores: dict[str, float]  # Score per agent
    bids_received: dict[str, int]  # Bid amount per agent
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    
    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "task_description": self.task_description[:100],  # Truncate
            "candidate_agents": self.candidate_agents,
            "selected_agent": self.selected_agent,
            "selection_reason": self.selection_reason,
            "capability_scores": self.capability_scores,
            "bids_received": self.bids_received,
            "timestamp": self.timestamp,
        }


class RoutingEngine:
    """Intelligent task routing with audit logging.
    
    The engine maintains capability manifests for all agents
    and uses them to score task matches. When a task comes in:
    
    1. Score each agent's capability match
    2. Let agents bid (lower bid = more confident)
    3. Select winner based on bid + capability score
    4. Log the decision for audit
    """
    
    def __init__(self) -> None:
        self._manifests: dict[str, CapabilityManifest] = {}
        self._lock = threading.Lock()
        self._db_initialized = False
        self._init_db()
        logger.info("RoutingEngine initialized")
    
    def _init_db(self) -> None:
        """Create routing audit table."""
        try:
            DB_PATH.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(DB_PATH))
            conn.execute("""
                CREATE TABLE IF NOT EXISTS routing_decisions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    task_hash TEXT NOT NULL,  -- For deduplication
                    selected_agent TEXT,
                    selection_reason TEXT,
                    decision_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_routing_task 
                ON routing_decisions(task_id)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_routing_time 
                ON routing_decisions(created_at)
            """)
            conn.commit()
            conn.close()
            self._db_initialized = True
        except sqlite3.Error as e:
            logger.warning("Failed to init routing DB: %s", e)
            self._db_initialized = False
    
    def register_persona(self, persona_id: str, agent_id: str) -> CapabilityManifest:
        """Create a capability manifest from a persona definition."""
        meta = PERSONAS.get(persona_id)
        if not meta:
            raise ValueError(f"Unknown persona: {persona_id}")
        
        manifest = CapabilityManifest(
            agent_id=agent_id,
            agent_name=meta["name"],
            capabilities=meta["capabilities"].split(","),
            keywords=meta["preferred_keywords"],
            rate_sats=meta["rate_sats"],
        )
        
        with self._lock:
            self._manifests[agent_id] = manifest
        
        logger.debug("Registered %s (%s) with %d capabilities",
                     meta["name"], agent_id, len(manifest.capabilities))
        return manifest
    
    def register_custom_manifest(self, manifest: CapabilityManifest) -> None:
        """Register a custom capability manifest."""
        with self._lock:
            self._manifests[manifest.agent_id] = manifest
    
    def get_manifest(self, agent_id: str) -> Optional[CapabilityManifest]:
        """Get an agent's capability manifest."""
        with self._lock:
            return self._manifests.get(agent_id)
    
    def score_candidates(self, task_description: str) -> dict[str, float]:
        """Score all registered agents against a task.
        
        Returns:
            Dict mapping agent_id -> match score (0-1)
        """
        with self._lock:
            manifests = dict(self._manifests)
        
        scores = {}
        for agent_id, manifest in manifests.items():
            scores[agent_id] = manifest.score_task_match(task_description)
        
        return scores
    
    def recommend_agent(
        self,
        task_id: str,
        task_description: str,
        bids: dict[str, int],
    ) -> tuple[Optional[str], RoutingDecision]:
        """Recommend the best agent for a task.
        
        Scoring formula:
            final_score = capability_score * 0.6 + (1 / bid) * 0.4
        
        Higher capability + lower bid = better agent.
        
        Returns:
            Tuple of (selected_agent_id, routing_decision)
        """
        capability_scores = self.score_candidates(task_description)
        
        # Filter to only bidders
        candidate_ids = list(bids.keys())
        
        if not candidate_ids:
            decision = RoutingDecision(
                task_id=task_id,
                task_description=task_description,
                candidate_agents=[],
                selected_agent=None,
                selection_reason="No bids received",
                capability_scores=capability_scores,
                bids_received=bids,
            )
            self._log_decision(decision)
            return None, decision
        
        # Calculate combined scores
        combined_scores = {}
        for agent_id in candidate_ids:
            cap_score = capability_scores.get(agent_id, 0.0)
            bid = bids[agent_id]
            # Normalize bid: lower is better, so invert
            # Assuming bids are 10-100 sats, normalize to 0-1
            bid_score = max(0, min(1, (100 - bid) / 90))
            
            combined_scores[agent_id] = cap_score * 0.6 + bid_score * 0.4
        
        # Select best
        winner = max(combined_scores, key=combined_scores.get)
        winner_cap = capability_scores.get(winner, 0.0)
        
        reason = (
            f"Selected {winner} with capability_score={winner_cap:.2f}, "
            f"bid={bids[winner]} sats, combined={combined_scores[winner]:.2f}"
        )
        
        decision = RoutingDecision(
            task_id=task_id,
            task_description=task_description,
            candidate_agents=candidate_ids,
            selected_agent=winner,
            selection_reason=reason,
            capability_scores=capability_scores,
            bids_received=bids,
        )
        
        self._log_decision(decision)
        
        logger.info("Routing: %s → %s (score: %.2f)",
                    task_id[:8], winner[:8], combined_scores[winner])
        
        return winner, decision
    
    def _log_decision(self, decision: RoutingDecision) -> None:
        """Persist routing decision to audit log."""
        # Ensure DB is initialized (handles test DB resets)
        if not self._db_initialized:
            self._init_db()
        
        # Create hash for deduplication
        task_hash = hashlib.sha256(
            f"{decision.task_id}:{decision.timestamp}".encode()
        ).hexdigest()[:16]
        
        try:
            conn = sqlite3.connect(str(DB_PATH))
            conn.execute(
                """
                INSERT INTO routing_decisions 
                (task_id, task_hash, selected_agent, selection_reason, decision_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    decision.task_id,
                    task_hash,
                    decision.selected_agent,
                    decision.selection_reason,
                    json.dumps(decision.to_dict()),
                    decision.timestamp,
                )
            )
            conn.commit()
            conn.close()
        except sqlite3.Error as e:
            logger.warning("Failed to log routing decision: %s", e)
    
    def get_routing_history(
        self,
        task_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        limit: int = 100,
    ) -> list[RoutingDecision]:
        """Query routing decision history.
        
        Args:
            task_id: Filter to specific task
            agent_id: Filter to decisions involving this agent
            limit: Max results to return
        """
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        
        if task_id:
            rows = conn.execute(
                "SELECT * FROM routing_decisions WHERE task_id = ? ORDER BY created_at DESC LIMIT ?",
                (task_id, limit)
            ).fetchall()
        elif agent_id:
            rows = conn.execute(
                """SELECT * FROM routing_decisions 
                   WHERE selected_agent = ? OR decision_json LIKE ? 
                   ORDER BY created_at DESC LIMIT ?""",
                (agent_id, f'%"{agent_id}"%', limit)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM routing_decisions ORDER BY created_at DESC LIMIT ?",
                (limit,)
            ).fetchall()
        
        conn.close()
        
        decisions = []
        for row in rows:
            data = json.loads(row["decision_json"])
            decisions.append(RoutingDecision(
                task_id=data["task_id"],
                task_description=data["task_description"],
                candidate_agents=data["candidate_agents"],
                selected_agent=data["selected_agent"],
                selection_reason=data["selection_reason"],
                capability_scores=data["capability_scores"],
                bids_received=data["bids_received"],
                timestamp=data["timestamp"],
            ))
        
        return decisions
    
    def get_agent_stats(self, agent_id: str) -> dict:
        """Get routing statistics for an agent.
        
        Returns:
            Dict with wins, avg_score, total_tasks, etc.
        """
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        
        # Count wins
        wins = conn.execute(
            "SELECT COUNT(*) FROM routing_decisions WHERE selected_agent = ?",
            (agent_id,)
        ).fetchone()[0]
        
        # Count total appearances
        total = conn.execute(
            "SELECT COUNT(*) FROM routing_decisions WHERE decision_json LIKE ?",
            (f'%"{agent_id}"%',)
        ).fetchone()[0]
        
        conn.close()
        
        return {
            "agent_id": agent_id,
            "tasks_won": wins,
            "tasks_considered": total,
            "win_rate": wins / total if total > 0 else 0.0,
        }
    
    def export_audit_log(self, since: Optional[str] = None) -> list[dict]:
        """Export full audit log for analysis.
        
        Args:
            since: ISO timestamp to filter from (optional)
        """
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        
        if since:
            rows = conn.execute(
                "SELECT * FROM routing_decisions WHERE created_at > ? ORDER BY created_at",
                (since,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM routing_decisions ORDER BY created_at"
            ).fetchall()
        
        conn.close()
        
        return [json.loads(row["decision_json"]) for row in rows]


# Module-level singleton
routing_engine = RoutingEngine()
