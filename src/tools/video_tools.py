"""Video generation tools — Reel persona.

Uses Wan 2.1 (via HuggingFace diffusers) for text-to-video and
image-to-video generation.  Heavy imports are lazy.
"""

from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Lazy-loaded pipeline singletons
_t2v_pipeline = None
_i2v_pipeline = None


def _get_t2v_pipeline():
    """Lazy-load the text-to-video pipeline (Wan 2.1)."""
    global _t2v_pipeline
    if _t2v_pipeline is not None:
        return _t2v_pipeline

    try:
        import torch
        from diffusers import DiffusionPipeline
    except ImportError:
        raise ImportError(
            "Creative dependencies not installed. "
            "Run: pip install 'timmy-time[creative]'"
        )

    from config import settings
    model_id = getattr(settings, "wan_model_id", "Wan-AI/Wan2.1-T2V-1.3B")
    device = "cuda" if torch.cuda.is_available() else "cpu"
    dtype = torch.float16 if device == "cuda" else torch.float32

    logger.info("Loading video model %s on %s …", model_id, device)
    _t2v_pipeline = DiffusionPipeline.from_pretrained(
        model_id, torch_dtype=dtype,
    ).to(device)
    logger.info("Video model loaded.")
    return _t2v_pipeline


def _output_dir() -> Path:
    from config import settings
    d = Path(getattr(settings, "video_output_dir", "data/video"))
    d.mkdir(parents=True, exist_ok=True)
    return d


def _save_metadata(video_path: Path, meta: dict) -> Path:
    meta_path = video_path.with_suffix(".json")
    meta_path.write_text(json.dumps(meta, indent=2))
    return meta_path


def _export_frames_to_mp4(frames, out_path: Path, fps: int = 24) -> None:
    """Export a list of PIL Image frames to an MP4 file using moviepy."""
    import numpy as np
    from moviepy import ImageSequenceClip

    frame_arrays = [np.array(f) for f in frames]
    clip = ImageSequenceClip(frame_arrays, fps=fps)
    clip.write_videofile(
        str(out_path), codec="libx264", audio=False, logger=None,
    )


# ── Resolution presets ────────────────────────────────────────────────────────

RESOLUTION_PRESETS = {
    "480p": (854, 480),
    "720p": (1280, 720),
}

VIDEO_STYLES = [
    "cinematic", "anime", "documentary", "abstract",
    "timelapse", "slow-motion", "music-video", "vlog",
]


# ── Public tools ──────────────────────────────────────────────────────────────

def generate_video_clip(
    prompt: str,
    duration: int = 5,
    resolution: str = "480p",
    fps: int = 24,
    seed: Optional[int] = None,
) -> dict:
    """Generate a short video clip from a text prompt.

    Args:
        prompt: Text description of the desired video.
        duration: Target duration in seconds (2–10).
        resolution: "480p" or "720p".
        fps: Frames per second.
        seed: Optional seed for reproducibility.

    Returns dict with ``path``, ``duration``, ``resolution``.
    """
    pipe = _get_t2v_pipeline()
    import torch

    duration = max(2, min(10, duration))
    w, h = RESOLUTION_PRESETS.get(resolution, RESOLUTION_PRESETS["480p"])
    num_frames = duration * fps

    generator = torch.Generator(device=pipe.device)
    if seed is not None:
        generator.manual_seed(seed)

    logger.info("Generating %ds video at %s …", duration, resolution)
    result = pipe(
        prompt=prompt,
        num_frames=num_frames,
        width=w,
        height=h,
        generator=generator,
    )
    frames = result.frames[0] if hasattr(result, "frames") else result.images

    uid = uuid.uuid4().hex[:12]
    out_path = _output_dir() / f"{uid}.mp4"
    _export_frames_to_mp4(frames, out_path, fps=fps)

    meta = {
        "id": uid, "prompt": prompt, "duration": duration,
        "resolution": resolution, "fps": fps, "seed": seed,
    }
    _save_metadata(out_path, meta)

    return {"success": True, "path": str(out_path), **meta}


def image_to_video(
    image_path: str,
    prompt: str = "",
    duration: int = 5,
    fps: int = 24,
) -> dict:
    """Animate a still image into a video clip.

    Args:
        image_path: Path to the source image.
        prompt: Optional motion / style guidance.
        duration: Target duration in seconds (2–10).
    """
    pipe = _get_t2v_pipeline()
    from PIL import Image

    duration = max(2, min(10, duration))
    img = Image.open(image_path).convert("RGB")
    num_frames = duration * fps

    logger.info("Animating image %s → %ds video …", image_path, duration)
    result = pipe(
        prompt=prompt or "animate this image with natural motion",
        image=img,
        num_frames=num_frames,
    )
    frames = result.frames[0] if hasattr(result, "frames") else result.images

    uid = uuid.uuid4().hex[:12]
    out_path = _output_dir() / f"{uid}.mp4"
    _export_frames_to_mp4(frames, out_path, fps=fps)

    meta = {
        "id": uid, "source_image": image_path,
        "prompt": prompt, "duration": duration, "fps": fps,
    }
    _save_metadata(out_path, meta)

    return {"success": True, "path": str(out_path), **meta}


def list_video_styles() -> dict:
    """Return supported video style presets."""
    return {"success": True, "styles": VIDEO_STYLES, "resolutions": list(RESOLUTION_PRESETS.keys())}


# ── Tool catalogue ────────────────────────────────────────────────────────────

VIDEO_TOOL_CATALOG: dict[str, dict] = {
    "generate_video_clip": {
        "name": "Generate Video Clip",
        "description": "Generate a short video clip from a text prompt using Wan 2.1",
        "fn": generate_video_clip,
    },
    "image_to_video": {
        "name": "Image to Video",
        "description": "Animate a still image into a video clip",
        "fn": image_to_video,
    },
    "list_video_styles": {
        "name": "List Video Styles",
        "description": "List supported video style presets and resolutions",
        "fn": list_video_styles,
    },
}
