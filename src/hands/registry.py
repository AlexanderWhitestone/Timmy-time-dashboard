"""Hand Registry — Load, validate, and index Hands from the hands directory.

The HandRegistry discovers all Hand packages in the hands/ directory,
loads their HAND.toml manifests, and maintains an index for fast lookup.

Usage:
    from hands.registry import HandRegistry
    
    registry = HandRegistry(hands_dir="hands/")
    await registry.load_all()
    
    oracle = registry.get_hand("oracle")
    all_hands = registry.list_hands()
    scheduled = registry.get_scheduled_hands()
"""

from __future__ import annotations

import logging
import sqlite3
import tomllib
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from hands.models import ApprovalGate, ApprovalRequest, ApprovalStatus, HandConfig, HandState, HandStatus, OutputConfig, ScheduleConfig

logger = logging.getLogger(__name__)


class HandRegistryError(Exception):
    """Base exception for HandRegistry errors."""
    pass


class HandNotFoundError(HandRegistryError):
    """Raised when a Hand is not found."""
    pass


class HandValidationError(HandRegistryError):
    """Raised when a Hand fails validation."""
    pass


class HandRegistry:
    """Registry for autonomous Hands.
    
    Discovers Hands from the filesystem, loads their configurations,
    and maintains a SQLite index for fast lookups.
    
    Attributes:
        hands_dir: Directory containing Hand packages
        db_path: SQLite database for indexing
        _hands: In-memory cache of loaded HandConfigs
        _states: Runtime state of each Hand
    """
    
    def __init__(
        self,
        hands_dir: str | Path = "hands/",
        db_path: str | Path = "data/hands.db",
    ) -> None:
        """Initialize HandRegistry.
        
        Args:
            hands_dir: Directory containing Hand subdirectories
            db_path: SQLite database path for indexing
        """
        self.hands_dir = Path(hands_dir)
        self.db_path = Path(db_path)
        self._hands: dict[str, HandConfig] = {}
        self._states: dict[str, HandState] = {}
        self._ensure_schema()
        logger.info("HandRegistry initialized (hands_dir=%s)", self.hands_dir)
    
    def _get_conn(self) -> sqlite3.Connection:
        """Get database connection."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn
    
    def _ensure_schema(self) -> None:
        """Create database tables if they don't exist."""
        with self._get_conn() as conn:
            # Hands index
            conn.execute("""
                CREATE TABLE IF NOT EXISTS hands (
                    name TEXT PRIMARY KEY,
                    config_json TEXT NOT NULL,
                    enabled INTEGER DEFAULT 1,
                    loaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Hand execution history
            conn.execute("""
                CREATE TABLE IF NOT EXISTS hand_executions (
                    id TEXT PRIMARY KEY,
                    hand_name TEXT NOT NULL,
                    trigger TEXT NOT NULL,
                    started_at TIMESTAMP NOT NULL,
                    completed_at TIMESTAMP,
                    outcome TEXT NOT NULL,
                    output TEXT,
                    error TEXT,
                    approval_id TEXT
                )
            """)
            
            # Approval queue
            conn.execute("""
                CREATE TABLE IF NOT EXISTS approval_queue (
                    id TEXT PRIMARY KEY,
                    hand_name TEXT NOT NULL,
                    action TEXT NOT NULL,
                    description TEXT NOT NULL,
                    context_json TEXT,
                    status TEXT DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP,
                    resolved_at TIMESTAMP,
                    resolved_by TEXT
                )
            """)
            
            conn.commit()
    
    async def load_all(self) -> dict[str, HandConfig]:
        """Load all Hands from the hands directory.
        
        Returns:
            Dict mapping hand names to HandConfigs
        """
        if not self.hands_dir.exists():
            logger.warning("Hands directory does not exist: %s", self.hands_dir)
            return {}
        
        loaded = {}
        
        for hand_dir in self.hands_dir.iterdir():
            if not hand_dir.is_dir():
                continue
            
            try:
                hand = self._load_hand_from_dir(hand_dir)
                if hand:
                    loaded[hand.name] = hand
                    self._hands[hand.name] = hand
                    
                    # Initialize state if not exists
                    if hand.name not in self._states:
                        self._states[hand.name] = HandState(name=hand.name)
                    
                    # Store in database
                    self._store_hand(conn=None, hand=hand)
                    
                    logger.info("Loaded Hand: %s (%s)", hand.name, hand.description[:50])
                    
            except Exception as e:
                logger.error("Failed to load Hand from %s: %s", hand_dir, e)
        
        logger.info("Loaded %d Hands", len(loaded))
        return loaded
    
    def _load_hand_from_dir(self, hand_dir: Path) -> Optional[HandConfig]:
        """Load a single Hand from its directory.
        
        Args:
            hand_dir: Directory containing HAND.toml
            
        Returns:
            HandConfig or None if invalid
        """
        manifest_path = hand_dir / "HAND.toml"
        
        if not manifest_path.exists():
            logger.debug("No HAND.toml in %s", hand_dir)
            return None
        
        # Parse TOML
        try:
            with open(manifest_path, "rb") as f:
                data = tomllib.load(f)
        except Exception as e:
            raise HandValidationError(f"Invalid HAND.toml: {e}")
        
        # Extract hand section
        hand_data = data.get("hand", {})
        if not hand_data:
            raise HandValidationError("Missing [hand] section in HAND.toml")
        
        # Build HandConfig
        config = HandConfig(
            name=hand_data.get("name", hand_dir.name),
            description=hand_data.get("description", ""),
            enabled=hand_data.get("enabled", True),
            version=hand_data.get("version", "1.0.0"),
            author=hand_data.get("author"),
            hand_dir=hand_dir,
        )
        
        # Parse schedule
        if "schedule" in hand_data:
            schedule_data = hand_data["schedule"]
            if isinstance(schedule_data, str):
                # Simple cron string
                config.schedule = ScheduleConfig(cron=schedule_data)
            elif isinstance(schedule_data, dict):
                config.schedule = ScheduleConfig(**schedule_data)
        
        # Parse tools
        tools_data = data.get("tools", {})
        config.tools_required = tools_data.get("required", [])
        config.tools_optional = tools_data.get("optional", [])
        
        # Parse approval gates
        gates_data = data.get("approval_gates", {})
        for action, gate_data in gates_data.items():
            if isinstance(gate_data, dict):
                config.approval_gates.append(ApprovalGate(
                    action=gate_data.get("action", action),
                    description=gate_data.get("description", ""),
                    auto_approve_after=gate_data.get("auto_approve_after"),
                ))
        
        # Parse output config
        output_data = data.get("output", {})
        config.output = OutputConfig(**output_data)
        
        return config
    
    def _store_hand(self, conn: Optional[sqlite3.Connection], hand: HandConfig) -> None:
        """Store hand config in database."""
        import json
        
        if conn is None:
            with self._get_conn() as conn:
                self._store_hand(conn, hand)
                return
        
        conn.execute(
            """
            INSERT OR REPLACE INTO hands (name, config_json, enabled)
            VALUES (?, ?, ?)
            """,
            (hand.name, hand.json(), 1 if hand.enabled else 0),
        )
        conn.commit()
    
    def get_hand(self, name: str) -> HandConfig:
        """Get a Hand by name.
        
        Args:
            name: Hand name
            
        Returns:
            HandConfig
            
        Raises:
            HandNotFoundError: If Hand doesn't exist
        """
        if name not in self._hands:
            raise HandNotFoundError(f"Hand not found: {name}")
        return self._hands[name]
    
    def list_hands(self) -> list[HandConfig]:
        """List all loaded Hands.
        
        Returns:
            List of HandConfigs
        """
        return list(self._hands.values())
    
    def get_scheduled_hands(self) -> list[HandConfig]:
        """Get all Hands with schedule configuration.
        
        Returns:
            List of HandConfigs with schedules
        """
        return [h for h in self._hands.values() if h.schedule is not None and h.enabled]
    
    def get_enabled_hands(self) -> list[HandConfig]:
        """Get all enabled Hands.
        
        Returns:
            List of enabled HandConfigs
        """
        return [h for h in self._hands.values() if h.enabled]
    
    def get_state(self, name: str) -> HandState:
        """Get runtime state of a Hand.
        
        Args:
            name: Hand name
            
        Returns:
            HandState
        """
        if name not in self._states:
            self._states[name] = HandState(name=name)
        return self._states[name]
    
    def update_state(self, name: str, **kwargs) -> None:
        """Update Hand state.
        
        Args:
            name: Hand name
            **kwargs: State fields to update
        """
        state = self.get_state(name)
        for key, value in kwargs.items():
            if hasattr(state, key):
                setattr(state, key, value)
    
    async def log_execution(
        self,
        hand_name: str,
        trigger: str,
        outcome: str,
        output: str = "",
        error: Optional[str] = None,
        approval_id: Optional[str] = None,
    ) -> str:
        """Log a Hand execution.
        
        Args:
            hand_name: Name of the Hand
            trigger: Trigger type
            outcome: Execution outcome
            output: Execution output
            error: Error message if failed
            approval_id: Associated approval ID
            
        Returns:
            Execution ID
        """
        execution_id = str(uuid.uuid4())
        
        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT INTO hand_executions
                (id, hand_name, trigger, started_at, completed_at, outcome, output, error, approval_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    execution_id,
                    hand_name,
                    trigger,
                    datetime.now(timezone.utc).isoformat(),
                    datetime.now(timezone.utc).isoformat(),
                    outcome,
                    output,
                    error,
                    approval_id,
                ),
            )
            conn.commit()
        
        return execution_id
    
    async def create_approval(
        self,
        hand_name: str,
        action: str,
        description: str,
        context: dict,
        expires_after: Optional[int] = None,
    ) -> ApprovalRequest:
        """Create an approval request.
        
        Args:
            hand_name: Hand requesting approval
            action: Action to approve
            description: Human-readable description
            context: Additional context
            expires_after: Seconds until expiration
            
        Returns:
            ApprovalRequest
        """
        approval_id = str(uuid.uuid4())
        
        created_at = datetime.now(timezone.utc)
        expires_at = None
        if expires_after:
            from datetime import timedelta
            expires_at = created_at + timedelta(seconds=expires_after)
        
        request = ApprovalRequest(
            id=approval_id,
            hand_name=hand_name,
            action=action,
            description=description,
            context=context,
            created_at=created_at,
            expires_at=expires_at,
        )
        
        # Store in database
        import json
        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT INTO approval_queue
                (id, hand_name, action, description, context_json, status, created_at, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    request.id,
                    request.hand_name,
                    request.action,
                    request.description,
                    json.dumps(request.context),
                    request.status.value,
                    request.created_at.isoformat(),
                    request.expires_at.isoformat() if request.expires_at else None,
                ),
            )
            conn.commit()
        
        return request
    
    async def get_pending_approvals(self) -> list[ApprovalRequest]:
        """Get all pending approval requests.
        
        Returns:
            List of pending ApprovalRequests
        """
        import json
        
        with self._get_conn() as conn:
            rows = conn.execute(
                """
                SELECT * FROM approval_queue
                WHERE status = 'pending'
                ORDER BY created_at DESC
                """
            ).fetchall()
        
        requests = []
        for row in rows:
            requests.append(ApprovalRequest(
                id=row["id"],
                hand_name=row["hand_name"],
                action=row["action"],
                description=row["description"],
                context=json.loads(row["context_json"] or "{}"),
                status=ApprovalStatus(row["status"]),
                created_at=datetime.fromisoformat(row["created_at"]),
                expires_at=datetime.fromisoformat(row["expires_at"]) if row["expires_at"] else None,
            ))
        
        return requests
    
    async def resolve_approval(
        self,
        approval_id: str,
        approved: bool,
        resolved_by: Optional[str] = None,
    ) -> bool:
        """Resolve an approval request.
        
        Args:
            approval_id: ID of the approval request
            approved: True to approve, False to reject
            resolved_by: Who resolved the request
            
        Returns:
            True if resolved successfully
        """
        status = ApprovalStatus.APPROVED if approved else ApprovalStatus.REJECTED
        resolved_at = datetime.now(timezone.utc)
        
        with self._get_conn() as conn:
            cursor = conn.execute(
                """
                UPDATE approval_queue
                SET status = ?, resolved_at = ?, resolved_by = ?
                WHERE id = ? AND status = 'pending'
                """,
                (status.value, resolved_at.isoformat(), resolved_by, approval_id),
            )
            conn.commit()
            
            return cursor.rowcount > 0
    
    async def get_recent_executions(
        self,
        hand_name: Optional[str] = None,
        limit: int = 50,
    ) -> list[dict]:
        """Get recent Hand executions.
        
        Args:
            hand_name: Filter by Hand name
            limit: Maximum results
            
        Returns:
            List of execution records
        """
        with self._get_conn() as conn:
            if hand_name:
                rows = conn.execute(
                    """
                    SELECT * FROM hand_executions
                    WHERE hand_name = ?
                    ORDER BY started_at DESC
                    LIMIT ?
                    """,
                    (hand_name, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM hand_executions
                    ORDER BY started_at DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
        
        return [dict(row) for row in rows]
