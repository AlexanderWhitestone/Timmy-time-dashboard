"""Self-modification routes — /self-modify endpoints.

Exposes the edit-test-commit loop as a REST API.  Gated by
``SELF_MODIFY_ENABLED`` (default False).
"""

import asyncio
import logging

from fastapi import APIRouter, Form, HTTPException

from config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/self-modify", tags=["self-modify"])


@router.post("/run")
async def run_self_modify(
    instruction: str = Form(...),
    target_files: str = Form(""),
    dry_run: bool = Form(False),
    speak_result: bool = Form(False),
):
    """Execute a self-modification loop.

    Returns the ModifyResult as JSON.
    """
    if not settings.self_modify_enabled:
        raise HTTPException(403, "Self-modification is disabled")

    from self_modify.loop import SelfModifyLoop, ModifyRequest

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


@router.get("/status")
async def self_modify_status():
    """Return whether self-modification is enabled."""
    return {"enabled": settings.self_modify_enabled}
