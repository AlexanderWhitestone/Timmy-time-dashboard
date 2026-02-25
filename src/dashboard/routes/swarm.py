"""Swarm dashboard routes — /swarm/* endpoints.

Provides REST endpoints for managing the swarm: listing agents,
spawning sub-agents, posting tasks, and viewing auction results.
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from swarm import learner as swarm_learner
from swarm import registry
from swarm.coordinator import coordinator
from swarm.tasks import TaskStatus, update_task

router = APIRouter(prefix="/swarm", tags=["swarm"])
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


@router.get("")
async def swarm_status():
    """Return the current swarm status summary."""
    return coordinator.status()


@router.get("/live", response_class=HTMLResponse)
async def swarm_live_page(request: Request):
    """Render the live swarm dashboard page."""
    return templates.TemplateResponse(
        request, "swarm_live.html", {"page_title": "Swarm Live"}
    )


@router.get("/agents")
async def list_swarm_agents():
    """List all registered swarm agents."""
    agents = coordinator.list_swarm_agents()
    return {
        "agents": [
            {
                "id": a.id,
                "name": a.name,
                "status": a.status,
                "capabilities": a.capabilities,
                "last_seen": a.last_seen,
            }
            for a in agents
        ]
    }


@router.post("/spawn")
async def spawn_agent(name: str = Form(...)):
    """Spawn a new sub-agent in the swarm."""
    result = coordinator.spawn_agent(name)
    return result


@router.delete("/agents/{agent_id}")
async def stop_agent(agent_id: str):
    """Stop and unregister a swarm agent."""
    success = coordinator.stop_agent(agent_id)
    return {"stopped": success, "agent_id": agent_id}


@router.get("/tasks")
async def list_tasks(status: Optional[str] = None):
    """List swarm tasks, optionally filtered by status."""
    task_status = TaskStatus(status) if status else None
    tasks = coordinator.list_tasks(task_status)
    return {
        "tasks": [
            {
                "id": t.id,
                "description": t.description,
                "status": t.status.value,
                "assigned_agent": t.assigned_agent,
                "result": t.result,
                "created_at": t.created_at,
                "completed_at": t.completed_at,
            }
            for t in tasks
        ]
    }


@router.post("/tasks")
async def post_task(description: str = Form(...)):
    """Post a new task to the swarm for bidding."""
    task = coordinator.post_task(description)
    return {
        "task_id": task.id,
        "description": task.description,
        "status": task.status.value,
    }


@router.post("/tasks/auction")
async def post_task_and_auction(description: str = Form(...)):
    """Post a task and immediately run an auction to assign it."""
    task = coordinator.post_task(description)
    winner = await coordinator.run_auction_and_assign(task.id)
    updated = coordinator.get_task(task.id)
    return {
        "task_id": task.id,
        "description": task.description,
        "status": updated.status.value if updated else task.status.value,
        "assigned_agent": updated.assigned_agent if updated else None,
        "winning_bid": winner.bid_sats if winner else None,
    }


@router.get("/tasks/panel", response_class=HTMLResponse)
async def task_create_panel(request: Request, agent_id: Optional[str] = None):
    """Task creation panel, optionally pre-selecting an agent."""
    agents = coordinator.list_swarm_agents()
    return templates.TemplateResponse(
        request,
        "partials/task_assign_panel.html",
        {"agents": agents, "preselected_agent_id": agent_id},
    )


@router.post("/tasks/direct", response_class=HTMLResponse)
async def direct_assign_task(
    request: Request,
    description: str = Form(...),
    agent_id: Optional[str] = Form(None),
):
    """Create a task: assign directly if agent_id given, else open auction."""
    timestamp = datetime.now(timezone.utc).strftime("%H:%M:%S")

    if agent_id:
        agent = registry.get_agent(agent_id)
        task = coordinator.post_task(description)
        coordinator.auctions.open_auction(task.id)
        coordinator.auctions.submit_bid(task.id, agent_id, 1)
        coordinator.auctions.close_auction(task.id)
        update_task(task.id, status=TaskStatus.ASSIGNED, assigned_agent=agent_id)
        registry.update_status(agent_id, "busy")
        agent_name = agent.name if agent else agent_id
    else:
        task = coordinator.post_task(description)
        winner = await coordinator.run_auction_and_assign(task.id)
        task = coordinator.get_task(task.id)
        agent_name = winner.agent_id if winner else "unassigned"

    return templates.TemplateResponse(
        request,
        "partials/task_result.html",
        {
            "task": task,
            "agent_name": agent_name,
            "timestamp": timestamp,
        },
    )


@router.get("/tasks/{task_id}")
async def get_task(task_id: str):
    """Get details for a specific task."""
    task = coordinator.get_task(task_id)
    if task is None:
        return {"error": "Task not found"}
    return {
        "id": task.id,
        "description": task.description,
        "status": task.status.value,
        "assigned_agent": task.assigned_agent,
        "result": task.result,
        "created_at": task.created_at,
        "completed_at": task.completed_at,
    }


@router.post("/tasks/{task_id}/complete")
async def complete_task(task_id: str, result: str = Form(...)):
    """Mark a task completed — called by agent containers."""
    task = coordinator.complete_task(task_id, result)
    if task is None:
        raise HTTPException(404, "Task not found")
    return {"task_id": task_id, "status": task.status.value}


@router.post("/tasks/{task_id}/fail")
async def fail_task(task_id: str, reason: str = Form("")):
    """Mark a task failed — feeds failure data into the learner."""
    task = coordinator.fail_task(task_id, reason)
    if task is None:
        raise HTTPException(404, "Task not found")
    return {"task_id": task_id, "status": task.status.value}


# ── Learning insights ────────────────────────────────────────────────────────

@router.get("/insights")
async def swarm_insights():
    """Return learned performance metrics for all agents."""
    all_metrics = swarm_learner.get_all_metrics()
    return {
        "agents": {
            aid: {
                "total_bids": m.total_bids,
                "auctions_won": m.auctions_won,
                "tasks_completed": m.tasks_completed,
                "tasks_failed": m.tasks_failed,
                "win_rate": round(m.win_rate, 3),
                "success_rate": round(m.success_rate, 3),
                "avg_winning_bid": round(m.avg_winning_bid, 1),
                "top_keywords": swarm_learner.learned_keywords(aid)[:10],
            }
            for aid, m in all_metrics.items()
        }
    }


@router.get("/insights/{agent_id}")
async def agent_insights(agent_id: str):
    """Return learned performance metrics for a specific agent."""
    m = swarm_learner.get_metrics(agent_id)
    return {
        "agent_id": agent_id,
        "total_bids": m.total_bids,
        "auctions_won": m.auctions_won,
        "tasks_completed": m.tasks_completed,
        "tasks_failed": m.tasks_failed,
        "win_rate": round(m.win_rate, 3),
        "success_rate": round(m.success_rate, 3),
        "avg_winning_bid": round(m.avg_winning_bid, 1),
        "learned_keywords": swarm_learner.learned_keywords(agent_id),
    }


# ── UI endpoints (return HTML partials for HTMX) ─────────────────────────────

@router.get("/agents/sidebar", response_class=HTMLResponse)
async def agents_sidebar(request: Request):
    """Sidebar partial: all registered agents."""
    agents = coordinator.list_swarm_agents()
    return templates.TemplateResponse(
        request, "partials/swarm_agents_sidebar.html", {"agents": agents}
    )


@router.get("/agents/{agent_id}/panel", response_class=HTMLResponse)
async def agent_panel(agent_id: str, request: Request):
    """Main-panel partial: agent detail + chat + task history."""
    agent = registry.get_agent(agent_id)
    if agent is None:
        raise HTTPException(404, "Agent not found")
    all_tasks = coordinator.list_tasks()
    agent_tasks = [t for t in all_tasks if t.assigned_agent == agent_id][-10:]
    return templates.TemplateResponse(
        request,
        "partials/agent_panel.html",
        {"agent": agent, "tasks": agent_tasks},
    )


@router.post("/agents/{agent_id}/message", response_class=HTMLResponse)
async def message_agent(agent_id: str, request: Request, message: str = Form(...)):
    """Send a direct message to an agent (creates + assigns a task)."""
    agent = registry.get_agent(agent_id)
    if agent is None:
        raise HTTPException(404, "Agent not found")

    timestamp = datetime.now(timezone.utc).strftime("%H:%M:%S")

    # Timmy: route through his AI backend
    if agent_id == "timmy":
        result_text = error_text = None
        try:
            from timmy.agent import create_timmy
            run = create_timmy().run(message, stream=False)
            result_text = run.content if hasattr(run, "content") else str(run)
        except Exception as exc:
            error_text = f"Timmy is offline: {exc}"
        return templates.TemplateResponse(
            request,
            "partials/agent_chat_msg.html",
            {
                "message": message,
                "agent": agent,
                "response": result_text,
                "error": error_text,
                "timestamp": timestamp,
                "task_id": None,
            },
        )

    # Other agents: create a task and assign directly
    task = coordinator.post_task(message)
    coordinator.auctions.open_auction(task.id)
    coordinator.auctions.submit_bid(task.id, agent_id, 1)
    coordinator.auctions.close_auction(task.id)
    update_task(task.id, status=TaskStatus.ASSIGNED, assigned_agent=agent_id)
    registry.update_status(agent_id, "busy")

    return templates.TemplateResponse(
        request,
        "partials/agent_chat_msg.html",
        {
            "message": message,
            "agent": agent,
            "response": None,
            "error": None,
            "timestamp": timestamp,
            "task_id": task.id,
        },
    )


