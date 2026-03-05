"""Thinking routes — Timmy's inner thought stream.

GET  /thinking            — render the thought stream page
GET  /thinking/api        — JSON list of recent thoughts
GET  /thinking/api/{id}/chain — follow a thought chain
"""

import logging

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

from timmy.thinking import thinking_engine
from dashboard.templating import templates

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/thinking", tags=["thinking"])


@router.get("", response_class=HTMLResponse)
async def thinking_page(request: Request):
    """Render Timmy's thought stream page."""
    thoughts = thinking_engine.get_recent_thoughts(limit=50)
    return templates.TemplateResponse(
        request,
        "thinking.html",
        {"thoughts": thoughts},
    )


@router.get("/api", response_class=JSONResponse)
async def thinking_api(limit: int = 20):
    """Return recent thoughts as JSON."""
    thoughts = thinking_engine.get_recent_thoughts(limit=limit)
    return [
        {
            "id": t.id,
            "content": t.content,
            "seed_type": t.seed_type,
            "parent_id": t.parent_id,
            "created_at": t.created_at,
        }
        for t in thoughts
    ]


@router.get("/api/{thought_id}/chain", response_class=JSONResponse)
async def thought_chain_api(thought_id: str):
    """Follow a thought chain backward and return in chronological order."""
    chain = thinking_engine.get_thought_chain(thought_id)
    if not chain:
        return JSONResponse({"error": "Thought not found"}, status_code=404)
    return [
        {
            "id": t.id,
            "content": t.content,
            "seed_type": t.seed_type,
            "parent_id": t.parent_id,
            "created_at": t.created_at,
        }
        for t in chain
    ]
