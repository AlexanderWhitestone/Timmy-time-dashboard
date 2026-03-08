"""Agentic loop — multi-step task execution with progress tracking.

Provides `run_agentic_loop()`, the engine behind the `plan_and_execute` tool.
When the model recognises a task needs 3+ sequential steps, it calls
`plan_and_execute(task)` which spawns this loop in the background.

Flow:
  1. Planning — ask the model to break the task into numbered steps
  2. Execution — run each step sequentially, feeding results forward
  3. Adaptation — on failure, ask the model to adapt the plan
  4. Summary — ask the model to summarise what was accomplished

Progress is broadcast via WebSocket so the dashboard can show live updates.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Callable, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class AgenticStep:
    """Result of a single step in the agentic loop."""
    step_num: int
    description: str
    result: str
    status: str  # "completed" | "failed" | "adapted"
    duration_ms: int


@dataclass
class AgenticResult:
    """Final result of the entire agentic loop."""
    task_id: str
    task: str
    summary: str
    steps: list[AgenticStep] = field(default_factory=list)
    status: str = "completed"  # "completed" | "partial" | "failed"
    total_duration_ms: int = 0


# ---------------------------------------------------------------------------
# Agent factory
# ---------------------------------------------------------------------------

def _get_loop_agent():
    """Create a fresh agent for the agentic loop.

    Returns the same type of agent as `create_timmy()` but with a
    dedicated session so it doesn't pollute the main chat history.
    """
    from timmy.agent import create_timmy
    return create_timmy()


# ---------------------------------------------------------------------------
# Plan parser
# ---------------------------------------------------------------------------

_STEP_RE = re.compile(r"^\s*(\d+)[.)]\s*(.+)$", re.MULTILINE)


def _parse_steps(plan_text: str) -> list[str]:
    """Extract numbered steps from the model's planning output."""
    matches = _STEP_RE.findall(plan_text)
    if matches:
        return [desc.strip() for _, desc in matches]
    # Fallback: split on newlines, ignore blanks
    return [line.strip() for line in plan_text.strip().splitlines() if line.strip()]


# ---------------------------------------------------------------------------
# Core loop
# ---------------------------------------------------------------------------

async def run_agentic_loop(
    task: str,
    *,
    session_id: str = "agentic",
    max_steps: int = 0,
    on_progress: Optional[Callable] = None,
) -> AgenticResult:
    """Execute a multi-step task with planning, execution, and adaptation.

    Args:
        task:        Full description of the task to execute.
        session_id:  Agno session_id for conversation continuity.
        max_steps:   Max steps to execute (0 = use config default).
        on_progress: Optional async callback(description, step_num, total_steps).

    Returns:
        AgenticResult with steps, summary, and status.
    """
    from config import settings

    if max_steps <= 0:
        max_steps = getattr(settings, "max_agent_steps", 10)

    task_id = str(uuid.uuid4())[:8]
    start_time = time.monotonic()

    agent = _get_loop_agent()
    result = AgenticResult(task_id=task_id, task=task, summary="")

    # ── Phase 1: Planning ──────────────────────────────────────────────────
    plan_prompt = (
        f"Break this task into numbered steps (max {max_steps}). "
        f"Return ONLY a numbered list, nothing else.\n\n"
        f"Task: {task}"
    )
    try:
        plan_run = await asyncio.to_thread(
            agent.run, plan_prompt, stream=False, session_id=f"{session_id}_plan"
        )
        plan_text = plan_run.content if hasattr(plan_run, "content") else str(plan_run)
    except Exception as exc:
        logger.error("Agentic loop: planning failed: %s", exc)
        result.status = "failed"
        result.summary = f"Planning failed: {exc}"
        result.total_duration_ms = int((time.monotonic() - start_time) * 1000)
        return result

    steps = _parse_steps(plan_text)
    if not steps:
        result.status = "failed"
        result.summary = "Planning produced no steps."
        result.total_duration_ms = int((time.monotonic() - start_time) * 1000)
        return result

    # Enforce max_steps — track if we truncated
    planned_steps = len(steps)
    steps = steps[:max_steps]
    total_steps = len(steps)
    was_truncated = planned_steps > total_steps

    # Broadcast plan
    await _broadcast_progress("agentic.plan_ready", {
        "task_id": task_id,
        "task": task,
        "steps": steps,
        "total": total_steps,
    })

    # ── Phase 2: Execution ─────────────────────────────────────────────────
    completed_results: list[str] = []

    for i, step_desc in enumerate(steps, 1):
        step_start = time.monotonic()

        context = (
            f"Task: {task}\n"
            f"Plan: {plan_text}\n"
            f"Completed so far: {completed_results}\n\n"
            f"Now do step {i}: {step_desc}\n"
            f"Execute this step and report what you did."
        )

        try:
            step_run = await asyncio.to_thread(
                agent.run, context, stream=False, session_id=f"{session_id}_step{i}"
            )
            step_result = step_run.content if hasattr(step_run, "content") else str(step_run)

            # Clean the response
            from timmy.session import _clean_response
            step_result = _clean_response(step_result)

            step = AgenticStep(
                step_num=i,
                description=step_desc,
                result=step_result,
                status="completed",
                duration_ms=int((time.monotonic() - step_start) * 1000),
            )
            result.steps.append(step)
            completed_results.append(f"Step {i}: {step_result[:200]}")

            # Broadcast progress
            await _broadcast_progress("agentic.step_complete", {
                "task_id": task_id,
                "step": i,
                "total": total_steps,
                "description": step_desc,
                "result": step_result[:200],
            })

            if on_progress:
                await on_progress(step_desc, i, total_steps)

        except Exception as exc:
            logger.warning("Agentic loop step %d failed: %s", i, exc)

            # ── Adaptation: ask model to adapt ─────────────────────────────
            adapt_prompt = (
                f"Step {i} failed with error: {exc}\n"
                f"Original step was: {step_desc}\n"
                f"Adapt the plan and try an alternative approach for this step."
            )
            try:
                adapt_run = await asyncio.to_thread(
                    agent.run, adapt_prompt, stream=False,
                    session_id=f"{session_id}_adapt{i}",
                )
                adapt_result = adapt_run.content if hasattr(adapt_run, "content") else str(adapt_run)
                from timmy.session import _clean_response
                adapt_result = _clean_response(adapt_result)

                step = AgenticStep(
                    step_num=i,
                    description=f"[Adapted] {step_desc}",
                    result=adapt_result,
                    status="adapted",
                    duration_ms=int((time.monotonic() - step_start) * 1000),
                )
                result.steps.append(step)
                completed_results.append(f"Step {i} (adapted): {adapt_result[:200]}")

                await _broadcast_progress("agentic.step_adapted", {
                    "task_id": task_id,
                    "step": i,
                    "total": total_steps,
                    "description": step_desc,
                    "error": str(exc),
                    "adaptation": adapt_result[:200],
                })

                if on_progress:
                    await on_progress(f"[Adapted] {step_desc}", i, total_steps)

            except Exception as adapt_exc:
                logger.error("Agentic loop adaptation also failed: %s", adapt_exc)
                step = AgenticStep(
                    step_num=i,
                    description=step_desc,
                    result=f"Failed: {exc}; Adaptation also failed: {adapt_exc}",
                    status="failed",
                    duration_ms=int((time.monotonic() - step_start) * 1000),
                )
                result.steps.append(step)
                completed_results.append(f"Step {i}: FAILED")

    # ── Phase 3: Summary ───────────────────────────────────────────────────
    summary_prompt = (
        f"Task: {task}\n"
        f"Results:\n" + "\n".join(completed_results) + "\n\n"
        f"Summarise what was accomplished in 2-3 sentences."
    )
    try:
        summary_run = await asyncio.to_thread(
            agent.run, summary_prompt, stream=False,
            session_id=f"{session_id}_summary",
        )
        result.summary = summary_run.content if hasattr(summary_run, "content") else str(summary_run)
        from timmy.session import _clean_response
        result.summary = _clean_response(result.summary)
    except Exception as exc:
        logger.error("Agentic loop summary failed: %s", exc)
        result.summary = f"Completed {len(result.steps)} steps."

    # Determine final status
    if was_truncated:
        result.status = "partial"
    elif len(result.steps) < total_steps:
        result.status = "partial"
    elif any(s.status == "failed" for s in result.steps):
        result.status = "partial"
    else:
        result.status = "completed"

    result.total_duration_ms = int((time.monotonic() - start_time) * 1000)

    await _broadcast_progress("agentic.task_complete", {
        "task_id": task_id,
        "status": result.status,
        "steps_completed": len(result.steps),
        "summary": result.summary[:300],
        "duration_ms": result.total_duration_ms,
    })

    return result


# ---------------------------------------------------------------------------
# WebSocket broadcast helper
# ---------------------------------------------------------------------------

async def _broadcast_progress(event: str, data: dict) -> None:
    """Broadcast agentic loop progress via WebSocket (best-effort)."""
    try:
        from infrastructure.ws_manager.handler import ws_manager
        await ws_manager.broadcast(event, data)
    except Exception:
        logger.debug("Agentic loop: WS broadcast failed for %s", event)
