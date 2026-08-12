from __future__ import annotations

import subprocess
from pathlib import Path

from kinderclip.config import default_config
from kinderclip.renderer import render_edl


def test_renderer_reports_all_major_rendering_stages(tmp_path, monkeypatch):
    config = default_config()
    font = tmp_path / "font.ttf"
    font.write_bytes(b"font")
    config["font_file"] = str(font)
    source = tmp_path / "source.mp4"
    events: list[str] = []

    def fake_runner(command, **_kwargs):
        Path(command[-1]).parent.mkdir(parents=True, exist_ok=True)
        Path(command[-1]).write_bytes(b"video")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr("kinderclip.renderer.ffmpeg_available", lambda _bin: True)
    edl = {
        "project": {
            "ceremony_duration": 10.0, "opening_title": "KinderClip", "lower_third": "Demo",
            "closing_credit": "Thanks", "main_camera_id": "front", "master_audio_camera": "front", "silent_export": False,
        },
        "sources": [{"id": "front", "path": str(source), "clap_timestamp": 0.0}],
        "segments": [{"id": "segment-001", "start": 0.0, "end": 10.0, "selected_camera": "front", "transition": "Cut"}],
    }
    output = render_edl(edl, tmp_path, config, events.append, runner=fake_runner)
    assert output.exists()
    assert events == [
        "Creating opening title", "Rendering ceremony segments", "Rendered segment 1 of 1",
        "Creating closing credits", "Joining visual stage 1 of 2", "Joining visual stage 2 of 2",
        "Adding continuous master audio", "Final video completed",
    ]
