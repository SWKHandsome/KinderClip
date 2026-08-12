"""FFprobe-backed source inspection and executable preflight."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .models import CameraInfo


def media_tools_available() -> dict[str, bool]:
    return {"ffmpeg": shutil.which("ffmpeg") is not None, "ffprobe": shutil.which("ffprobe") is not None}


def media_preflight_message() -> str | None:
    tools = media_tools_available()
    missing = [name for name, found in tools.items() if not found]
    if not missing:
        return None
    return (
        f"KinderClip cannot find {', '.join(missing)} on PATH. Install FFmpeg for Windows, "
        "add its bin folder to PATH, then restart Streamlit."
    )


def _parse_rate(value: str | None) -> float:
    if not value or value == "0/0":
        return 0.0
    numerator, separator, denominator = value.partition("/")
    try:
        return float(numerator) / float(denominator) if separator and float(denominator) else float(value)
    except ValueError:
        return 0.0


def probe_media(path: str | Path, camera_id: str, label: str, ffprobe_bin: str = "ffprobe") -> CameraInfo:
    """Return normalised metadata, preserving failure details for the UI."""
    source = Path(path)
    base = CameraInfo(
        id=camera_id, label=label, path=str(source), duration=0.0, width=0, height=0,
        frame_rate=0.0, codec="", has_audio=False, readable=False,
    )
    if not source.exists():
        base.error = "File does not exist"
        return base
    command = [
        ffprobe_bin, "-v", "error", "-show_entries",
        "format=duration:stream=codec_type,codec_name,width,height,avg_frame_rate",
        "-of", "json", str(source),
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=False, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as exc:
        base.error = f"FFprobe could not inspect this file: {exc}"
        return base
    if result.returncode != 0:
        base.error = result.stderr.strip() or "FFprobe rejected this file"
        return base
    try:
        metadata: dict[str, Any] = json.loads(result.stdout)
        streams = metadata.get("streams", [])
        video = next(stream for stream in streams if stream.get("codec_type") == "video")
        duration = float(metadata.get("format", {}).get("duration", 0.0))
    except (ValueError, TypeError, StopIteration, json.JSONDecodeError) as exc:
        base.error = f"Invalid media metadata: {exc}"
        return base
    base.duration = duration
    base.width = int(video.get("width") or 0)
    base.height = int(video.get("height") or 0)
    base.frame_rate = _parse_rate(video.get("avg_frame_rate"))
    base.codec = str(video.get("codec_name") or "unknown")
    base.has_audio = any(stream.get("codec_type") == "audio" for stream in streams)
    base.readable = duration > 0 and base.width > 0 and base.height > 0
    if not base.readable:
        base.error = "No readable video stream or duration"
    return base
