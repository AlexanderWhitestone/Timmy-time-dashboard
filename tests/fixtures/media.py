"""Real media file fixtures for integration tests.

Generates actual PNG images, WAV audio files, and MP4 video clips
using numpy, Pillow, and MoviePy — no AI models required.
"""

from __future__ import annotations

import wave
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw


# ── Color palettes for visual variety ─────────────────────────────────────────

SCENE_COLORS = [
    (30, 60, 120),    # dark blue  — "night sky"
    (200, 100, 30),   # warm orange — "sunrise"
    (50, 150, 50),    # forest green — "mountain forest"
    (20, 120, 180),   # teal blue — "river"
    (180, 60, 60),    # crimson — "sunset"
    (40, 40, 80),     # deep purple — "twilight"
]


def make_storyboard_frame(
    path: Path,
    label: str,
    color: tuple[int, int, int] = (60, 60, 60),
    width: int = 320,
    height: int = 180,
) -> Path:
    """Create a real PNG image with a colored background and text label.

    Returns the path to the written file.
    """
    img = Image.new("RGB", (width, height), color=color)
    draw = ImageDraw.Draw(img)

    # Draw label text in white, centered
    bbox = draw.textbbox((0, 0), label)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = (width - tw) // 2
    y = (height - th) // 2
    draw.text((x, y), label, fill=(255, 255, 255))

    # Add a border
    draw.rectangle([2, 2, width - 3, height - 3], outline=(255, 255, 255), width=2)

    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)
    return path


def make_storyboard(
    output_dir: Path,
    scene_labels: list[str],
    width: int = 320,
    height: int = 180,
) -> list[Path]:
    """Generate a full storyboard — one PNG per scene."""
    frames = []
    for i, label in enumerate(scene_labels):
        color = SCENE_COLORS[i % len(SCENE_COLORS)]
        path = output_dir / f"frame_{i:03d}.png"
        make_storyboard_frame(path, label, color=color, width=width, height=height)
        frames.append(path)
    return frames


def make_audio_track(
    path: Path,
    duration_seconds: float = 10.0,
    sample_rate: int = 44100,
    frequency: float = 440.0,
    fade_in: float = 0.5,
    fade_out: float = 0.5,
) -> Path:
    """Create a real WAV audio file — a sine wave tone with fade in/out.

    Good enough to verify audio overlay, mixing, and codec encoding.
    """
    n_samples = int(sample_rate * duration_seconds)
    t = np.linspace(0, duration_seconds, n_samples, endpoint=False)

    # Generate a sine wave with slight frequency variation for realism
    signal = np.sin(2 * np.pi * frequency * t)

    # Add a second harmonic for richness
    signal += 0.3 * np.sin(2 * np.pi * frequency * 2 * t)

    # Fade in/out
    fade_in_samples = int(sample_rate * fade_in)
    fade_out_samples = int(sample_rate * fade_out)
    if fade_in_samples > 0:
        signal[:fade_in_samples] *= np.linspace(0, 1, fade_in_samples)
    if fade_out_samples > 0:
        signal[-fade_out_samples:] *= np.linspace(1, 0, fade_out_samples)

    # Normalize and convert to 16-bit PCM
    signal = (signal / np.max(np.abs(signal)) * 32767 * 0.8).astype(np.int16)

    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(signal.tobytes())

    return path


def make_video_clip(
    path: Path,
    duration_seconds: float = 3.0,
    fps: int = 12,
    width: int = 320,
    height: int = 180,
    color_start: tuple[int, int, int] = (30, 30, 80),
    color_end: tuple[int, int, int] = (80, 30, 30),
    label: str = "",
) -> Path:
    """Create a real MP4 video clip with a color gradient animation.

    Frames transition smoothly from color_start to color_end,
    producing a visible animation that's easy to visually verify.
    """
    from moviepy import ImageSequenceClip

    n_frames = int(duration_seconds * fps)
    frames = []

    for i in range(n_frames):
        t = i / max(1, n_frames - 1)
        r = int(color_start[0] + (color_end[0] - color_start[0]) * t)
        g = int(color_start[1] + (color_end[1] - color_start[1]) * t)
        b = int(color_start[2] + (color_end[2] - color_start[2]) * t)

        img = Image.new("RGB", (width, height), color=(r, g, b))

        if label:
            draw = ImageDraw.Draw(img)
            draw.text((10, 10), label, fill=(255, 255, 255))
            # Frame counter
            draw.text((10, height - 20), f"f{i}/{n_frames}", fill=(200, 200, 200))

        frames.append(np.array(img))

    path.parent.mkdir(parents=True, exist_ok=True)
    clip = ImageSequenceClip(frames, fps=fps)
    clip.write_videofile(str(path), codec="libx264", audio=False, logger=None)

    return path


def make_scene_clips(
    output_dir: Path,
    scene_labels: list[str],
    duration_per_clip: float = 3.0,
    fps: int = 12,
    width: int = 320,
    height: int = 180,
) -> list[Path]:
    """Generate one video clip per scene, each with a distinct color animation."""
    clips = []
    for i, label in enumerate(scene_labels):
        c1 = SCENE_COLORS[i % len(SCENE_COLORS)]
        c2 = SCENE_COLORS[(i + 1) % len(SCENE_COLORS)]
        path = output_dir / f"clip_{i:03d}.mp4"
        make_video_clip(
            path, duration_seconds=duration_per_clip, fps=fps,
            width=width, height=height,
            color_start=c1, color_end=c2, label=label,
        )
        clips.append(path)
    return clips
