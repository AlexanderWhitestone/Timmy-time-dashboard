"""Swarm learner — outcome tracking and adaptive bid intelligence.

Records task outcomes (win/loss, success/failure) per agent and extracts
actionable metrics.  Persona nodes consult the learner to adjust bids
based on historical performance rather than using static strategies.

Inspired by feedback-loop learning: outcomes re-enter the system to
improve future decisions.  All data lives in swarm.db alongside the
existing bid_history and tasks tables.
"""

import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

DB_PATH = Path("data/swarm.db")

# Minimum outcomes before the learner starts adjusting bids
_MIN_OUTCOMES = 3

# Stop-words excluded from keyword extraction
_STOP_WORDS = frozenset({
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "it", "this", "that", "be", "as",
    "are", "was", "were", "been", "do", "does", "did", "will", "would",
    "can", "could", "should", "may", "might", "me", "my", "i", "we",
    "you", "your", "please", "task", "need", "want", "make", "get",
})

_WORD_RE = re.compile(r"[a-z]{3,}")


@dataclass
class AgentMetrics:
    """Computed performance metrics for a single agent."""
    agent_id: str
    total_bids: int = 0
    auctions_won: int = 0
    tasks_completed: int = 0
    tasks_failed: int = 0
    avg_winning_bid: float = 0.0
    win_rate: float = 0.0
    success_rate: float = 0.0
    keyword_wins: dict[str, int] = field(default_factory=dict)
    keyword_failures: dict[str, int] = field(default_factory=dict)


def _get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS task_outcomes (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id         TEXT NOT NULL,
            agent_id        TEXT NOT NULL,
            description     TEXT NOT NULL DEFAULT '',
            bid_sats        INTEGER NOT NULL DEFAULT 0,
            won_auction     INTEGER NOT NULL DEFAULT 0,
            task_succeeded  INTEGER,
            created_at      TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    conn.commit()
    return conn


def _extract_keywords(text: str) -> list[str]:
    """Pull meaningful words from a task description."""
    words = _WORD_RE.findall(text.lower())
    return [w for w in words if w not in _STOP_WORDS]


# ── Recording ────────────────────────────────────────────────────────────────

def record_outcome(
    task_id: str,
    agent_id: str,
    description: str,
    bid_sats: int,
    won_auction: bool,
    task_succeeded: Optional[bool] = None,
) -> None:
    """Record one agent's outcome for a task."""
    conn = _get_conn()
    conn.execute(
        """
        INSERT INTO task_outcomes
            (task_id, agent_id, description, bid_sats, won_auction, task_succeeded)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            task_id,
            agent_id,
            description,
            bid_sats,
            int(won_auction),
            int(task_succeeded) if task_succeeded is not None else None,
        ),
    )
    conn.commit()
    conn.close()


def record_task_result(task_id: str, agent_id: str, succeeded: bool) -> int:
    """Update the task_succeeded flag for an already-recorded winning outcome.

    Returns the number of rows updated.
    """
    conn = _get_conn()
    cursor = conn.execute(
        """
        UPDATE task_outcomes
        SET task_succeeded = ?
        WHERE task_id = ? AND agent_id = ? AND won_auction = 1
        """,
        (int(succeeded), task_id, agent_id),
    )
    conn.commit()
    updated = cursor.rowcount
    conn.close()
    return updated


# ── Metrics ──────────────────────────────────────────────────────────────────

def get_metrics(agent_id: str) -> AgentMetrics:
    """Compute performance metrics from stored outcomes."""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM task_outcomes WHERE agent_id = ?",
        (agent_id,),
    ).fetchall()
    conn.close()

    metrics = AgentMetrics(agent_id=agent_id)
    if not rows:
        return metrics

    metrics.total_bids = len(rows)
    winning_bids: list[int] = []

    for row in rows:
        won = bool(row["won_auction"])
        succeeded = row["task_succeeded"]
        keywords = _extract_keywords(row["description"])

        if won:
            metrics.auctions_won += 1
            winning_bids.append(row["bid_sats"])
            if succeeded == 1:
                metrics.tasks_completed += 1
                for kw in keywords:
                    metrics.keyword_wins[kw] = metrics.keyword_wins.get(kw, 0) + 1
            elif succeeded == 0:
                metrics.tasks_failed += 1
                for kw in keywords:
                    metrics.keyword_failures[kw] = metrics.keyword_failures.get(kw, 0) + 1

    metrics.win_rate = (
        metrics.auctions_won / metrics.total_bids if metrics.total_bids else 0.0
    )
    decided = metrics.tasks_completed + metrics.tasks_failed
    metrics.success_rate = (
        metrics.tasks_completed / decided if decided else 0.0
    )
    metrics.avg_winning_bid = (
        sum(winning_bids) / len(winning_bids) if winning_bids else 0.0
    )
    return metrics


def get_all_metrics() -> dict[str, AgentMetrics]:
    """Return metrics for every agent that has recorded outcomes."""
    conn = _get_conn()
    agent_ids = [
        row["agent_id"]
        for row in conn.execute(
            "SELECT DISTINCT agent_id FROM task_outcomes"
        ).fetchall()
    ]
    conn.close()
    return {aid: get_metrics(aid) for aid in agent_ids}


# ── Bid intelligence ─────────────────────────────────────────────────────────

def suggest_bid(agent_id: str, task_description: str, base_bid: int) -> int:
    """Adjust a base bid using learned performance data.

    Returns the base_bid unchanged until the agent has enough history
    (>= _MIN_OUTCOMES).  After that:

    - Win rate too high (>80%): nudge bid up — still win, earn more.
    - Win rate too low (<20%): nudge bid down — be more competitive.
    - Success rate low on won tasks: nudge bid up — avoid winning tasks
      this agent tends to fail.
    - Strong keyword match from past wins: nudge bid down — this agent
      is proven on similar work.
    """
    metrics = get_metrics(agent_id)
    if metrics.total_bids < _MIN_OUTCOMES:
        return base_bid

    factor = 1.0

    # Win-rate adjustment
    if metrics.win_rate > 0.8:
        factor *= 1.15          # bid higher, maximise revenue
    elif metrics.win_rate < 0.2:
        factor *= 0.85          # bid lower, be competitive

    # Success-rate adjustment (only when enough completed tasks)
    decided = metrics.tasks_completed + metrics.tasks_failed
    if decided >= 2:
        if metrics.success_rate < 0.5:
            factor *= 1.25      # avoid winning bad matches
        elif metrics.success_rate > 0.8:
            factor *= 0.90      # we're good at this, lean in

    # Keyword relevance from past wins
    task_keywords = _extract_keywords(task_description)
    if task_keywords:
        wins = sum(metrics.keyword_wins.get(kw, 0) for kw in task_keywords)
        fails = sum(metrics.keyword_failures.get(kw, 0) for kw in task_keywords)
        if wins > fails and wins >= 2:
            factor *= 0.90      # proven track record on these keywords
        elif fails > wins and fails >= 2:
            factor *= 1.15      # poor track record — back off

    adjusted = int(base_bid * factor)
    return max(1, adjusted)


def learned_keywords(agent_id: str) -> list[dict]:
    """Return keywords ranked by net wins (wins minus failures).

    Useful for discovering which task types an agent actually excels at,
    potentially different from its hardcoded preferred_keywords.
    """
    metrics = get_metrics(agent_id)
    all_kw = set(metrics.keyword_wins) | set(metrics.keyword_failures)
    results = []
    for kw in all_kw:
        wins = metrics.keyword_wins.get(kw, 0)
        fails = metrics.keyword_failures.get(kw, 0)
        results.append({"keyword": kw, "wins": wins, "failures": fails, "net": wins - fails})
    results.sort(key=lambda x: x["net"], reverse=True)
    return results
