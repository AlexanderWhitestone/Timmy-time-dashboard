"""Image generation tools — Pixel persona.

Uses FLUX.2 Klein 4B (or configurable model) via HuggingFace diffusers
for text-to-image generation, storyboard frames, and variations.

All heavy imports are lazy so the module loads instantly even without
a GPU or the ``creative`` extra installed.
"""

from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Lazy-loaded pipeline singleton
_pipeline = None


def _get_pipeline():
    """Lazy-load the FLUX diffusers pipeline."""
    global _pipeline
    if _pipeline is not None:
        return _pipeline

    try:
        import torch
        from diffusers import FluxPipeline
    except ImportError:
        raise ImportError(
            "Creative dependencies not installed. "
            "Run: pip install 'timmy-time[creative]'"
        )

    from config import settings

    model_id = getattr(settings, "flux_model_id", "black-forest-labs/FLUX.1-schnell")
    device = "cuda" if torch.cuda.is_available() else "cpu"
    dtype = torch.float16 if device == "cuda" else torch.float32

    logger.info("Loading image model %s on %s …", model_id, device)
    _pipeline = FluxPipeline.from_pretrained(
        model_id, torch_dtype=dtype,
    ).to(device)
    logger.info("Image model loaded.")
    return _pipeline


def _output_dir() -> Path:
    from config import settings
    d = Path(getattr(settings, "image_output_dir", "data/images"))
    d.mkdir(parents=True, exist_ok=True)
    return d


def _save_metadata(image_path: Path, meta: dict) -> Path:
    meta_path = image_path.with_suffix(".json")
    meta_path.write_text(json.dumps(meta, indent=2))
    return meta_path


# ── Public tools ──────────────────────────────────────────────────────────────

def generate_image(
    prompt: str,
    negative_prompt: str = "",
    width: int = 1024,
    height: int = 1024,
    steps: int = 4,
    seed: Optional[int] = None,
) -> dict:
    """Generate an image from a text prompt.

    Returns dict with ``path``, ``width``, ``height``, and ``prompt``.
    """
    pipe = _get_pipeline()
    import torch

    generator = torch.Generator(device=pipe.device)
    if seed is not None:
        generator.manual_seed(seed)

    image = pipe(
        prompt=prompt,
        negative_prompt=negative_prompt or None,
        width=width,
        height=height,
        num_inference_steps=steps,
        generator=generator,
    ).images[0]

    uid = uuid.uuid4().hex[:12]
    out_path = _output_dir() / f"{uid}.png"
    image.save(out_path)

    meta = {
        "id": uid, "prompt": prompt, "negative_prompt": negative_prompt,
        "width": width, "height": height, "steps": steps, "seed": seed,
    }
    _save_metadata(out_path, meta)

    return {"success": True, "path": str(out_path), **meta}


def generate_storyboard(
    scenes: list[str],
    width: int = 1024,
    height: int = 576,
    steps: int = 4,
) -> dict:
    """Generate a storyboard: one keyframe image per scene description.

    Args:
        scenes: List of scene description strings.

    Returns dict with list of generated frame paths.
    """
    frames = []
    for i, scene in enumerate(scenes):
        result = generate_image(
            prompt=scene, width=width, height=height, steps=steps,
        )
        result["scene_index"] = i
        result["scene_description"] = scene
        frames.append(result)
    return {"success": True, "frame_count": len(frames), "frames": frames}


def image_variations(
    prompt: str,
    count: int = 4,
    width: int = 1024,
    height: int = 1024,
    steps: int = 4,
) -> dict:
    """Generate multiple variations of the same prompt with different seeds."""
    import random
    variations = []
    for _ in range(count):
        seed = random.randint(0, 2**32 - 1)
        result = generate_image(
            prompt=prompt, width=width, height=height,
            steps=steps, seed=seed,
        )
        variations.append(result)
    return {"success": True, "count": len(variations), "variations": variations}


# ── Tool catalogue ────────────────────────────────────────────────────────────

IMAGE_TOOL_CATALOG: dict[str, dict] = {
    "generate_image": {
        "name": "Generate Image",
        "description": "Generate an image from a text prompt using FLUX",
        "fn": generate_image,
    },
    "generate_storyboard": {
        "name": "Generate Storyboard",
        "description": "Generate keyframe images for a sequence of scenes",
        "fn": generate_storyboard,
    },
    "image_variations": {
        "name": "Image Variations",
        "description": "Generate multiple variations of the same prompt",
        "fn": image_variations,
    },
}
