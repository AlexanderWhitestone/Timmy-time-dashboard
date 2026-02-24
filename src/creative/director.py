"""Creative Director — multi-persona pipeline for 3+ minute creative works.

Orchestrates Pixel (images), Lyra (music), and Reel (video) to produce
complete music videos, cinematic shorts, and other creative works.

Pipeline stages:
1. Script   — Generate scene descriptions and lyrics
2. Storyboard — Generate keyframe images (Pixel)
3. Music    — Generate soundtrack (Lyra)
4. Video    — Generate clips per scene (Reel)
5. Assembly — Stitch clips + overlay audio (MoviePy)
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class CreativeProject:
    """Tracks all assets and state for a creative production."""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    title: str = ""
    description: str = ""
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    status: str = "planning"  # planning|scripting|storyboard|music|video|assembly|complete|failed

    # Pipeline outputs
    scenes: list[dict] = field(default_factory=list)
    lyrics: str = ""
    storyboard_frames: list[dict] = field(default_factory=list)
    music_track: Optional[dict] = None
    video_clips: list[dict] = field(default_factory=list)
    final_video: Optional[dict] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id, "title": self.title,
            "description": self.description,
            "created_at": self.created_at, "status": self.status,
            "scene_count": len(self.scenes),
            "has_storyboard": len(self.storyboard_frames) > 0,
            "has_music": self.music_track is not None,
            "clip_count": len(self.video_clips),
            "has_final": self.final_video is not None,
        }


# In-memory project store
_projects: dict[str, CreativeProject] = {}


def _project_dir(project_id: str) -> Path:
    from config import settings
    d = Path(getattr(settings, "creative_output_dir", "data/creative")) / project_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def _save_project(project: CreativeProject) -> None:
    """Persist project metadata to disk."""
    path = _project_dir(project.id) / "project.json"
    path.write_text(json.dumps(project.to_dict(), indent=2))


# ── Project management ────────────────────────────────────────────────────────

def create_project(
    title: str,
    description: str,
    scenes: Optional[list[dict]] = None,
    lyrics: str = "",
) -> dict:
    """Create a new creative project.

    Args:
        title: Project title.
        description: High-level creative brief.
        scenes: Optional pre-written scene descriptions.
                Each scene is a dict with ``description`` key.
        lyrics: Optional song lyrics for the soundtrack.

    Returns dict with project metadata.
    """
    project = CreativeProject(
        title=title,
        description=description,
        scenes=scenes or [],
        lyrics=lyrics,
    )
    _projects[project.id] = project
    _save_project(project)
    logger.info("Creative project created: %s (%s)", project.id, title)
    return {"success": True, "project": project.to_dict()}


def get_project(project_id: str) -> Optional[dict]:
    """Get project metadata."""
    project = _projects.get(project_id)
    if project:
        return project.to_dict()
    return None


def list_projects() -> list[dict]:
    """List all creative projects."""
    return [p.to_dict() for p in _projects.values()]


# ── Pipeline steps ────────────────────────────────────────────────────────────

def run_storyboard(project_id: str) -> dict:
    """Generate storyboard frames for all scenes in a project.

    Calls Pixel's generate_storyboard tool.
    """
    project = _projects.get(project_id)
    if not project:
        return {"success": False, "error": "Project not found"}
    if not project.scenes:
        return {"success": False, "error": "No scenes defined"}

    project.status = "storyboard"

    from tools.image_tools import generate_storyboard

    scene_descriptions = [s["description"] for s in project.scenes]
    result = generate_storyboard(scene_descriptions)

    if result["success"]:
        project.storyboard_frames = result["frames"]
        _save_project(project)

    return result


def run_music(
    project_id: str,
    genre: str = "pop",
    duration: Optional[int] = None,
) -> dict:
    """Generate the soundtrack for a project.

    Calls Lyra's generate_song tool.
    """
    project = _projects.get(project_id)
    if not project:
        return {"success": False, "error": "Project not found"}

    project.status = "music"

    from tools.music_tools import generate_song

    # Default duration: ~15s per scene, minimum 60s
    target_duration = duration or max(60, len(project.scenes) * 15)

    result = generate_song(
        lyrics=project.lyrics,
        genre=genre,
        duration=target_duration,
        title=project.title,
    )

    if result["success"]:
        project.music_track = result
        _save_project(project)

    return result


def run_video_generation(project_id: str) -> dict:
    """Generate video clips for each scene.

    Uses storyboard frames (image-to-video) if available,
    otherwise falls back to text-to-video.
    """
    project = _projects.get(project_id)
    if not project:
        return {"success": False, "error": "Project not found"}
    if not project.scenes:
        return {"success": False, "error": "No scenes defined"}

    project.status = "video"

    from tools.video_tools import generate_video_clip, image_to_video

    clips = []
    for i, scene in enumerate(project.scenes):
        desc = scene["description"]

        # Prefer image-to-video if storyboard frame exists
        if i < len(project.storyboard_frames):
            frame = project.storyboard_frames[i]
            result = image_to_video(
                image_path=frame["path"],
                prompt=desc,
                duration=scene.get("duration", 5),
            )
        else:
            result = generate_video_clip(
                prompt=desc,
                duration=scene.get("duration", 5),
            )

        result["scene_index"] = i
        clips.append(result)

    project.video_clips = clips
    _save_project(project)

    return {
        "success": True,
        "clip_count": len(clips),
        "clips": clips,
    }


def run_assembly(project_id: str, transition_duration: float = 1.0) -> dict:
    """Assemble all clips into the final video with music.

    Pipeline:
    1. Stitch clips with transitions
    2. Overlay music track
    3. Add title card
    """
    project = _projects.get(project_id)
    if not project:
        return {"success": False, "error": "Project not found"}
    if not project.video_clips:
        return {"success": False, "error": "No video clips generated"}

    project.status = "assembly"

    from creative.assembler import stitch_clips, overlay_audio, add_title_card

    # 1. Stitch clips
    clip_paths = [c["path"] for c in project.video_clips if c.get("success")]
    if not clip_paths:
        return {"success": False, "error": "No successful clips to assemble"}

    stitched = stitch_clips(clip_paths, transition_duration=transition_duration)
    if not stitched["success"]:
        return stitched

    # 2. Overlay music (if available)
    current_video = stitched["path"]
    if project.music_track and project.music_track.get("path"):
        mixed = overlay_audio(current_video, project.music_track["path"])
        if mixed["success"]:
            current_video = mixed["path"]

    # 3. Add title card
    titled = add_title_card(current_video, title=project.title)
    if titled["success"]:
        current_video = titled["path"]

    project.final_video = {
        "path": current_video,
        "duration": titled.get("duration", stitched["total_duration"]),
    }
    project.status = "complete"
    _save_project(project)

    return {
        "success": True,
        "path": current_video,
        "duration": project.final_video["duration"],
        "project_id": project_id,
    }


def run_full_pipeline(
    title: str,
    description: str,
    scenes: list[dict],
    lyrics: str = "",
    genre: str = "pop",
) -> dict:
    """Run the entire creative pipeline end-to-end.

    This is the top-level orchestration function that:
    1. Creates the project
    2. Generates storyboard frames
    3. Generates music
    4. Generates video clips
    5. Assembles the final video

    Args:
        title: Project title.
        description: Creative brief.
        scenes: List of scene dicts with ``description`` keys.
        lyrics: Song lyrics for the soundtrack.
        genre: Music genre.

    Returns dict with final video path and project metadata.
    """
    # Create project
    project_result = create_project(title, description, scenes, lyrics)
    if not project_result["success"]:
        return project_result
    project_id = project_result["project"]["id"]

    # Run pipeline steps
    steps = [
        ("storyboard", lambda: run_storyboard(project_id)),
        ("music", lambda: run_music(project_id, genre=genre)),
        ("video", lambda: run_video_generation(project_id)),
        ("assembly", lambda: run_assembly(project_id)),
    ]

    for step_name, step_fn in steps:
        logger.info("Creative pipeline step: %s (project %s)", step_name, project_id)
        result = step_fn()
        if not result.get("success"):
            project = _projects.get(project_id)
            if project:
                project.status = "failed"
                _save_project(project)
            return {
                "success": False,
                "failed_step": step_name,
                "error": result.get("error", "Unknown error"),
                "project_id": project_id,
            }

    project = _projects.get(project_id)
    return {
        "success": True,
        "project_id": project_id,
        "final_video": project.final_video if project else None,
        "project": project.to_dict() if project else None,
    }


# ── Tool catalogue ────────────────────────────────────────────────────────────

DIRECTOR_TOOL_CATALOG: dict[str, dict] = {
    "create_project": {
        "name": "Create Creative Project",
        "description": "Create a new creative production project",
        "fn": create_project,
    },
    "run_storyboard": {
        "name": "Generate Storyboard",
        "description": "Generate keyframe images for all project scenes",
        "fn": run_storyboard,
    },
    "run_music": {
        "name": "Generate Music",
        "description": "Generate the project soundtrack with vocals and instrumentals",
        "fn": run_music,
    },
    "run_video_generation": {
        "name": "Generate Video Clips",
        "description": "Generate video clips for each project scene",
        "fn": run_video_generation,
    },
    "run_assembly": {
        "name": "Assemble Final Video",
        "description": "Stitch clips, overlay music, and add title cards",
        "fn": run_assembly,
    },
    "run_full_pipeline": {
        "name": "Run Full Pipeline",
        "description": "Execute entire creative pipeline end-to-end",
        "fn": run_full_pipeline,
    },
}
