from __future__ import annotations

import subprocess

from kinderclip.audio_manager import validate_master_audio
from kinderclip.media_probe import probe_media


def test_master_audio_requires_audio_stream(cameras):
    errors = validate_master_audio(cameras, "side", 60.0)
    assert "has no audio" in errors[0]


def test_silent_export_allows_missing_audio(cameras):
    assert validate_master_audio(cameras, "side", 60.0, silent_export=True) == []


def test_main_camera_audio_covers_full_main_timeline(cameras):
    assert validate_master_audio(cameras, "front", 120.0, main_camera_id="front") == []
    assert validate_master_audio(cameras, "side", 120.0, main_camera_id="front")


def test_probe_parses_video_and_audio_metadata(tmp_path, monkeypatch):
    video = tmp_path / "camera.mp4"
    video.write_bytes(b"not a real file")
    payload = '{"format":{"duration":"42.5"},"streams":[{"codec_type":"video","codec_name":"h264","width":1280,"height":720,"avg_frame_rate":"30000/1001"},{"codec_type":"audio","codec_name":"aac"}]}'
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, payload, ""))
    result = probe_media(video, "front", "Front", ffprobe_bin="ffprobe")
    assert result.readable and result.has_audio
    assert result.frame_rate == 30000 / 1001


def test_probe_marks_ffprobe_failure_unreadable(tmp_path, monkeypatch):
    video = tmp_path / "camera.mp4"
    video.write_bytes(b"x")
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 1, "", "broken"))
    assert not probe_media(video, "front", "Front").readable
