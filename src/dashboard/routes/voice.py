"""Voice routes — /voice/* and /voice/enhanced/* endpoints.

Provides NLU intent detection, TTS control, and the full voice-to-action
pipeline (detect intent → execute → optionally speak).
"""

import logging

from fastapi import APIRouter, Form

from voice.nlu import detect_intent, extract_command
from timmy.agent import create_timmy

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/voice", tags=["voice"])


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
            from swarm.coordinator import coordinator
            status = coordinator.status()
            response_text = (
                f"Swarm status: {status['agents']} agents registered, "
                f"{status['agents_idle']} idle, {status['agents_busy']} busy. "
                f"{status['tasks_total']} total tasks, "
                f"{status['tasks_completed']} completed."
            )

        elif intent.name == "voice":
            response_text = "Voice settings acknowledged. TTS is available for spoken responses."

        elif intent.name == "code":
            from config import settings as app_settings
            if not app_settings.self_modify_enabled:
                response_text = (
                    "Self-modification is disabled. "
                    "Set SELF_MODIFY_ENABLED=true to enable."
                )
            else:
                import asyncio
                from self_modify.loop import SelfModifyLoop, ModifyRequest

                target_files = []
                if "target_file" in intent.entities:
                    target_files = [intent.entities["target_file"]]

                loop = SelfModifyLoop()
                request = ModifyRequest(
                    instruction=text,
                    target_files=target_files,
                )
                result = await asyncio.to_thread(loop.run, request)

                if result.success:
                    sha_short = result.commit_sha[:8] if result.commit_sha else "none"
                    response_text = (
                        f"Code modification complete. "
                        f"Changed {len(result.files_changed)} file(s). "
                        f"Tests passed. Committed as {sha_short} "
                        f"on branch {result.branch_name}."
                    )
                else:
                    response_text = f"Code modification failed: {result.error}"

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
