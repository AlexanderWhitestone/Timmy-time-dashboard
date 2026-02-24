# Plan: Full Creative & DevOps Capabilities for Timmy

## Overview

Add five major capability domains to Timmy's agent system, turning it into a
sovereign creative studio and full-stack DevOps operator. All tools are
open-source, self-hosted, and GPU-accelerated where needed.

---

## Phase 1: Git & DevOps Tools (Forge + Helm personas)

**Goal:** Timmy can observe local/remote repos, read code, create branches,
stage changes, commit, diff, log, and manage PRs — all through the swarm
task system with Spark event capture.

### New module: `src/tools/git_tools.py`

Tools to add (using **GitPython** — BSD-3, `pip install GitPython`):

| Tool | Function | Persona Access |
|---|---|---|
| `git_clone` | Clone a remote repo to local path | Forge, Helm |
| `git_status` | Show working tree status | Forge, Helm, Timmy |
| `git_diff` | Show staged/unstaged diffs | Forge, Helm, Timmy |
| `git_log` | Show recent commit history | Forge, Helm, Echo, Timmy |
| `git_branch` | List/create/switch branches | Forge, Helm |
| `git_add` | Stage files for commit | Forge, Helm |
| `git_commit` | Create a commit with message | Forge, Helm |
| `git_push` | Push to remote | Forge, Helm |
| `git_pull` | Pull from remote | Forge, Helm |
| `git_blame` | Show line-by-line authorship | Forge, Echo |
| `git_stash` | Stash/pop changes | Forge, Helm |

### Changes to existing files

- **`src/timmy/tools.py`** — Add `create_git_tools()` factory, wire into
  `PERSONA_TOOLKITS` for Forge and Helm
- **`src/swarm/tool_executor.py`** — Enhance `_infer_tools_needed()` with
  git keywords (commit, branch, push, pull, diff, clone, merge)
- **`src/config.py`** — Add `git_default_repo_dir: str = "~/repos"` setting
- **`src/spark/engine.py`** — Add `on_tool_executed()` method to capture
  individual tool invocations (not just task-level events)
- **`src/swarm/personas.py`** — Add git-related keywords to Forge and Helm
  preferred_keywords

### New dependency

```toml
# pyproject.toml
dependencies = [
    ...,
    "GitPython>=3.1.40",
]
```

### Dashboard

- **`/tools`** page updated to show git tools in the catalog
- Git tool usage stats visible per agent

### Tests

- `tests/test_git_tools.py` — test all git tool functions against tmp repos
- Mock GitPython's `Repo` class for unit tests

---

## Phase 2: Image Generation (new "Pixel" persona)

**Goal:** Generate storyboard frames and standalone images from text prompts
using FLUX.2 Klein 4B locally.

### New persona: Pixel — Visual Architect

```python
"pixel": {
    "id": "pixel",
    "name": "Pixel",
    "role": "Visual Architect",
    "description": "Image generation, storyboard frames, and visual design.",
    "capabilities": "image-generation,storyboard,design",
    "rate_sats": 80,
    "bid_base": 60,
    "bid_jitter": 20,
    "preferred_keywords": [
        "image", "picture", "photo", "draw", "illustration",
        "storyboard", "frame", "visual", "design", "generate",
        "portrait", "landscape", "scene", "artwork",
    ],
}
```

### New module: `src/tools/image_tools.py`

Tools (using **diffusers** + **FLUX.2 Klein 4B** — Apache 2.0):

| Tool | Function |
|---|---|
| `generate_image` | Text-to-image generation (returns file path) |
| `generate_storyboard` | Generate N frames from scene descriptions |
| `image_variations` | Generate variations of an existing image |

### Architecture

```
generate_image(prompt, width=1024, height=1024, steps=4)
    → loads FLUX.2 Klein via diffusers FluxPipeline
    → saves to data/images/{uuid}.png
    → returns path + metadata
```

- Model loaded lazily on first use, kept in memory for subsequent calls
- Falls back to CPU generation (slower) if no GPU
- Output saved to `data/images/` with metadata JSON sidecar

### New dependency (optional extra)

```toml
[project.optional-dependencies]
creative = [
    "diffusers>=0.30.0",
    "transformers>=4.40.0",
    "accelerate>=0.30.0",
    "torch>=2.2.0",
    "safetensors>=0.4.0",
]
```

### Config

```python
# config.py additions
flux_model_id: str = "black-forest-labs/FLUX.2-klein-4b"
image_output_dir: str = "data/images"
image_default_steps: int = 4
```

### Dashboard

- `/creative/ui` — new Creative Studio page (image gallery + generation form)
- HTMX-powered: submit prompt, poll for result, display inline
- Gallery view of all generated images with metadata

### Tests

- `tests/test_image_tools.py` — mock diffusers pipeline, test prompt handling,
  file output, storyboard generation

---

## Phase 3: Music Generation (new "Lyra" persona)

**Goal:** Generate full songs with vocals, instrumentals, and lyrics using
ACE-Step 1.5 locally.

### New persona: Lyra — Sound Weaver

```python
"lyra": {
    "id": "lyra",
    "name": "Lyra",
    "role": "Sound Weaver",
    "description": "Music and song generation with vocals, instrumentals, and lyrics.",
    "capabilities": "music-generation,vocals,composition",
    "rate_sats": 90,
    "bid_base": 70,
    "bid_jitter": 20,
    "preferred_keywords": [
        "music", "song", "sing", "vocal", "instrumental",
        "melody", "beat", "track", "compose", "lyrics",
        "audio", "sound", "album", "remix",
    ],
}
```

### New module: `src/tools/music_tools.py`

Tools (using **ACE-Step 1.5** — Apache 2.0, `pip install ace-step`):

| Tool | Function |
|---|---|
| `generate_song` | Text/lyrics → full song (vocals + instrumentals) |
| `generate_instrumental` | Text prompt → instrumental track |
| `generate_vocals` | Lyrics + style → vocal track |
| `list_genres` | Return supported genre/style tags |

### Architecture

```
generate_song(lyrics, genre="pop", duration=120, language="en")
    → loads ACE-Step model (lazy, cached)
    → generates audio
    → saves to data/music/{uuid}.wav
    → returns path + metadata (duration, genre, etc.)
```

- Model loaded lazily, ~4GB VRAM minimum
- Output saved to `data/music/` with metadata sidecar
- Supports 19 languages, genre tags, tempo control

### New dependency (optional extra, extends `creative`)

```toml
[project.optional-dependencies]
creative = [
    ...,
    "ace-step>=1.5.0",
]
```

### Config

```python
music_output_dir: str = "data/music"
ace_step_model: str = "ace-step/ACE-Step-v1.5"
```

### Dashboard

- `/creative/ui` expanded with Music tab
- Audio player widget (HTML5 `<audio>` element)
- Lyrics input form with genre/style selector

### Tests

- `tests/test_music_tools.py` — mock ACE-Step model, test generation params

---

## Phase 4: Video Generation (new "Reel" persona)

**Goal:** Generate video clips from text/image prompts using Wan 2.1 locally.

### New persona: Reel — Motion Director

```python
"reel": {
    "id": "reel",
    "name": "Reel",
    "role": "Motion Director",
    "description": "Video generation from text and image prompts.",
    "capabilities": "video-generation,animation,motion",
    "rate_sats": 100,
    "bid_base": 80,
    "bid_jitter": 20,
    "preferred_keywords": [
        "video", "clip", "animate", "motion", "film",
        "scene", "cinematic", "footage", "render", "timelapse",
    ],
}
```

### New module: `src/tools/video_tools.py`

Tools (using **Wan 2.1** via diffusers — Apache 2.0):

| Tool | Function |
|---|---|
| `generate_video_clip` | Text → short video clip (3–6 seconds) |
| `image_to_video` | Image + prompt → animated video from still |
| `list_video_styles` | Return supported style presets |

### Architecture

```
generate_video_clip(prompt, duration=5, resolution="480p", fps=24)
    → loads Wan 2.1 via diffusers pipeline (lazy, cached)
    → generates frames
    → encodes to MP4 via FFmpeg
    → saves to data/video/{uuid}.mp4
    → returns path + metadata
```

- Wan 2.1 1.3B model: ~16GB VRAM
- Output saved to `data/video/`
- Resolution options: 480p (16GB), 720p (24GB+)

### New dependency (extends `creative` extra)

```toml
creative = [
    ...,
    # Wan 2.1 uses diffusers (already listed) + model weights downloaded on first use
]
```

### Config

```python
video_output_dir: str = "data/video"
wan_model_id: str = "Wan-AI/Wan2.1-T2V-1.3B"
video_default_resolution: str = "480p"
```

### Tests

- `tests/test_video_tools.py` — mock diffusers pipeline, test clip generation

---

## Phase 5: Creative Director — Storyboard & Assembly Pipeline

**Goal:** Orchestrate multi-persona workflows to produce 3+ minute creative
videos with music, narration, and stitched scenes.

### New module: `src/creative/director.py`

The Creative Director is a **multi-step pipeline** that coordinates Pixel,
Lyra, and Reel to produce complete creative works:

```
User: "Create a 3-minute music video about a sunrise over mountains"
                              │
                   Creative Director
                    ┌─────────┼──────────┐
                    │         │          │
              1. STORYBOARD  2. MUSIC   3. GENERATE
              (Pixel)        (Lyra)     (Reel)
                    │         │          │
              N scene        Full song   N video clips
              descriptions   with       from storyboard
              + keyframes    vocals     frames
                    │         │          │
                    └─────────┼──────────┘
                              │
                       4. ASSEMBLE
                       (MoviePy + FFmpeg)
                              │
                       Final video with
                       music, transitions,
                       titles
```

### Pipeline steps

1. **Script** — Timmy (or Quill) writes scene descriptions and lyrics
2. **Storyboard** — Pixel generates keyframe images for each scene
3. **Music** — Lyra generates the soundtrack (vocals + instrumentals)
4. **Video clips** — Reel generates video for each scene (image-to-video
   from storyboard frames, or text-to-video from descriptions)
5. **Assembly** — MoviePy stitches clips together with cross-fades,
   overlays the music track, adds title cards

### New module: `src/creative/assembler.py`

Video assembly engine (using **MoviePy** — MIT, `pip install moviepy`):

| Function | Purpose |
|---|---|
| `stitch_clips` | Concatenate video clips with transitions |
| `overlay_audio` | Mix music track onto video |
| `add_title_card` | Prepend/append title/credits |
| `add_subtitles` | Burn lyrics/captions onto video |
| `export_final` | Encode final video (H.264 + AAC) |

### New dependency

```toml
dependencies = [
    ...,
    "moviepy>=2.0.0",
]
```

### Config

```python
creative_output_dir: str = "data/creative"
video_transition_duration: float = 1.0  # seconds
default_video_codec: str = "libx264"
```

### Dashboard

- `/creative/ui` — Full Creative Studio with tabs:
  - **Images** — gallery + generation form
  - **Music** — player + generation form
  - **Video** — player + generation form
  - **Director** — multi-step pipeline builder with storyboard view
- `/creative/projects` — saved projects with all assets
- `/creative/projects/{id}` — project detail with timeline view

### Tests

- `tests/test_assembler.py` — test stitching, audio overlay, title cards
- `tests/test_director.py` — test pipeline orchestration with mocks

---

## Phase 6: Spark Integration for All New Tools

**Goal:** Every tool invocation and creative pipeline step gets captured by
Spark Intelligence for learning and advisory.

### Changes to `src/spark/engine.py`

```python
def on_tool_executed(
    self, agent_id: str, tool_name: str,
    task_id: Optional[str], success: bool,
    duration_ms: Optional[int] = None,
) -> Optional[str]:
    """Capture individual tool invocations."""

def on_creative_step(
    self, project_id: str, step_name: str,
    agent_id: str, output_path: Optional[str],
) -> Optional[str]:
    """Capture creative pipeline progress."""
```

### New advisor patterns

- "Pixel generates storyboards 40% faster than individual image calls"
- "Lyra's pop genre tracks have 85% higher completion rate than jazz"
- "Video generation on 480p uses 60% less GPU time than 720p for similar quality"
- "Git commits from Forge average 3 files per commit"

---

## Implementation Order

| Phase | What | New Files | Est. Tests |
|---|---|---|---|
| 1 | Git/DevOps tools | 2 source + 1 test | ~25 |
| 2 | Image generation | 2 source + 1 test + 1 template | ~15 |
| 3 | Music generation | 1 source + 1 test | ~12 |
| 4 | Video generation | 1 source + 1 test | ~12 |
| 5 | Creative Director pipeline | 2 source + 2 tests + 1 template | ~20 |
| 6 | Spark tool-level capture | 1 modified + 1 test update | ~8 |

**Total: ~10 new source files, ~6 new test files, ~92 new tests**

---

## New Dependencies Summary

**Required (always installed):**
```
GitPython>=3.1.40
moviepy>=2.0.0
```

**Optional `creative` extra (GPU features):**
```
diffusers>=0.30.0
transformers>=4.40.0
accelerate>=0.30.0
torch>=2.2.0
safetensors>=0.4.0
ace-step>=1.5.0
```

**Install:** `pip install ".[creative]"` for full creative stack

---

## New Persona Summary

| ID | Name | Role | Tools |
|---|---|---|---|
| pixel | Pixel | Visual Architect | generate_image, generate_storyboard, image_variations |
| lyra | Lyra | Sound Weaver | generate_song, generate_instrumental, generate_vocals |
| reel | Reel | Motion Director | generate_video_clip, image_to_video |

These join the existing 6 personas (Echo, Mace, Helm, Seer, Forge, Quill)
for a total of **9 specialized agents** in the swarm.

---

## Hardware Requirements

- **CPU only:** Git tools, MoviePy assembly, all tests (mocked)
- **8GB VRAM:** FLUX.2 Klein 4B (images)
- **4GB VRAM:** ACE-Step 1.5 (music)
- **16GB VRAM:** Wan 2.1 1.3B (video at 480p)
- **Recommended:** RTX 4090 24GB runs the entire stack comfortably
