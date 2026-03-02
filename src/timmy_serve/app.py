"""Timmy Serve — FastAPI app for Timmy's API.

Endpoints:
  POST /serve/chat    — Chat with Timmy
  GET  /serve/status  — Service status
  GET  /health        — Health check
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel

from config import settings
from timmy.agent import create_timmy

logger = logging.getLogger(__name__)


class ChatRequest(BaseModel):
    message: str
    stream: bool = False


class ChatResponse(BaseModel):
    response: str


class StatusResponse(BaseModel):
    status: str
    backend: str


def create_timmy_serve_app() -> FastAPI:
    """Create the Timmy Serve FastAPI application."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        logger.info("Timmy Serve starting")
        yield
        logger.info("Timmy Serve shutting down")

    app = FastAPI(
        title="Timmy Serve — Sovereign AI API",
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
    )

    @app.get("/serve/status", response_model=StatusResponse)
    async def serve_status():
        """Get service status."""
        return StatusResponse(
            status="active",
            backend=settings.timmy_model_backend,
        )

    @app.post("/serve/chat", response_model=ChatResponse)
    async def serve_chat(request: Request, body: ChatRequest):
        """Process a chat request."""
        try:
            timmy = create_timmy()
            result = timmy.run(body.message, stream=False)
            response_text = result.content if hasattr(result, "content") else str(result)

            return ChatResponse(response=response_text)

        except Exception as exc:
            logger.error("Chat processing error: %s", exc)
            raise HTTPException(status_code=500, detail=f"Processing error: {exc}")

    @app.get("/health")
    async def health():
        """Health check endpoint."""
        return {"status": "healthy", "service": "timmy-serve"}

    return app


# Default app instance for uvicorn
timmy_serve_app = create_timmy_serve_app()
