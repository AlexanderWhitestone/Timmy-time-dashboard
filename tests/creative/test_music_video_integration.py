"""Integration test: end-to-end music video pipeline with real media files.

Exercises the Creative Director pipeline and Assembler with genuine PNG,
WAV, and MP4 files.  Only AI model inference is replaced with fixture
generators; all MoviePy / FFmpeg operations run for real.

The final output video is inspected for:
  - Duration — correct within tolerance
  - Resolution — 320x180 (fixture default)
  - Audio stream — present
  - File size — non-trivial (>10 kB)
"""

import pytest
from pathlib import Path
from unittest.mock import patch

from moviepy import VideoFileClip

from creative.director import (
    create_project,
    run_storyboard,
    run_music,
    run_video_generation,
    run_assembly,
    run_full_pipeline,
    _projects,
)
from creative.assembler import (
    stitch_clips,
    overlay_audio,
    add_title_card,
    add_subtitles,
    export_final,
)
from fixtures.media import (
    make_storyboard,
    make_audio_track,
    make_video_clip,
    make_scene_clips,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

SCENES = [
    {"description": "Dawn breaks over misty mountains", "duration": 4},
    {"description": "A river carves through green valleys", "duration": 4},
    {"description": "Wildflowers sway in warm sunlight", "duration": 4},
    {"description": "Clouds gather as evening approaches", "duration": 4},
    {"description": "Stars emerge over a quiet lake", "duration": 4},
]


@pytest.fixture(autouse=True)
def clear_projects():
    """Clear in-memory project store between tests."""
    _projects.clear()
    yield
    _projects.clear()


@pytest.fixture
def media_dir(tmp_path):
    d = tmp_path / "media"
    d.mkdir()
    return d


@pytest.fixture
def scene_defs():
    """Five-scene creative brief for a short music video."""
    return [dict(s) for s in SCENES]


@pytest.fixture
def storyboard_frames(media_dir):
    """Real PNG storyboard frames for all scenes."""
    return make_storyboard(
        media_dir / "frames",
        [s["description"][:20] for s in SCENES],
        width=320, height=180,
    )


@pytest.fixture
def audio_track(media_dir):
    """Real 25-second WAV audio track."""
    return make_audio_track(
        media_dir / "soundtrack.wav",
        duration_seconds=25.0,
        frequency=440.0,
    )


@pytest.fixture
def video_clips(media_dir):
    """Real 4-second MP4 clips, one per scene (~20s total)."""
    return make_scene_clips(
        media_dir / "clips",
        [s["description"][:20] for s in SCENES],
        duration_per_clip=4.0,
        fps=12,
        width=320,
        height=180,
    )


# ── Direct assembly (zero AI mocking) ───────────────────────────────────────

class TestMusicVideoAssembly:
    """Build a real music video from fixture clips + audio, inspect output."""

    def test_full_music_video(self, video_clips, audio_track, tmp_path):
        """Stitch 5 clips -> overlay audio -> title -> credits -> inspect."""
        # 1. Stitch with crossfade
        stitched = tmp_path / "stitched.mp4"
        stitch_result = stitch_clips(
            [str(p) for p in video_clips],
            transition_duration=0.5,
            output_path=str(stitched),
        )
        assert stitch_result["success"]
        assert stitch_result["clip_count"] == 5

        # 2. Overlay audio
        with_audio = tmp_path / "with_audio.mp4"
        audio_result = overlay_audio(
            str(stitched), str(audio_track),
            output_path=str(with_audio),
        )
        assert audio_result["success"]

        # 3. Title card at start
        titled = tmp_path / "titled.mp4"
        title_result = add_title_card(
            str(with_audio),
            title="Dawn to Dusk",
            duration=3.0,
            position="start",
            output_path=str(titled),
        )
        assert title_result["success"]

        # 4. Credits at end
        final_path = tmp_path / "final_music_video.mp4"
        credits_result = add_title_card(
            str(titled),
            title="THE END",
            duration=2.0,
            position="end",
            output_path=str(final_path),
        )
        assert credits_result["success"]

        # ── Inspect final video ──────────────────────────────────────────
        assert final_path.exists()
        assert final_path.stat().st_size > 10_000  # non-trivial file

        video = VideoFileClip(str(final_path))

        # Duration: 5x4s - 4x0.5s crossfade = 18s + 3s title + 2s credits = 23s
        expected_body = 5 * 4.0 - 4 * 0.5  # 18s
        expected_total = expected_body + 3.0 + 2.0  # 23s
        assert video.duration >= 15.0  # floor sanity check
        assert video.duration == pytest.approx(expected_total, abs=3.0)

        # Resolution
        assert video.size == [320, 180]

        # Audio present
        assert video.audio is not None

        video.close()

    def test_with_subtitles(self, video_clips, audio_track, tmp_path):
        """Full video with burned-in captions."""
        # Stitch without transitions for predictable duration
        stitched = tmp_path / "stitched.mp4"
        stitch_clips(
            [str(p) for p in video_clips],
            transition_duration=0,
            output_path=str(stitched),
        )

        # Overlay audio
        with_audio = tmp_path / "with_audio.mp4"
        overlay_audio(
            str(stitched), str(audio_track),
            output_path=str(with_audio),
        )

        # Burn subtitles — one caption per scene
        captions = [
            {"text": "Dawn breaks over misty mountains", "start": 0.0, "end": 3.5},
            {"text": "A river carves through green valleys", "start": 4.0, "end": 7.5},
            {"text": "Wildflowers sway in warm sunlight", "start": 8.0, "end": 11.5},
            {"text": "Clouds gather as evening approaches", "start": 12.0, "end": 15.5},
            {"text": "Stars emerge over a quiet lake", "start": 16.0, "end": 19.5},
        ]

        final = tmp_path / "subtitled_video.mp4"
        result = add_subtitles(str(with_audio), captions, output_path=str(final))

        assert result["success"]
        assert result["caption_count"] == 5

        video = VideoFileClip(str(final))
        # 5x4s = 20s total (no crossfade)
        assert video.duration == pytest.approx(20.0, abs=1.0)
        assert video.size == [320, 180]
        assert video.audio is not None
        video.close()

    def test_export_final_quality(self, video_clips, tmp_path):
        """Export with specific codec/bitrate and verify."""
        stitched = tmp_path / "raw.mp4"
        stitch_clips(
            [str(p) for p in video_clips[:2]],
            transition_duration=0,
            output_path=str(stitched),
        )

        final = tmp_path / "hq.mp4"
        result = export_final(
            str(stitched),
            output_path=str(final),
            codec="libx264",
            bitrate="5000k",
        )

        assert result["success"]
        assert result["codec"] == "libx264"
        assert final.stat().st_size > 5000

        video = VideoFileClip(str(final))
        # Two 4s clips = 8s
        assert video.duration == pytest.approx(8.0, abs=1.0)
        video.close()


# ── Creative Director pipeline (AI calls replaced with fixtures) ────────────

class TestCreativeDirectorPipeline:
    """Run the full director pipeline; only AI model inference is stubbed
    with real-file fixture generators.  All assembly runs for real."""

    def _make_storyboard_stub(self, frames_dir):
        """Return a callable that produces real PNGs in tool-result format."""
        def stub(descriptions):
            frames = make_storyboard(
                frames_dir, descriptions, width=320, height=180,
            )
            return {
                "success": True,
                "frame_count": len(frames),
                "frames": [
                    {"path": str(f), "scene_index": i, "prompt": descriptions[i]}
                    for i, f in enumerate(frames)
                ],
            }
        return stub

    def _make_song_stub(self, audio_dir):
        """Return a callable that produces a real WAV in tool-result format."""
        def stub(lyrics="", genre="pop", duration=60, title=""):
            path = make_audio_track(
                audio_dir / "song.wav",
                duration_seconds=min(duration, 25),
            )
            return {
                "success": True,
                "path": str(path),
                "genre": genre,
                "duration": min(duration, 25),
            }
        return stub

    def _make_video_stub(self, clips_dir):
        """Return a callable that produces real MP4s in tool-result format."""
        counter = [0]
        def stub(image_path=None, prompt="scene", duration=4, **kwargs):
            path = make_video_clip(
                clips_dir / f"gen_{counter[0]:03d}.mp4",
                duration_seconds=duration,
                fps=12, width=320, height=180,
                label=prompt[:20],
            )
            counter[0] += 1
            return {
                "success": True,
                "path": str(path),
                "duration": duration,
            }
        return stub

    def test_full_pipeline_end_to_end(self, scene_defs, tmp_path):
        """run_full_pipeline with real fixtures at every stage."""
        frames_dir = tmp_path / "frames"
        frames_dir.mkdir()
        audio_dir = tmp_path / "audio"
        audio_dir.mkdir()
        clips_dir = tmp_path / "clips"
        clips_dir.mkdir()
        assembly_dir = tmp_path / "assembly"
        assembly_dir.mkdir()

        with (
            patch("creative.tools.image_tools.generate_storyboard",
                  side_effect=self._make_storyboard_stub(frames_dir)),
            patch("creative.tools.music_tools.generate_song",
                  side_effect=self._make_song_stub(audio_dir)),
            patch("creative.tools.video_tools.image_to_video",
                  side_effect=self._make_video_stub(clips_dir)),
            patch("creative.tools.video_tools.generate_video_clip",
                  side_effect=self._make_video_stub(clips_dir)),
            patch("creative.director._project_dir",
                  return_value=tmp_path / "project"),
            patch("creative.director._save_project"),
            patch("creative.assembler._output_dir",
                  return_value=assembly_dir),
        ):
            result = run_full_pipeline(
                title="Integration Test Video",
                description="End-to-end pipeline test",
                scenes=scene_defs,
                lyrics="Test lyrics for the song",
                genre="rock",
            )

        assert result["success"], f"Pipeline failed: {result}"
        assert result["project_id"]
        assert result["final_video"] is not None
        assert result["project"]["status"] == "complete"
        assert result["project"]["has_final"] is True
        assert result["project"]["clip_count"] == 5

        # Inspect the final video
        final_path = Path(result["final_video"]["path"])
        assert final_path.exists()
        assert final_path.stat().st_size > 5000

        video = VideoFileClip(str(final_path))
        # 5x4s clips - 4x1s crossfade = 16s body + 4s title card ~= 20s
        assert video.duration >= 10.0
        assert video.size == [320, 180]
        assert video.audio is not None
        video.close()

    def test_step_by_step_pipeline(self, scene_defs, tmp_path):
        """Run each pipeline step individually — mirrors manual usage."""
        frames_dir = tmp_path / "frames"
        frames_dir.mkdir()
        audio_dir = tmp_path / "audio"
        audio_dir.mkdir()
        clips_dir = tmp_path / "clips"
        clips_dir.mkdir()
        assembly_dir = tmp_path / "assembly"
        assembly_dir.mkdir()

        # 1. Create project
        with (
            patch("creative.director._project_dir",
                  return_value=tmp_path / "proj"),
            patch("creative.director._save_project"),
        ):
            proj = create_project(
                "Step-by-Step Video",
                "Manual pipeline test",
                scenes=scene_defs,
                lyrics="Step by step, we build it all",
            )
        pid = proj["project"]["id"]
        assert proj["success"]

        # 2. Storyboard
        with (
            patch("creative.tools.image_tools.generate_storyboard",
                  side_effect=self._make_storyboard_stub(frames_dir)),
            patch("creative.director._save_project"),
        ):
            sb = run_storyboard(pid)
        assert sb["success"]
        assert sb["frame_count"] == 5

        # 3. Music
        with (
            patch("creative.tools.music_tools.generate_song",
                  side_effect=self._make_song_stub(audio_dir)),
            patch("creative.director._save_project"),
        ):
            mus = run_music(pid, genre="electronic")
        assert mus["success"]
        assert mus["genre"] == "electronic"

        # Verify the audio file exists and is valid
        audio_path = Path(mus["path"])
        assert audio_path.exists()
        assert audio_path.stat().st_size > 1000

        # 4. Video generation (uses storyboard frames → image_to_video)
        with (
            patch("creative.tools.video_tools.image_to_video",
                  side_effect=self._make_video_stub(clips_dir)),
            patch("creative.director._save_project"),
        ):
            vid = run_video_generation(pid)
        assert vid["success"]
        assert vid["clip_count"] == 5

        # Verify each clip exists
        for clip_info in vid["clips"]:
            clip_path = Path(clip_info["path"])
            assert clip_path.exists()
            assert clip_path.stat().st_size > 1000

        # 5. Assembly (all real MoviePy operations)
        with (
            patch("creative.director._save_project"),
            patch("creative.assembler._output_dir",
                  return_value=assembly_dir),
        ):
            asm = run_assembly(pid, transition_duration=0.5)
        assert asm["success"]

        # Inspect final output
        final_path = Path(asm["path"])
        assert final_path.exists()
        assert final_path.stat().st_size > 5000

        video = VideoFileClip(str(final_path))
        # 5x4s - 4x0.5s = 18s body, + title card ~= 22s
        assert video.duration >= 10.0
        assert video.size == [320, 180]
        assert video.audio is not None
        video.close()

        # Verify project reached completion
        project = _projects[pid]
        assert project.status == "complete"
        assert project.final_video is not None
        assert len(project.video_clips) == 5
        assert len(project.storyboard_frames) == 5
        assert project.music_track is not None
