"""Video assembly engine — stitch clips, overlay audio, add titles.

Uses MoviePy + FFmpeg to combine generated video clips, music tracks,
and title cards into 3+ minute final videos.
"""

from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_MOVIEPY_AVAILABLE = True
try:
    from moviepy import (
        VideoFileClip,
        AudioFileClip,
        TextClip,
        CompositeVideoClip,
        ImageClip,
        concatenate_videoclips,
        vfx,
    )
except ImportError:
    _MOVIEPY_AVAILABLE = False

# Resolve a font that actually exists on this system.
_DEFAULT_FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"


def _require_moviepy() -> None:
    if not _MOVIEPY_AVAILABLE:
        raise ImportError(
            "MoviePy is not installed. Run: pip install moviepy"
        )


def _output_dir() -> Path:
    from config import settings
    d = Path(getattr(settings, "creative_output_dir", "data/creative"))
    d.mkdir(parents=True, exist_ok=True)
    return d


# ── Stitching ─────────────────────────────────────────────────────────────────

def stitch_clips(
    clip_paths: list[str],
    transition_duration: float = 1.0,
    output_path: Optional[str] = None,
) -> dict:
    """Concatenate video clips with cross-fade transitions.

    Args:
        clip_paths: Ordered list of MP4 file paths.
        transition_duration: Cross-fade duration in seconds.
        output_path: Optional output path.  Auto-generated if omitted.

    Returns dict with ``path`` and ``total_duration``.
    """
    _require_moviepy()

    clips = [VideoFileClip(p) for p in clip_paths]

    # Apply cross-fade between consecutive clips
    if transition_duration > 0 and len(clips) > 1:
        processed = [clips[0]]
        for clip in clips[1:]:
            clip = clip.with_start(
                processed[-1].end - transition_duration
            ).with_effects([vfx.CrossFadeIn(transition_duration)])
            processed.append(clip)
        final = CompositeVideoClip(processed)
    else:
        final = concatenate_videoclips(clips, method="compose")

    uid = uuid.uuid4().hex[:12]
    out = Path(output_path) if output_path else _output_dir() / f"stitched_{uid}.mp4"
    final.write_videofile(str(out), codec="libx264", audio_codec="aac", logger=None)

    total_duration = final.duration
    # Clean up
    for c in clips:
        c.close()

    return {
        "success": True,
        "path": str(out),
        "total_duration": total_duration,
        "clip_count": len(clip_paths),
    }


# ── Audio overlay ─────────────────────────────────────────────────────────────

def overlay_audio(
    video_path: str,
    audio_path: str,
    output_path: Optional[str] = None,
    volume: float = 1.0,
) -> dict:
    """Mix an audio track onto a video file.

    The audio is trimmed or looped to match the video duration.
    """
    _require_moviepy()

    video = VideoFileClip(video_path)
    audio = AudioFileClip(audio_path)

    # Trim audio to video length
    if audio.duration > video.duration:
        audio = audio.subclipped(0, video.duration)

    if volume != 1.0:
        audio = audio.with_volume_scaled(volume)

    video = video.with_audio(audio)

    uid = uuid.uuid4().hex[:12]
    out = Path(output_path) if output_path else _output_dir() / f"mixed_{uid}.mp4"
    video.write_videofile(str(out), codec="libx264", audio_codec="aac", logger=None)

    result_duration = video.duration
    video.close()
    audio.close()

    return {
        "success": True,
        "path": str(out),
        "duration": result_duration,
    }


# ── Title cards ───────────────────────────────────────────────────────────────

def add_title_card(
    video_path: str,
    title: str,
    subtitle: str = "",
    duration: float = 4.0,
    position: str = "start",
    output_path: Optional[str] = None,
) -> dict:
    """Add a title card at the start or end of a video.

    Args:
        video_path: Source video path.
        title: Title text.
        subtitle: Optional subtitle text.
        duration: Title card display duration in seconds.
        position: "start" or "end".
    """
    _require_moviepy()

    video = VideoFileClip(video_path)
    w, h = video.size

    # Build title card as a text clip on black background
    txt = TextClip(
        text=title,
        font_size=60,
        color="white",
        size=(w, h),
        method="caption",
        font=_DEFAULT_FONT,
    ).with_duration(duration)

    clips = [txt, video] if position == "start" else [video, txt]
    final = concatenate_videoclips(clips, method="compose")

    uid = uuid.uuid4().hex[:12]
    out = Path(output_path) if output_path else _output_dir() / f"titled_{uid}.mp4"
    final.write_videofile(str(out), codec="libx264", audio_codec="aac", logger=None)

    result_duration = final.duration
    video.close()

    return {
        "success": True,
        "path": str(out),
        "duration": result_duration,
        "title": title,
    }


# ── Subtitles / captions ─────────────────────────────────────────────────────

def add_subtitles(
    video_path: str,
    captions: list[dict],
    output_path: Optional[str] = None,
) -> dict:
    """Burn subtitle captions onto a video.

    Args:
        captions: List of dicts with ``text``, ``start``, ``end`` keys
                  (times in seconds).
    """
    _require_moviepy()

    video = VideoFileClip(video_path)
    w, h = video.size

    text_clips = []
    for cap in captions:
        txt = (
            TextClip(
                text=cap["text"],
                font_size=36,
                color="white",
                stroke_color="black",
                stroke_width=2,
                size=(w - 40, None),
                method="caption",
                font=_DEFAULT_FONT,
            )
            .with_start(cap["start"])
            .with_end(cap["end"])
            .with_position(("center", h - 100))
        )
        text_clips.append(txt)

    final = CompositeVideoClip([video] + text_clips)

    uid = uuid.uuid4().hex[:12]
    out = Path(output_path) if output_path else _output_dir() / f"subtitled_{uid}.mp4"
    final.write_videofile(str(out), codec="libx264", audio_codec="aac", logger=None)

    result_duration = final.duration
    video.close()

    return {
        "success": True,
        "path": str(out),
        "duration": result_duration,
        "caption_count": len(captions),
    }


# ── Final export helper ──────────────────────────────────────────────────────

def export_final(
    video_path: str,
    output_path: Optional[str] = None,
    codec: str = "libx264",
    audio_codec: str = "aac",
    bitrate: str = "8000k",
) -> dict:
    """Re-encode a video with specific codec settings for distribution."""
    _require_moviepy()

    video = VideoFileClip(video_path)
    uid = uuid.uuid4().hex[:12]
    out = Path(output_path) if output_path else _output_dir() / f"final_{uid}.mp4"
    video.write_videofile(
        str(out), codec=codec, audio_codec=audio_codec,
        bitrate=bitrate, logger=None,
    )

    result_duration = video.duration
    video.close()

    return {
        "success": True,
        "path": str(out),
        "duration": result_duration,
        "codec": codec,
    }


# ── Tool catalogue ────────────────────────────────────────────────────────────

ASSEMBLER_TOOL_CATALOG: dict[str, dict] = {
    "stitch_clips": {
        "name": "Stitch Clips",
        "description": "Concatenate video clips with cross-fade transitions",
        "fn": stitch_clips,
    },
    "overlay_audio": {
        "name": "Overlay Audio",
        "description": "Mix a music track onto a video",
        "fn": overlay_audio,
    },
    "add_title_card": {
        "name": "Add Title Card",
        "description": "Add a title card at the start or end of a video",
        "fn": add_title_card,
    },
    "add_subtitles": {
        "name": "Add Subtitles",
        "description": "Burn subtitle captions onto a video",
        "fn": add_subtitles,
    },
    "export_final": {
        "name": "Export Final",
        "description": "Re-encode video with specific codec settings",
        "fn": export_final,
    },
}
