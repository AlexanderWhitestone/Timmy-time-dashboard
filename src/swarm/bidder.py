"""15-second auction system for swarm task assignment with SQLite persistence.

When a task is posted, agents have 15 seconds to submit bids (in sats).
The lowest bid wins.  If no bids arrive, the task remains unassigned.
Auctions and bids are persisted in the swarm database to survive restarts.
"""

import asyncio
import logging
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

AUCTION_DURATION_SECONDS = 15
DB_PATH = Path("data/swarm.db")


@dataclass
class Bid:
    agent_id: str
    bid_sats: int
    task_id: str


@dataclass
class Auction:
    task_id: str
    bids: List[Bid] = field(default_factory=list)
    closed: bool = False
    winner: Optional[Bid] = None

    def submit(self, agent_id: str, bid_sats: int) -> bool:
        """Submit a bid.  Returns False if the auction is already closed."""
        if self.closed:
            return False
        self.bids.append(Bid(agent_id=agent_id, bid_sats=bid_sats, task_id=self.task_id))
        return True

    def close(self) -> Optional[Bid]:
        """Close the auction and determine the winner (lowest bid)."""
        self.closed = True
        if not self.bids:
            logger.info("Auction %s: no bids received", self.task_id)
            return None
        self.winner = min(self.bids, key=lambda b: b.bid_sats)
        logger.info(
            "Auction %s: winner is %s at %d sats",
            self.task_id, self.winner.agent_id, self.winner.bid_sats,
        )
        return self.winner


def init_db(db_path: Path) -> None:
    """Initialize the auctions and bids tables."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS auctions (
            task_id TEXT PRIMARY KEY,
            closed INTEGER NOT NULL DEFAULT 0,
            winner_agent_id TEXT,
            winner_bid_sats INTEGER
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS bids (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL,
            agent_id TEXT NOT NULL,
            bid_sats INTEGER NOT NULL,
            FOREIGN KEY (task_id) REFERENCES auctions (task_id)
        )
        """
    )
    conn.commit()
    conn.close()


class AuctionManager:
    """Manages concurrent auctions for multiple tasks with persistence."""

    def __init__(self) -> None:
        pass

    def _get_conn(self) -> sqlite3.Connection:
        init_db(DB_PATH)
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        return conn

    def open_auction(self, task_id: str) -> Auction:
        """Open a new auction in the persistent store."""
        conn = self._get_conn()
        conn.execute(
            "INSERT OR IGNORE INTO auctions (task_id, closed) VALUES (?, 0)",
            (task_id,),
        )
        conn.commit()
        conn.close()
        logger.info("Auction opened for task %s", task_id)
        return self.get_auction(task_id)

    def get_auction(self, task_id: str) -> Optional[Auction]:
        """Retrieve an auction and its bids from the persistent store."""
        conn = self._get_conn()
        row = conn.execute("SELECT * FROM auctions WHERE task_id = ?", (task_id,)).fetchone()
        if not row:
            conn.close()
            return None

        bid_rows = conn.execute("SELECT agent_id, bid_sats FROM bids WHERE task_id = ?", (task_id,)).fetchall()
        conn.close()

        bids = [Bid(agent_id=r["agent_id"], bid_sats=r["bid_sats"], task_id=task_id) for r in bid_rows]
        winner = None
        if row["winner_agent_id"]:
            winner = Bid(agent_id=row["winner_agent_id"], bid_sats=row["winner_bid_sats"], task_id=task_id)

        return Auction(
            task_id=task_id,
            bids=bids,
            closed=bool(row["closed"]),
            winner=winner,
        )

    def submit_bid(self, task_id: str, agent_id: str, bid_sats: int) -> bool:
        """Submit a bid to the persistent store."""
        auction = self.get_auction(task_id)
        if auction is None or auction.closed:
            logger.warning("No open auction found for task %s", task_id)
            return False

        conn = self._get_conn()
        conn.execute(
            "INSERT INTO bids (task_id, agent_id, bid_sats) VALUES (?, ?, ?)",
            (task_id, agent_id, bid_sats),
        )
        conn.commit()
        conn.close()
        return True

    def close_auction(self, task_id: str) -> Optional[Bid]:
        """Close an auction in the persistent store and determine the winner."""
        auction = self.get_auction(task_id)
        if auction is None:
            return None

        winner = auction.close()
        conn = self._get_conn()
        if winner:
            conn.execute(
                "UPDATE auctions SET closed = 1, winner_agent_id = ?, winner_bid_sats = ? WHERE task_id = ?",
                (winner.agent_id, winner.bid_sats, task_id),
            )
        else:
            conn.execute("UPDATE auctions SET closed = 1 WHERE task_id = ?", (task_id,))
        conn.commit()
        conn.close()
        return winner

    async def run_auction(self, task_id: str) -> Optional[Bid]:
        """Open an auction, wait the bidding period, then close and return winner."""
        self.open_auction(task_id)
        await asyncio.sleep(AUCTION_DURATION_SECONDS)
        return self.close_auction(task_id)

    @property
    def active_auctions(self) -> List[str]:
        """List all currently open task IDs."""
        conn = self._get_conn()
        rows = conn.execute("SELECT task_id FROM auctions WHERE closed = 0").fetchall()
        conn.close()
        return [r["task_id"] for r in rows]
