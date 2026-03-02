"""Serve routes — merged from timmy_serve into dashboard.

These endpoints expose Timmy's API service capabilities directly
from the dashboard, eliminating the need for a separate FastAPI app.
"""

import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, field_validator

from config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/serve", tags=["serve"])


class ChatRequest(BaseModel):
    """Chat request body."""
    message: str

    @field_validator("message")
    @classmethod
    def message_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Message cannot be empty")
        return v


@router.get("/status")
async def serve_status():
    """Service status endpoint."""
    return JSONResponse({
        "status": "active",
        "backend": settings.timmy_model_backend,
        "model": settings.ollama_model,
        "service": "timmy-serve",
    })


@router.post("/chat")
async def serve_chat(req: ChatRequest):
    """Chat with Timmy via API.

    This is the merged version of timmy_serve's /serve/chat endpoint.
    """
    try:
        from timmy.agent import create_timmy

        agent = create_timmy()
        result = agent.run(req.message, stream=False)
        content = result.content if hasattr(result, "content") else str(result)
        return JSONResponse({"response": content})
    except Exception as exc:
        logger.error("Serve chat error: %s", exc)
        return JSONResponse(
            {"error": "Failed to generate response", "detail": str(exc)},
            status_code=500,
        )
