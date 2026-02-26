"""Creative Studio dashboard route — /creative endpoints.

Provides a dashboard page for the creative pipeline: image generation,
music generation, video generation, and the full director pipeline.
"""

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter(tags=["creative"])
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


@router.get("/creative/ui", response_class=HTMLResponse)
async def creative_studio(request: Request):
    """Render the Creative Studio page."""
    # Collect existing outputs
    image_dir = Path("data/images")
    music_dir = Path("data/music")
    video_dir = Path("data/video")
    creative_dir = Path("data/creative")

    images = sorted(image_dir.glob("*.png"), key=lambda p: p.stat().st_mtime, reverse=True)[:20] if image_dir.exists() else []
    music_files = sorted(music_dir.glob("*.wav"), key=lambda p: p.stat().st_mtime, reverse=True)[:20] if music_dir.exists() else []
    videos = sorted(video_dir.glob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)[:20] if video_dir.exists() else []

    # Load projects
    projects = []
    if creative_dir.exists():
        for proj_dir in sorted(creative_dir.iterdir(), reverse=True):
            meta_path = proj_dir / "project.json"
            if meta_path.exists():
                import json
                projects.append(json.loads(meta_path.read_text()))

    return templates.TemplateResponse(
        request,
        "creative.html",
        {
            "page_title": "Creative Studio",
            "images": [{"name": p.name, "path": str(p)} for p in images],
            "music_files": [{"name": p.name, "path": str(p)} for p in music_files],
            "videos": [{"name": p.name, "path": str(p)} for p in videos],
            "projects": projects[:10],
            "image_count": len(images),
            "music_count": len(music_files),
            "video_count": len(videos),
            "project_count": len(projects),
        },
    )


@router.get("/creative/api/projects")
async def creative_projects_api():
    """Return creative projects as JSON."""
    try:
        from creative.director import list_projects
        return {"projects": list_projects()}
    except ImportError:
        return {"projects": []}


@router.get("/creative/api/genres")
async def creative_genres_api():
    """Return supported music genres."""
    try:
        from creative.tools.music_tools import GENRES
        return {"genres": GENRES}
    except ImportError:
        return {"genres": []}


@router.get("/creative/api/video-styles")
async def creative_video_styles_api():
    """Return supported video styles and resolutions."""
    try:
        from creative.tools.video_tools import VIDEO_STYLES, RESOLUTION_PRESETS
        return {
            "styles": VIDEO_STYLES,
            "resolutions": list(RESOLUTION_PRESETS.keys()),
        }
    except ImportError:
        return {"styles": [], "resolutions": []}
