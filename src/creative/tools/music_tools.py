"""Music generation tools — Lyra persona.

Uses ACE-Step 1.5 for full song generation with vocals, instrumentals,
and lyrics.  Falls back gracefully when the ``creative`` extra is not
installed.

All heavy imports are lazy — the module loads instantly without GPU.
"""

from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Lazy-loaded model singleton
_model = None


def _get_model():
    """Lazy-load the ACE-Step music generation model."""
    global _model
    if _model is not None:
        return _model

    try:
        from ace_step import ACEStep
    except ImportError:
        raise ImportError(
            "ACE-Step not installed.  Run: pip install 'timmy-time[creative]'"
        )

    from config import settings
    model_name = getattr(settings, "ace_step_model", "ace-step/ACE-Step-v1.5")

    logger.info("Loading music model %s …", model_name)
    _model = ACEStep(model_name)
    logger.info("Music model loaded.")
    return _model


def _output_dir() -> Path:
    from config import settings
    d = Path(getattr(settings, "music_output_dir", "data/music"))
    d.mkdir(parents=True, exist_ok=True)
    return d


def _save_metadata(audio_path: Path, meta: dict) -> Path:
    meta_path = audio_path.with_suffix(".json")
    meta_path.write_text(json.dumps(meta, indent=2))
    return meta_path


# ── Supported genres ──────────────────────────────────────────────────────────

GENRES = [
    "pop", "rock", "hip-hop", "r&b", "jazz", "blues", "country",
    "electronic", "classical", "folk", "reggae", "metal", "punk",
    "soul", "funk", "latin", "ambient", "lo-fi", "cinematic",
]


# ── Public tools ──────────────────────────────────────────────────────────────

def generate_song(
    lyrics: str,
    genre: str = "pop",
    duration: int = 120,
    language: str = "en",
    title: Optional[str] = None,
) -> dict:
    """Generate a full song with vocals and instrumentals from lyrics.

    Args:
        lyrics: Song lyrics text.
        genre: Musical genre / style tag.
        duration: Target duration in seconds (30–240).
        language: ISO language code (19 languages supported).
        title: Optional song title for metadata.

    Returns dict with ``path``, ``duration``, ``genre``, etc.
    """
    model = _get_model()
    duration = max(30, min(240, duration))

    uid = uuid.uuid4().hex[:12]
    out_path = _output_dir() / f"{uid}.wav"

    logger.info("Generating song: genre=%s duration=%ds …", genre, duration)
    audio = model.generate(
        lyrics=lyrics,
        genre=genre,
        duration=duration,
        language=language,
    )
    audio.save(str(out_path))

    meta = {
        "id": uid, "title": title or f"Untitled ({genre})",
        "lyrics": lyrics, "genre": genre,
        "duration": duration, "language": language,
    }
    _save_metadata(out_path, meta)

    return {"success": True, "path": str(out_path), **meta}


def generate_instrumental(
    prompt: str,
    genre: str = "cinematic",
    duration: int = 60,
) -> dict:
    """Generate an instrumental track from a text prompt (no vocals).

    Args:
        prompt: Description of the desired music.
        genre: Musical genre / style tag.
        duration: Target duration in seconds (15–180).
    """
    model = _get_model()
    duration = max(15, min(180, duration))

    uid = uuid.uuid4().hex[:12]
    out_path = _output_dir() / f"{uid}.wav"

    logger.info("Generating instrumental: genre=%s …", genre)
    audio = model.generate(
        lyrics="",
        genre=genre,
        duration=duration,
        prompt=prompt,
    )
    audio.save(str(out_path))

    meta = {
        "id": uid, "prompt": prompt, "genre": genre,
        "duration": duration, "instrumental": True,
    }
    _save_metadata(out_path, meta)

    return {"success": True, "path": str(out_path), **meta}


def generate_vocals(
    lyrics: str,
    style: str = "pop",
    duration: int = 60,
    language: str = "en",
) -> dict:
    """Generate a vocal-only track from lyrics.

    Useful for layering over custom instrumentals.
    """
    model = _get_model()
    duration = max(15, min(180, duration))

    uid = uuid.uuid4().hex[:12]
    out_path = _output_dir() / f"{uid}.wav"

    audio = model.generate(
        lyrics=lyrics,
        genre=f"{style} acapella vocals",
        duration=duration,
        language=language,
    )
    audio.save(str(out_path))

    meta = {
        "id": uid, "lyrics": lyrics, "style": style,
        "duration": duration, "vocals_only": True,
    }
    _save_metadata(out_path, meta)

    return {"success": True, "path": str(out_path), **meta}


def list_genres() -> dict:
    """Return the list of supported genre / style tags."""
    return {"success": True, "genres": GENRES}


# ── Tool catalogue ────────────────────────────────────────────────────────────

MUSIC_TOOL_CATALOG: dict[str, dict] = {
    "generate_song": {
        "name": "Generate Song",
        "description": "Generate a full song with vocals + instrumentals from lyrics",
        "fn": generate_song,
    },
    "generate_instrumental": {
        "name": "Generate Instrumental",
        "description": "Generate an instrumental track from a text prompt",
        "fn": generate_instrumental,
    },
    "generate_vocals": {
        "name": "Generate Vocals",
        "description": "Generate a vocal-only track from lyrics",
        "fn": generate_vocals,
    },
    "list_genres": {
        "name": "List Genres",
        "description": "List supported music genre / style tags",
        "fn": list_genres,
    },
}
