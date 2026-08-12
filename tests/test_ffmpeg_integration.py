"""Optional real-media smoke test; skipped on machines without FFmpeg tools."""

from __future__ import annotations

import shutil
import subprocess

import pytest

from kinderclip.config import default_config
from kinderclip.renderer import render_edl


pytestmark = pytest.mark.skipif(
    not (shutil.which("ffmpeg") and shutil.which("ffprobe")),
    reason="FFmpeg and FFprobe are required for the optional rendering integration test",
)


def test_ffmpeg_renders_a_playable_kinderclip_smoke_video(tmp_path):
    """Exercise staged video rendering and delayed continuous master audio."""
    source = tmp_path / "camera.mp4"
    subprocess.run(
        [
            "ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=blue:s=160x90:r=5",
            "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000", "-t", "1",
            "-c:v", "libx264", "-c:a", "aac", "-shortest", str(source),
        ],
        capture_output=True, text=True, check=True,
    )
    config = default_config()
    config.update({"output_width": 160, "output_height": 90, "output_fps": 5, "title_seconds": 0.2, "credits_seconds": 0.2, "audio_fade_seconds": 0.1})
    edl = {
        "project": {
            "ceremony_duration": 1.0, "opening_title": "KinderClip", "lower_third": "Demo",
            "closing_credit": "Thanks", "master_audio_camera": "front", "silent_export": False,
        },
        "sources": [{"id": "front", "label": "Front", "path": str(source), "clap_timestamp": 0.0}],
        "segments": [{"id": "segment-001", "start": 0.0, "end": 1.0, "selected_camera": "front", "transition": "Cut"}],
    }
    output = render_edl(edl, tmp_path, config)
    assert output.exists() and output.stat().st_size > 0
