"""Self-Coding Dashboard Routes.

API endpoints and HTMX views for the self-coding system:
- Journal viewer with filtering
- Stats dashboard
- Manual task execution
- Real-time status updates
- Self-modification loop (/self-modify/*)
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from config import settings

from self_coding import (
    CodebaseIndexer,
    ModificationJournal,
    Outcome,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/self-coding", tags=["self_coding"])


# ── API Models ────────────────────────────────────────────────────────────

class JournalEntryResponse(BaseModel):
    """A journal entry for API response."""
    id: int
    timestamp: str
    task_description: str
    approach: str
    files_modified: list[str]
    outcome: str
    retry_count: int
    has_reflection: bool


class StatsResponse(BaseModel):
    """Self-coding stats for API response."""
    total_attempts: int
    success_count: int
    failure_count: int
    rollback_count: int
    success_rate: float
    recent_failures: list[JournalEntryResponse]


class ExecuteRequest(BaseModel):
    """Request to execute a self-edit task."""
    task_description: str


class ExecuteResponse(BaseModel):
    """Response from executing a self-edit task."""
    success: bool
    message: str
    attempt_id: Optional[int] = None
    files_modified: list[str] = []
    commit_hash: Optional[str] = None


# ── Services (initialized lazily) ─────────────────────────────────────────

_journal: Optional[ModificationJournal] = None
_indexer: Optional[CodebaseIndexer] = None


def get_journal() -> ModificationJournal:
    """Get or create ModificationJournal singleton."""
    global _journal
    if _journal is None:
        _journal = ModificationJournal()
    return _journal


def get_indexer() -> CodebaseIndexer:
    """Get or create CodebaseIndexer singleton."""
    global _indexer
    if _indexer is None:
        _indexer = CodebaseIndexer()
    return _indexer


# ── API Endpoints ─────────────────────────────────────────────────────────

@router.get("/api/journal", response_model=list[JournalEntryResponse])
async def api_journal_list(
    limit: int = 50,
    outcome: Optional[str] = None,
):
    """Get modification journal entries.
    
    Args:
        limit: Maximum number of entries to return
        outcome: Filter by outcome (success, failure, rollback)
    """
    journal = get_journal()
    
    # Build query based on filters
    if outcome:
        try:
            outcome_enum = Outcome(outcome)
            # Get recent and filter
            from self_coding.modification_journal import ModificationAttempt
            # Note: This is a simplified query - in production you'd add
            # proper filtering to the journal class
            entries = []
            # Placeholder for filtered query
        except ValueError:
            return JSONResponse(
                status_code=400,
                content={"error": f"Invalid outcome: {outcome}"},
            )
    
    # For now, return recent failures mixed with successes
    recent = await journal.get_recent_failures(limit=limit)
    
    # Also get some successes
    # Note: We'd need to add a method to journal for this
    # For now, return what we have
    
    response = []
    for entry in recent:
        response.append(JournalEntryResponse(
            id=entry.id or 0,
            timestamp=entry.timestamp.isoformat() if entry.timestamp else "",
            task_description=entry.task_description,
            approach=entry.approach,
            files_modified=entry.files_modified,
            outcome=entry.outcome.value,
            retry_count=entry.retry_count,
            has_reflection=bool(entry.reflection),
        ))
    
    return response


@router.get("/api/journal/{attempt_id}", response_model=dict)
async def api_journal_detail(attempt_id: int):
    """Get detailed information about a specific attempt."""
    journal = get_journal()
    entry = await journal.get_by_id(attempt_id)
    
    if not entry:
        return JSONResponse(
            status_code=404,
            content={"error": "Attempt not found"},
        )
    
    return {
        "id": entry.id,
        "timestamp": entry.timestamp.isoformat() if entry.timestamp else "",
        "task_description": entry.task_description,
        "approach": entry.approach,
        "files_modified": entry.files_modified,
        "diff": entry.diff,
        "test_results": entry.test_results,
        "outcome": entry.outcome.value,
        "failure_analysis": entry.failure_analysis,
        "reflection": entry.reflection,
        "retry_count": entry.retry_count,
    }


@router.get("/api/stats", response_model=StatsResponse)
async def api_stats():
    """Get self-coding statistics."""
    journal = get_journal()
    
    metrics = await journal.get_success_rate()
    recent_failures = await journal.get_recent_failures(limit=5)
    
    return StatsResponse(
        total_attempts=metrics["total"],
        success_count=metrics["success"],
        failure_count=metrics["failure"],
        rollback_count=metrics["rollback"],
        success_rate=metrics["overall"],
        recent_failures=[
            JournalEntryResponse(
                id=f.id or 0,
                timestamp=f.timestamp.isoformat() if f.timestamp else "",
                task_description=f.task_description,
                approach=f.approach,
                files_modified=f.files_modified,
                outcome=f.outcome.value,
                retry_count=f.retry_count,
                has_reflection=bool(f.reflection),
            )
            for f in recent_failures
        ],
    )


@router.post("/api/execute", response_model=ExecuteResponse)
async def api_execute(request: ExecuteRequest):
    """Execute a self-edit task.
    
    This is the API endpoint for manual task execution.
    In production, this should require authentication and confirmation.
    """
    from creative.tools.self_edit import SelfEditTool
    
    tool = SelfEditTool()
    result = await tool.execute(request.task_description)
    
    return ExecuteResponse(
        success=result.success,
        message=result.message,
        attempt_id=result.attempt_id,
        files_modified=result.files_modified,
        commit_hash=result.commit_hash,
    )


@router.get("/api/codebase/summary")
async def api_codebase_summary():
    """Get codebase summary for LLM context."""
    indexer = get_indexer()
    await indexer.index_changed()
    
    summary = await indexer.get_summary(max_tokens=3000)
    
    return {
        "summary": summary,
        "generated_at": "",
    }


@router.post("/api/codebase/reindex")
async def api_codebase_reindex():
    """Trigger a full codebase reindex."""
    indexer = get_indexer()
    stats = await indexer.index_all()
    
    return {
        "indexed": stats["indexed"],
        "failed": stats["failed"],
        "skipped": stats["skipped"],
    }


# ── HTMX Page Routes ──────────────────────────────────────────────────────

@router.get("", response_class=HTMLResponse)
async def self_coding_page(request: Request):
    """Main self-coding dashboard page."""
    from dashboard.app import templates
    
    return templates.TemplateResponse(
        "self_coding.html",
        {
            "request": request,
            "title": "Self-Coding",
        },
    )


@router.get("/journal", response_class=HTMLResponse)
async def journal_partial(
    request: Request,
    outcome: Optional[str] = None,
    limit: int = 20,
):
    """HTMX partial for journal entries."""
    from dashboard.app import templates
    
    journal = get_journal()
    
    # Get entries (simplified - in production, add proper filtering)
    if outcome == "failure":
        entries = await journal.get_recent_failures(limit=limit)
    else:
        # Get all recent
        entries = await journal.get_recent_failures(limit=limit)
        # TODO: Add method to get successes too
    
    return templates.TemplateResponse(
        "partials/journal_entries.html",
        {
            "request": request,
            "entries": entries,
            "outcome_filter": outcome,
        },
    )


@router.get("/stats", response_class=HTMLResponse)
async def stats_partial(request: Request):
    """HTMX partial for stats cards."""
    from dashboard.app import templates
    
    journal = get_journal()
    metrics = await journal.get_success_rate()
    
    return templates.TemplateResponse(
        "partials/self_coding_stats.html",
        {
            "request": request,
            "metrics": metrics,
        },
    )


@router.get("/execute-form", response_class=HTMLResponse)
async def execute_form_partial(request: Request):
    """HTMX partial for execute task form."""
    from dashboard.app import templates
    
    return templates.TemplateResponse(
        "partials/execute_form.html",
        {
            "request": request,
        },
    )


@router.post("/execute", response_class=HTMLResponse)
async def execute_task(
    request: Request,
    task_description: str = Form(...),
):
    """HTMX endpoint to execute a task."""
    from dashboard.app import templates
    from creative.tools.self_edit import SelfEditTool
    
    tool = SelfEditTool()
    result = await tool.execute(task_description)
    
    return templates.TemplateResponse(
        "partials/execute_result.html",
        {
            "request": request,
            "result": result,
        },
    )


@router.get("/journal/{attempt_id}/detail", response_class=HTMLResponse)
async def journal_entry_detail(request: Request, attempt_id: int):
    """HTMX partial for journal entry detail."""
    from dashboard.app import templates
    
    journal = get_journal()
    entry = await journal.get_by_id(attempt_id)
    
    if not entry:
        return templates.TemplateResponse(
            "partials/error.html",
            {
                "request": request,
                "message": "Attempt not found",
            },
        )
    
    return templates.TemplateResponse(
        "partials/journal_entry_detail.html",
        {
            "request": request,
            "entry": entry,
        },
    )


# ── Self-Modification Routes (/self-modify/*) ───────────────────────────

self_modify_router = APIRouter(prefix="/self-modify", tags=["self-modify"])


@self_modify_router.post("/run")
async def run_self_modify(
    instruction: str = Form(...),
    target_files: str = Form(""),
    dry_run: bool = Form(False),
    speak_result: bool = Form(False),
):
    """Execute a self-modification loop."""
    if not settings.self_modify_enabled:
        raise HTTPException(403, "Self-modification is disabled")

    from self_coding.self_modify.loop import SelfModifyLoop, ModifyRequest

    files = [f.strip() for f in target_files.split(",") if f.strip()]
    request = ModifyRequest(
        instruction=instruction,
        target_files=files,
        dry_run=dry_run,
    )

    loop = SelfModifyLoop()
    result = await asyncio.to_thread(loop.run, request)

    if speak_result and result.success:
        try:
            from timmy_serve.voice_tts import voice_tts
            if voice_tts.available:
                voice_tts.speak(
                    f"Code modification complete. "
                    f"{len(result.files_changed)} files changed. Tests passing."
                )
        except Exception:
            pass

    return {
        "success": result.success,
        "files_changed": result.files_changed,
        "test_passed": result.test_passed,
        "commit_sha": result.commit_sha,
        "branch_name": result.branch_name,
        "error": result.error,
        "attempts": result.attempts,
    }


@self_modify_router.get("/status")
async def self_modify_status():
    """Return whether self-modification is enabled."""
    return {"enabled": settings.self_modify_enabled}
