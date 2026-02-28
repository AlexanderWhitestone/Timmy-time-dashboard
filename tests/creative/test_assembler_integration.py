"""Integration tests for creative.assembler — real files, no mocks.

Every test creates actual media files (PNG, WAV, MP4), runs them through
the assembler functions, and inspects the output with MoviePy / Pillow.
"""

import pytest
from pathlib import Path

from moviepy import VideoFileClip, AudioFileClip

from creative.assembler import (
    stitch_clips,
    overlay_audio,
    add_title_card,
    add_subtitles,
    export_final,
)
from tests.fixtures.media import (
    make_audio_track,
    make_video_clip,
    make_scene_clips,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def media_dir(tmp_path):
    """Isolated directory for generated media."""
    d = tmp_path / "media"
    d.mkdir()
    return d


@pytest.fixture
def two_clips(media_dir):
    """Two real 3-second MP4 clips."""
    return make_scene_clips(
        media_dir, ["Scene A", "Scene B"],
        duration_per_clip=3.0, fps=12, width=320, height=180,
    )


@pytest.fixture
def five_clips(media_dir):
    """Five real 2-second MP4 clips — enough for a short video."""
    return make_scene_clips(
        media_dir,
        ["Dawn", "Sunrise", "Mountains", "River", "Sunset"],
        duration_per_clip=2.0, fps=12, width=320, height=180,
    )


@pytest.fixture
def audio_10s(media_dir):
    """A real 10-second WAV audio track."""
    return make_audio_track(media_dir / "track.wav", duration_seconds=10.0)


@pytest.fixture
def audio_30s(media_dir):
    """A real 30-second WAV audio track."""
    return make_audio_track(
        media_dir / "track_long.wav",
        duration_seconds=30.0,
        frequency=330.0,
    )


# ── Stitch clips ─────────────────────────────────────────────────────────────

class TestStitchClipsReal:
    def test_stitch_two_clips_no_transition(self, two_clips, tmp_path):
        """Stitching 2 x 3s clips → ~6s video."""
        out = tmp_path / "stitched.mp4"
        result = stitch_clips(
            [str(p) for p in two_clips],
            transition_duration=0,
            output_path=str(out),
        )

        assert result["success"]
        assert result["clip_count"] == 2
        assert out.exists()
        assert out.stat().st_size > 1000  # non-trivial file

        video = VideoFileClip(str(out))
        assert video.duration == pytest.approx(6.0, abs=0.5)
        assert video.size == [320, 180]
        video.close()

    def test_stitch_with_crossfade(self, two_clips, tmp_path):
        """Cross-fade transition shortens total duration."""
        out = tmp_path / "crossfade.mp4"
        result = stitch_clips(
            [str(p) for p in two_clips],
            transition_duration=1.0,
            output_path=str(out),
        )

        assert result["success"]
        video = VideoFileClip(str(out))
        # 2 x 3s - 1s overlap = ~5s
        assert video.duration == pytest.approx(5.0, abs=1.0)
        video.close()

    def test_stitch_five_clips(self, five_clips, tmp_path):
        """Stitch 5 clips → continuous video with correct frame count."""
        out = tmp_path / "five.mp4"
        result = stitch_clips(
            [str(p) for p in five_clips],
            transition_duration=0.5,
            output_path=str(out),
        )

        assert result["success"]
        assert result["clip_count"] == 5

        video = VideoFileClip(str(out))
        # 5 x 2s - 4 * 0.5s overlap = 8s
        assert video.duration >= 7.0
        assert video.size == [320, 180]
        video.close()


# ── Audio overlay ─────────────────────────────────────────────────────────────

class TestOverlayAudioReal:
    def test_overlay_adds_audio_stream(self, two_clips, audio_10s, tmp_path):
        """Overlaying audio onto a silent video produces audible output."""
        # First stitch clips
        stitched = tmp_path / "silent.mp4"
        stitch_clips(
            [str(p) for p in two_clips],
            transition_duration=0,
            output_path=str(stitched),
        )

        out = tmp_path / "with_audio.mp4"
        result = overlay_audio(str(stitched), str(audio_10s), output_path=str(out))

        assert result["success"]
        assert out.exists()

        video = VideoFileClip(str(out))
        assert video.audio is not None  # has audio stream
        assert video.duration == pytest.approx(6.0, abs=0.5)
        video.close()

    def test_audio_trimmed_to_video_length(self, two_clips, audio_30s, tmp_path):
        """30s audio track is trimmed to match ~6s video duration."""
        stitched = tmp_path / "short.mp4"
        stitch_clips(
            [str(p) for p in two_clips],
            transition_duration=0,
            output_path=str(stitched),
        )

        out = tmp_path / "trimmed.mp4"
        result = overlay_audio(str(stitched), str(audio_30s), output_path=str(out))

        assert result["success"]
        video = VideoFileClip(str(out))
        # Audio should be trimmed to video length, not 30s
        assert video.duration < 10.0
        video.close()


# ── Title cards ───────────────────────────────────────────────────────────────

class TestAddTitleCardReal:
    def test_prepend_title_card(self, two_clips, tmp_path):
        """Title card at start adds to total duration."""
        stitched = tmp_path / "base.mp4"
        stitch_clips(
            [str(p) for p in two_clips],
            transition_duration=0,
            output_path=str(stitched),
        )
        base_video = VideoFileClip(str(stitched))
        base_duration = base_video.duration
        base_video.close()

        out = tmp_path / "titled.mp4"
        result = add_title_card(
            str(stitched),
            title="My Music Video",
            duration=3.0,
            position="start",
            output_path=str(out),
        )

        assert result["success"]
        assert result["title"] == "My Music Video"

        video = VideoFileClip(str(out))
        # Title card (3s) + base video (~6s) = ~9s
        assert video.duration == pytest.approx(base_duration + 3.0, abs=1.0)
        video.close()

    def test_append_credits(self, two_clips, tmp_path):
        """Credits card at end adds to total duration."""
        clip_path = str(two_clips[0])  # single 3s clip

        out = tmp_path / "credits.mp4"
        result = add_title_card(
            clip_path,
            title="THE END",
            duration=2.0,
            position="end",
            output_path=str(out),
        )

        assert result["success"]
        video = VideoFileClip(str(out))
        # 3s clip + 2s credits = ~5s
        assert video.duration == pytest.approx(5.0, abs=1.0)
        video.close()


# ── Subtitles ─────────────────────────────────────────────────────────────────

class TestAddSubtitlesReal:
    def test_burn_captions(self, two_clips, tmp_path):
        """Subtitles are burned onto the video (duration unchanged)."""
        stitched = tmp_path / "base.mp4"
        stitch_clips(
            [str(p) for p in two_clips],
            transition_duration=0,
            output_path=str(stitched),
        )

        captions = [
            {"text": "Welcome to the show", "start": 0.0, "end": 2.0},
            {"text": "Here we go!", "start": 2.5, "end": 4.5},
            {"text": "Finale", "start": 5.0, "end": 6.0},
        ]

        out = tmp_path / "subtitled.mp4"
        result = add_subtitles(str(stitched), captions, output_path=str(out))

        assert result["success"]
        assert result["caption_count"] == 3

        video = VideoFileClip(str(out))
        # Duration should be unchanged
        assert video.duration == pytest.approx(6.0, abs=0.5)
        assert video.size == [320, 180]
        video.close()


# ── Export final ──────────────────────────────────────────────────────────────

class TestExportFinalReal:
    def test_reencodes_video(self, two_clips, tmp_path):
        """Final export produces a valid re-encoded file."""
        clip_path = str(two_clips[0])

        out = tmp_path / "final.mp4"
        result = export_final(
            clip_path,
            output_path=str(out),
            codec="libx264",
            bitrate="2000k",
        )

        assert result["success"]
        assert result["codec"] == "libx264"
        assert out.exists()
        assert out.stat().st_size > 500

        video = VideoFileClip(str(out))
        assert video.duration == pytest.approx(3.0, abs=0.5)
        video.close()
