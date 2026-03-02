"""Voice routes — /voice/* and /voice/enhanced/* endpoints.

Provides NLU intent detection, TTS control, the full voice-to-action
pipeline (detect intent → execute → optionally speak), and the voice
button UI page.
"""

import logging

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

from integrations.voice.nlu import detect_intent, extract_command
from timmy.agent import create_timmy

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/voice", tags=["voice"])
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


@router.post("/nlu")
async def nlu_detect(text: str = Form(...)):
    """Detect intent from a text utterance."""
    intent = detect_intent(text)
    command = extract_command(text)
    return {
        "intent": intent.name,
        "confidence": intent.confidence,
        "entities": intent.entities,
        "command": command,
        "raw_text": intent.raw_text,
    }


@router.get("/tts/status")
async def tts_status():
    """Check TTS engine availability."""
    try:
        from timmy_serve.voice_tts import voice_tts
        return {
            "available": voice_tts.available,
            "voices": voice_tts.get_voices() if voice_tts.available else [],
        }
    except Exception:
        return {"available": False, "voices": []}


@router.post("/tts/speak")
async def tts_speak(text: str = Form(...)):
    """Speak text aloud via TTS."""
    try:
        from timmy_serve.voice_tts import voice_tts
        if not voice_tts.available:
            return {"spoken": False, "reason": "TTS engine not available"}
        voice_tts.speak(text)
        return {"spoken": True, "text": text}
    except Exception as exc:
        return {"spoken": False, "reason": str(exc)}


# ── Voice button page ────────────────────────────────────────────────────


@router.get("/button", response_class=HTMLResponse)
async def voice_button_page(request: Request):
    """Render the voice button UI."""
    return templates.TemplateResponse(request, "voice_button.html")


@router.post("/command")
async def voice_command(text: str = Form(...)):
    """Process a voice command (used by voice_button.html).

    Wraps the enhanced pipeline and returns the result in the format
    the voice button template expects.
    """
    result = await process_voice_input(text=text, speak_response=False)
    return {
        "command": {
            "intent": result["intent"],
            "response": result["response"] or result.get("error", "No response"),
        }
    }


# ── Enhanced voice pipeline ──────────────────────────────────────────────

@router.post("/enhanced/process")
async def process_voice_input(
    text: str = Form(...),
    speak_response: bool = Form(False),
):
    """Process a voice input: detect intent -> execute -> optionally speak.

    This is the main entry point for voice-driven interaction with Timmy.
    """
    intent = detect_intent(text)
    response_text = None
    error = None

    try:
        if intent.name == "status":
            response_text = "Timmy is operational and running locally. All systems sovereign."

        elif intent.name == "help":
            response_text = (
                "Available commands: chat with me, check status, "
                "manage the swarm, create tasks, or adjust voice settings. "
                "Everything runs locally — no cloud, no permission needed."
            )

        elif intent.name == "swarm":
            response_text = "Swarm module is not currently active."

        elif intent.name == "voice":
            response_text = "Voice settings acknowledged. TTS is available for spoken responses."

        elif intent.name == "code":
            response_text = "Self-modification module is not currently active."

        else:
            # Default: chat with Timmy
            agent = create_timmy()
            run = agent.run(text, stream=False)
            response_text = run.content if hasattr(run, "content") else str(run)

    except Exception as exc:
        error = f"Processing failed: {exc}"
        logger.error("Voice processing error: %s", exc)

    # Optionally speak the response
    if speak_response and response_text:
        try:
            from timmy_serve.voice_tts import voice_tts
            if voice_tts.available:
                voice_tts.speak(response_text)
        except Exception:
            pass

    return {
        "intent": intent.name,
        "confidence": intent.confidence,
        "response": response_text,
        "error": error,
        "spoken": speak_response and response_text is not None,
    }
