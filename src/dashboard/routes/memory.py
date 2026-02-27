"""Memory (vector store) routes for browsing and searching memories."""

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from timmy.memory.vector_store import (
    store_memory,
    search_memories,
    get_memory_stats,
    recall_personal_facts,
    recall_personal_facts_with_ids,
    store_personal_fact,
    update_personal_fact,
    delete_memory,
)

router = APIRouter(prefix="/memory", tags=["memory"])
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


@router.get("", response_class=HTMLResponse)
async def memory_page(
    request: Request,
    query: Optional[str] = None,
    context_type: Optional[str] = None,
    agent_id: Optional[str] = None,
):
    """Memory browser and search page."""
    results = []
    if query:
        results = search_memories(
            query=query,
            context_type=context_type,
            agent_id=agent_id,
            limit=20,
        )
    
    stats = get_memory_stats()
    facts = recall_personal_facts_with_ids()[:10]
    
    return templates.TemplateResponse(
        request,
        "memory.html",
        {
            "page_title": "Memory Browser",
            "query": query,
            "results": results,
            "stats": stats,
            "facts": facts,
            "filter_type": context_type,
            "filter_agent": agent_id,
        },
    )


@router.post("/search", response_class=HTMLResponse)
async def memory_search(
    request: Request,
    query: str = Form(...),
    context_type: Optional[str] = Form(None),
):
    """Search memories (form submission)."""
    results = search_memories(
        query=query,
        context_type=context_type,
        limit=20,
    )
    
    # Return partial for HTMX
    return templates.TemplateResponse(
        request,
        "partials/memory_results.html",
        {
            "query": query,
            "results": results,
        },
    )


@router.post("/fact", response_class=HTMLResponse)
async def add_fact(
    request: Request,
    fact: str = Form(...),
    agent_id: Optional[str] = Form(None),
):
    """Add a personal fact to memory."""
    store_personal_fact(fact, agent_id=agent_id)

    facts = recall_personal_facts_with_ids()[:10]
    return templates.TemplateResponse(
        request,
        "partials/memory_facts.html",
        {"facts": facts},
    )


@router.put("/fact/{fact_id}", response_class=JSONResponse)
async def edit_fact(fact_id: str, request: Request):
    """Update a personal fact."""
    body = await request.json()
    new_content = body.get("content", "").strip()
    if not new_content:
        raise HTTPException(400, "Content cannot be empty")
    ok = update_personal_fact(fact_id, new_content)
    if not ok:
        raise HTTPException(404, "Fact not found")
    return {"success": True, "id": fact_id, "content": new_content}


@router.delete("/fact/{fact_id}", response_class=JSONResponse)
async def delete_fact(fact_id: str):
    """Delete a personal fact."""
    ok = delete_memory(fact_id)
    if not ok:
        raise HTTPException(404, "Fact not found")
    return {"success": True, "id": fact_id}
