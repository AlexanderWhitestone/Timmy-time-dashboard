"""Internal swarm HTTP API — for Docker container agents.

Container agents can't use the in-memory SwarmComms channel, so they poll
these lightweight endpoints to participate in the auction system.

Routes
------
GET  /internal/tasks
    Returns all tasks currently in BIDDING status — the set an agent
    can submit bids for.

POST /internal/bids
    Accepts a bid from a container agent and feeds it into the in-memory
    AuctionManager.  The coordinator then closes auctions and assigns
    winners exactly as it does for in-process agents.

These endpoints are intentionally unauthenticated because they are only
reachable inside the Docker swarm-net bridge network.  Do not expose them
through a reverse-proxy to the public internet.
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from swarm.coordinator import coordinator
from swarm.tasks import TaskStatus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/internal", tags=["internal"])


# ── Request / response models ─────────────────────────────────────────────────

class BidRequest(BaseModel):
    task_id: str
    agent_id: str
    bid_sats: int
    capabilities: Optional[str] = ""


class BidResponse(BaseModel):
    accepted: bool
    task_id: str
    agent_id: str
    message: str


class TaskSummary(BaseModel):
    task_id: str
    description: str
    status: str


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/tasks", response_model=list[TaskSummary])
def list_biddable_tasks():
    """Return all tasks currently open for bidding.

    Container agents should poll this endpoint and submit bids for any
    tasks they are capable of handling.
    """
    tasks = coordinator.list_tasks(status=TaskStatus.BIDDING)
    return [
        TaskSummary(
            task_id=t.id,
            description=t.description,
            status=t.status.value,
        )
        for t in tasks
    ]


@router.post("/bids", response_model=BidResponse)
def submit_bid(bid: BidRequest):
    """Accept a bid from a container agent.

    The bid is injected directly into the in-memory AuctionManager.
    If no auction is open for the task (e.g. it already closed), the
    bid is rejected gracefully — the agent should just move on.
    """
    if bid.bid_sats <= 0:
        raise HTTPException(status_code=422, detail="bid_sats must be > 0")

    accepted = coordinator.auctions.submit_bid(
        task_id=bid.task_id,
        agent_id=bid.agent_id,
        bid_sats=bid.bid_sats,
    )

    if accepted:
        # Persist bid in stats table for marketplace analytics
        from swarm import stats as swarm_stats
        swarm_stats.record_bid(bid.task_id, bid.agent_id, bid.bid_sats, won=False)
        logger.info(
            "Docker agent %s bid %d sats on task %s",
            bid.agent_id, bid.bid_sats, bid.task_id,
        )
        return BidResponse(
            accepted=True,
            task_id=bid.task_id,
            agent_id=bid.agent_id,
            message="Bid accepted.",
        )

    return BidResponse(
        accepted=False,
        task_id=bid.task_id,
        agent_id=bid.agent_id,
        message="No open auction for this task — it may have already closed.",
    )
