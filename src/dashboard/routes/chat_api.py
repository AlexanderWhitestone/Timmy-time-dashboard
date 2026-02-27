"""JSON REST API for mobile / external chat clients.

Provides the same Timmy chat experience as the HTMX dashboard but over
a JSON interface that React Native (or any HTTP client) can consume.

Endpoints:
    POST /api/chat       — send a message, get Timmy's reply
    POST /api/upload     — upload a file attachment
    GET  /api/chat/history  — retrieve recent chat history
    DELETE /api/chat/history — clear chat history
"""

import logging
import os
import uuid
from datetime import datetime

from fastapi import APIRouter, File, Request, UploadFile, HTTPException
from fastapi.responses import JSONResponse

from config import settings
from dashboard.store import message_log
from timmy.session import chat as timmy_chat

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["chat-api"])

_UPLOAD_DIR = os.path.join("data", "chat-uploads")


# ── POST /api/chat ────────────────────────────────────────────────────────────

@router.post("/chat")
async def api_chat(request: Request):
    """Accept a JSON chat payload and return Timmy's reply.

    Request body:
        {"messages": [{"role": "user"|"assistant", "content": "..."}]}

    Response:
        {"reply": "...", "timestamp": "HH:MM:SS"}
    """
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": "Invalid JSON"})

    messages = body.get("messages")
    if not messages or not isinstance(messages, list):
        return JSONResponse(status_code=400, content={"error": "messages array is required"})

    # Extract the latest user message text
    last_user_msg = None
    for msg in reversed(messages):
        if msg.get("role") == "user":
            content = msg.get("content", "")
            # Handle multimodal content arrays — extract text parts
            if isinstance(content, list):
                text_parts = [
                    p.get("text", "") for p in content
                    if isinstance(p, dict) and p.get("type") == "text"
                ]
                last_user_msg = " ".join(text_parts).strip()
            else:
                last_user_msg = str(content).strip()
            break

    if not last_user_msg:
        return JSONResponse(status_code=400, content={"error": "No user message found"})

    timestamp = datetime.now().strftime("%H:%M:%S")

    try:
        # Inject context (same pattern as the HTMX chat handler in agents.py)
        now = datetime.now()
        context_prefix = (
            f"[System: Current date/time is "
            f"{now.strftime('%A, %B %d, %Y at %I:%M %p')}]\n"
            f"[System: Mobile client]\n\n"
        )
        response_text = timmy_chat(
            context_prefix + last_user_msg,
            session_id="mobile",
        )

        message_log.append(role="user", content=last_user_msg, timestamp=timestamp)
        message_log.append(role="agent", content=response_text, timestamp=timestamp)

        return {"reply": response_text, "timestamp": timestamp}

    except Exception as exc:
        error_msg = f"Timmy is offline: {exc}"
        logger.error("api_chat error: %s", exc)
        message_log.append(role="user", content=last_user_msg, timestamp=timestamp)
        message_log.append(role="error", content=error_msg, timestamp=timestamp)
        return JSONResponse(
            status_code=503,
            content={"error": error_msg, "timestamp": timestamp},
        )


# ── POST /api/upload ──────────────────────────────────────────────────────────

@router.post("/upload")
async def api_upload(file: UploadFile = File(...)):
    """Accept a file upload and return its URL.

    Includes security checks for file size and extension.

    Response:
        {"url": "/static/chat-uploads/...", "fileName": "...", "mimeType": "..."}
    """
    # 1. Check file extension
    filename = file.filename or "upload"
    ext = filename.split(".")[-1].lower() if "." in filename else ""
    if ext not in settings.allowed_upload_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"File extension '.{ext}' not allowed. Allowed: {', '.join(settings.allowed_upload_extensions)}"
        )

    # 2. Check file size (streaming to avoid loading huge files into memory)
    max_size = settings.max_upload_size_mb * 1024 * 1024
    size = 0
    os.makedirs(_UPLOAD_DIR, exist_ok=True)

    suffix = uuid.uuid4().hex[:12]
    safe_name = filename.replace("/", "_").replace("\\", "_")
    stored_name = f"{suffix}-{safe_name}"
    file_path = os.path.join(_UPLOAD_DIR, stored_name)

    try:
        with open(file_path, "wb") as f:
            while chunk := await file.read(8192):
                size += len(chunk)
                if size > max_size:
                    f.close()
                    if os.path.exists(file_path):
                        os.remove(file_path)
                    raise HTTPException(
                        status_code=413,
                        detail=f"File too large. Maximum size is {settings.max_upload_size_mb}MB"
                    )
                f.write(chunk)
    except Exception as exc:
        if isinstance(exc, HTTPException):
            raise exc
        logger.error("Upload error: %s", exc)
        if os.path.exists(file_path):
            os.remove(file_path)
        raise HTTPException(status_code=500, detail="Internal server error during upload")

    # Return a URL the mobile app can reference
    url = f"/uploads/{stored_name}"

    return {
        "url": url,
        "fileName": filename,
        "mimeType": file.content_type or "application/octet-stream",
    }


# ── GET /api/chat/history ────────────────────────────────────────────────────

@router.get("/chat/history")
async def api_chat_history():
    """Return the in-memory chat history as JSON."""
    return {
        "messages": [
            {
                "role": msg.role,
                "content": msg.content,
                "timestamp": msg.timestamp,
            }
            for msg in message_log.all()
        ]
    }


# ── DELETE /api/chat/history ──────────────────────────────────────────────────

@router.delete("/chat/history")
async def api_clear_history():
    """Clear the in-memory chat history."""
    message_log.clear()
    return {"success": True}
