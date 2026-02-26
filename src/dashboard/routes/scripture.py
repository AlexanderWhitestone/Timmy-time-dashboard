"""Scripture dashboard routes.

GET  /scripture              — JSON status of the scripture module
GET  /scripture/verse        — Look up a single verse by reference
GET  /scripture/search       — Full-text search across verse content
GET  /scripture/chapter      — Retrieve an entire chapter
GET  /scripture/meditate     — Get the current meditation verse
POST /scripture/meditate     — Advance meditation to the next verse
POST /scripture/meditate/mode — Change meditation mode
GET  /scripture/memory       — Scripture memory system status
GET  /scripture/xref         — Cross-references for a verse
GET  /scripture/stats        — Store statistics
POST /scripture/ingest       — Bulk-ingest verses (JSON array)
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from scripture.constants import BOOK_BY_ID, book_by_name
from scripture.meditation import meditation_scheduler
from scripture.memory import scripture_memory
from scripture.models import Verse, encode_verse_id
from scripture.parser import extract_references, format_reference, parse_reference
from scripture.store import scripture_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/scripture", tags=["scripture"])


@router.get("")
async def scripture_status():
    """Return scripture module status — store stats + memory state."""
    return JSONResponse({
        "store": scripture_store.stats(),
        "memory": scripture_memory.status(),
        "meditation": meditation_scheduler.status(),
    })


@router.get("/verse")
async def get_verse(
    ref: str = Query(
        ...,
        description="Biblical reference, e.g. 'John 3:16' or 'Gen 1:1-3'",
    ),
):
    """Look up one or more verses by reference string."""
    parsed = parse_reference(ref)
    if not parsed:
        return JSONResponse(
            {"error": f"Could not parse reference: {ref}"},
            status_code=400,
        )

    start = parsed.start
    end = parsed.end

    if start.verse_id == end.verse_id:
        verse = scripture_store.get_verse(start.book, start.chapter, start.verse)
        if not verse:
            return JSONResponse({"error": "Verse not found", "ref": ref}, status_code=404)
        return JSONResponse(_verse_to_dict(verse))

    verses = scripture_store.get_range(start.verse_id, end.verse_id)
    if not verses:
        return JSONResponse({"error": "No verses found in range", "ref": ref}, status_code=404)
    return JSONResponse({"verses": [_verse_to_dict(v) for v in verses]})


@router.get("/chapter")
async def get_chapter(
    book: str = Query(..., description="Book name or abbreviation"),
    chapter: int = Query(..., ge=1, description="Chapter number"),
):
    """Retrieve all verses in a chapter."""
    book_info = book_by_name(book)
    if not book_info:
        return JSONResponse({"error": f"Unknown book: {book}"}, status_code=400)

    verses = scripture_store.get_chapter(book_info.id, chapter)
    if not verses:
        return JSONResponse(
            {"error": f"No verses found for {book_info.name} {chapter}"},
            status_code=404,
        )
    return JSONResponse({
        "book": book_info.name,
        "chapter": chapter,
        "verses": [_verse_to_dict(v) for v in verses],
    })


@router.get("/search")
async def search_verses(
    q: str = Query(..., min_length=2, description="Search query"),
    limit: int = Query(default=20, ge=1, le=100),
):
    """Full-text search across verse content."""
    verses = scripture_store.search_text(q, limit=limit)
    return JSONResponse({
        "query": q,
        "count": len(verses),
        "verses": [_verse_to_dict(v) for v in verses],
    })


@router.get("/meditate")
async def get_meditation():
    """Return the current meditation focus verse and status."""
    status = meditation_scheduler.status()
    current = meditation_scheduler.current_focus()
    return JSONResponse({
        "status": status,
        "current_verse": _verse_to_dict(current) if current else None,
    })


@router.post("/meditate")
async def advance_meditation():
    """Advance to the next verse in the meditation sequence."""
    verse = meditation_scheduler.next_meditation()
    if not verse:
        return JSONResponse(
            {"message": "No more verses available — scripture store may be empty"},
            status_code=404,
        )
    return JSONResponse({
        "verse": _verse_to_dict(verse),
        "status": meditation_scheduler.status(),
    })


@router.post("/meditate/mode")
async def set_meditation_mode(
    mode: str = Query(..., description="sequential, thematic, or lectionary"),
    theme: Optional[str] = Query(default=None, description="Theme for thematic mode"),
):
    """Change the meditation mode."""
    try:
        state = meditation_scheduler.set_mode(mode, theme=theme)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    return JSONResponse({
        "mode": state.mode,
        "theme": state.theme,
        "message": f"Meditation mode set to {state.mode}",
    })


@router.get("/memory")
async def memory_status():
    """Return the scripture memory system status."""
    return JSONResponse(scripture_memory.status())


@router.get("/xref")
async def get_cross_references(
    ref: str = Query(..., description="Verse reference, e.g. 'John 3:16'"),
):
    """Find cross-references for a verse."""
    parsed = parse_reference(ref)
    if not parsed:
        return JSONResponse({"error": f"Could not parse: {ref}"}, status_code=400)

    verse = scripture_store.get_verse(
        parsed.start.book, parsed.start.chapter, parsed.start.verse
    )
    if not verse:
        return JSONResponse({"error": "Verse not found"}, status_code=404)

    xrefs = scripture_store.get_cross_references(verse.verse_id)
    results = []
    for xref in xrefs:
        target_id = (
            xref.target_verse_id
            if xref.source_verse_id == verse.verse_id
            else xref.source_verse_id
        )
        target = scripture_store.get_verse_by_id(target_id)
        if target:
            results.append({
                "reference_type": xref.reference_type,
                "confidence": xref.confidence,
                "verse": _verse_to_dict(target),
            })

    return JSONResponse({
        "source": _verse_to_dict(verse),
        "cross_references": results,
    })


@router.get("/stats")
async def store_stats():
    """Return scripture store statistics."""
    return JSONResponse(scripture_store.stats())


@router.post("/ingest")
async def ingest_verses(request: Request):
    """Bulk-ingest verses from a JSON array.

    Expects a JSON body with a "verses" key containing an array of objects
    with: book, chapter, verse_num, text, and optionally
    translation/testament/genre.
    """
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

    raw_verses = body.get("verses", [])
    if not raw_verses:
        return JSONResponse({"error": "No verses provided"}, status_code=400)

    verses = []
    for rv in raw_verses:
        try:
            book = int(rv["book"])
            chapter = int(rv["chapter"])
            verse_num = int(rv["verse_num"])
            text = str(rv["text"])
            book_info = BOOK_BY_ID.get(book)
            verses.append(Verse(
                verse_id=encode_verse_id(book, chapter, verse_num),
                book=book,
                chapter=chapter,
                verse_num=verse_num,
                text=text,
                translation=rv.get("translation", "ESV"),
                testament=book_info.testament if book_info else "OT",
                genre=book_info.genre if book_info else "",
            ))
        except (KeyError, ValueError, TypeError) as exc:
            logger.warning("Skipping invalid verse record: %s", exc)
            continue

    if verses:
        scripture_store.insert_verses(verses)

    return JSONResponse({
        "ingested": len(verses),
        "skipped": len(raw_verses) - len(verses),
        "total_verses": scripture_store.count_verses(),
    })


# ── Helpers ──────────────────────────────────────────────────────────────────


def _verse_to_dict(verse: Verse) -> dict:
    """Convert a Verse model to a JSON-friendly dict with formatted reference."""
    from scripture.models import VerseRef

    ref = VerseRef(book=verse.book, chapter=verse.chapter, verse=verse.verse_num)
    return {
        "verse_id": verse.verse_id,
        "reference": format_reference(ref),
        "book": verse.book,
        "chapter": verse.chapter,
        "verse_num": verse.verse_num,
        "text": verse.text,
        "translation": verse.translation,
        "testament": verse.testament,
        "genre": verse.genre,
    }
