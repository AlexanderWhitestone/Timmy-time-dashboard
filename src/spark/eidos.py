"""EIDOS cognitive loop — prediction, evaluation, and learning.

Implements the core Spark learning cycle:
1. PREDICT — Before a task is assigned, predict the outcome
2. OBSERVE — Watch what actually happens
3. EVALUATE — Compare prediction vs reality
4. LEARN — Update internal models based on accuracy

All predictions and evaluations are stored in SQLite for
transparency and audit.  The loop runs passively, recording
predictions when tasks are posted and evaluating them when
tasks complete.
"""

import json
import logging
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

DB_PATH = Path("data/spark.db")


@dataclass
class Prediction:
    """A prediction made by the EIDOS loop."""
    id: str
    task_id: str
    prediction_type: str     # outcome, best_agent, bid_range
    predicted_value: str     # JSON-encoded prediction
    actual_value: Optional[str]   # JSON-encoded actual (filled on evaluation)
    accuracy: Optional[float]     # 0.0–1.0 (filled on evaluation)
    created_at: str
    evaluated_at: Optional[str]


def _get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS spark_predictions (
            id               TEXT PRIMARY KEY,
            task_id          TEXT NOT NULL,
            prediction_type  TEXT NOT NULL,
            predicted_value  TEXT NOT NULL,
            actual_value     TEXT,
            accuracy         REAL,
            created_at       TEXT NOT NULL,
            evaluated_at     TEXT
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_pred_task ON spark_predictions(task_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_pred_type ON spark_predictions(prediction_type)"
    )
    conn.commit()
    return conn


# ── Prediction phase ────────────────────────────────────────────────────────

def predict_task_outcome(
    task_id: str,
    task_description: str,
    candidate_agents: list[str],
    agent_history: Optional[dict] = None,
) -> dict:
    """Predict the outcome of a task before it's assigned.

    Returns a prediction dict with:
    - likely_winner: agent_id most likely to win the auction
    - success_probability: 0.0–1.0 chance the task succeeds
    - estimated_bid_range: (low, high) sats range
    """
    # Default prediction when no history exists
    prediction = {
        "likely_winner": candidate_agents[0] if candidate_agents else None,
        "success_probability": 0.7,
        "estimated_bid_range": [20, 80],
        "reasoning": "baseline prediction (no history)",
    }

    if agent_history:
        # Adjust based on historical success rates
        best_agent = None
        best_rate = 0.0
        for aid, metrics in agent_history.items():
            if aid not in candidate_agents:
                continue
            rate = metrics.get("success_rate", 0.0)
            if rate > best_rate:
                best_rate = rate
                best_agent = aid

        if best_agent:
            prediction["likely_winner"] = best_agent
            prediction["success_probability"] = round(
                min(1.0, 0.5 + best_rate * 0.4), 2
            )
            prediction["reasoning"] = (
                f"agent {best_agent[:8]} has {best_rate:.0%} success rate"
            )

        # Adjust bid range from history
        all_bids = []
        for metrics in agent_history.values():
            avg = metrics.get("avg_winning_bid", 0)
            if avg > 0:
                all_bids.append(avg)
        if all_bids:
            prediction["estimated_bid_range"] = [
                max(1, int(min(all_bids) * 0.8)),
                int(max(all_bids) * 1.2),
            ]

    # Store prediction
    pred_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    conn = _get_conn()
    conn.execute(
        """
        INSERT INTO spark_predictions
            (id, task_id, prediction_type, predicted_value, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (pred_id, task_id, "outcome", json.dumps(prediction), now),
    )
    conn.commit()
    conn.close()

    prediction["prediction_id"] = pred_id
    return prediction


# ── Evaluation phase ────────────────────────────────────────────────────────

def evaluate_prediction(
    task_id: str,
    actual_winner: Optional[str],
    task_succeeded: bool,
    winning_bid: Optional[int] = None,
) -> Optional[dict]:
    """Evaluate a stored prediction against actual outcomes.

    Returns the evaluation result or None if no prediction exists.
    """
    conn = _get_conn()
    row = conn.execute(
        """
        SELECT * FROM spark_predictions
        WHERE task_id = ? AND prediction_type = 'outcome' AND evaluated_at IS NULL
        ORDER BY created_at DESC LIMIT 1
        """,
        (task_id,),
    ).fetchone()

    if not row:
        conn.close()
        return None

    predicted = json.loads(row["predicted_value"])
    actual = {
        "winner": actual_winner,
        "succeeded": task_succeeded,
        "winning_bid": winning_bid,
    }

    # Calculate accuracy
    accuracy = _compute_accuracy(predicted, actual)
    now = datetime.now(timezone.utc).isoformat()

    conn.execute(
        """
        UPDATE spark_predictions
        SET actual_value = ?, accuracy = ?, evaluated_at = ?
        WHERE id = ?
        """,
        (json.dumps(actual), accuracy, now, row["id"]),
    )
    conn.commit()
    conn.close()

    return {
        "prediction_id": row["id"],
        "predicted": predicted,
        "actual": actual,
        "accuracy": accuracy,
    }


def _compute_accuracy(predicted: dict, actual: dict) -> float:
    """Score prediction accuracy from 0.0–1.0.

    Components:
    - Winner prediction: 0.4 weight (correct = 1.0, wrong = 0.0)
    - Success prediction: 0.4 weight (how close)
    - Bid range: 0.2 weight (was actual bid in predicted range)
    """
    score = 0.0
    weights = 0.0

    # Winner accuracy
    pred_winner = predicted.get("likely_winner")
    actual_winner = actual.get("winner")
    if pred_winner and actual_winner:
        score += 0.4 * (1.0 if pred_winner == actual_winner else 0.0)
        weights += 0.4

    # Success probability accuracy
    pred_success = predicted.get("success_probability", 0.5)
    actual_success = 1.0 if actual.get("succeeded") else 0.0
    success_error = abs(pred_success - actual_success)
    score += 0.4 * (1.0 - success_error)
    weights += 0.4

    # Bid range accuracy
    bid_range = predicted.get("estimated_bid_range", [20, 80])
    actual_bid = actual.get("winning_bid")
    if actual_bid is not None and len(bid_range) == 2:
        low, high = bid_range
        if low <= actual_bid <= high:
            score += 0.2
        else:
            # Partial credit: how far outside the range
            distance = min(abs(actual_bid - low), abs(actual_bid - high))
            range_size = max(1, high - low)
            score += 0.2 * max(0, 1.0 - distance / range_size)
        weights += 0.2

    return round(score / max(weights, 0.01), 2)


# ── Query helpers ──────────────────────────────────────────────────────────

def get_predictions(
    task_id: Optional[str] = None,
    evaluated_only: bool = False,
    limit: int = 50,
) -> list[Prediction]:
    """Query stored predictions."""
    conn = _get_conn()
    query = "SELECT * FROM spark_predictions WHERE 1=1"
    params: list = []

    if task_id:
        query += " AND task_id = ?"
        params.append(task_id)
    if evaluated_only:
        query += " AND evaluated_at IS NOT NULL"

    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)

    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [
        Prediction(
            id=r["id"],
            task_id=r["task_id"],
            prediction_type=r["prediction_type"],
            predicted_value=r["predicted_value"],
            actual_value=r["actual_value"],
            accuracy=r["accuracy"],
            created_at=r["created_at"],
            evaluated_at=r["evaluated_at"],
        )
        for r in rows
    ]


def get_accuracy_stats() -> dict:
    """Return aggregate accuracy statistics for the EIDOS loop."""
    conn = _get_conn()
    row = conn.execute(
        """
        SELECT
            COUNT(*)                          AS total_predictions,
            COUNT(evaluated_at)               AS evaluated,
            AVG(CASE WHEN accuracy IS NOT NULL THEN accuracy END) AS avg_accuracy,
            MIN(CASE WHEN accuracy IS NOT NULL THEN accuracy END) AS min_accuracy,
            MAX(CASE WHEN accuracy IS NOT NULL THEN accuracy END) AS max_accuracy
        FROM spark_predictions
        """
    ).fetchone()
    conn.close()

    return {
        "total_predictions": row["total_predictions"] or 0,
        "evaluated": row["evaluated"] or 0,
        "pending": (row["total_predictions"] or 0) - (row["evaluated"] or 0),
        "avg_accuracy": round(row["avg_accuracy"] or 0.0, 2),
        "min_accuracy": round(row["min_accuracy"] or 0.0, 2),
        "max_accuracy": round(row["max_accuracy"] or 0.0, 2),
    }
