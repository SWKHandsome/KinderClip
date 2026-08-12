"""Chronological OpenCV frame sampling with an FFmpeg single-frame fallback."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from typing import Iterable

import numpy as np

from .sync_manager import main_timeline_source_time, source_time


def analysis_windows(duration: float, window_seconds: float) -> list[dict[str, float]]:
    if duration <= 0 or window_seconds <= 0:
        raise ValueError("Duration and window size must be positive.")
    windows: list[dict[str, float]] = []
    start = 0.0
    while start < duration - 1e-9:
        end = min(duration, start + window_seconds)
        windows.append({"start": round(start, 3), "end": round(end, 3)})
        start = end
    return windows


def _cv2():
    try:
        import cv2
    except ImportError as exc:  # pragma: no cover - dependency preflight handles this in UI
        raise RuntimeError("OpenCV is required for camera analysis.") from exc
    return cv2


def sample_frame(
    path: str | Path, file_time: float, width: int, height: int, ffmpeg_bin: str = "ffmpeg"
) -> np.ndarray | None:
    """Seek a source frame with OpenCV, then fall back to FFmpeg if needed."""
    cv2 = _cv2()
    capture = cv2.VideoCapture(str(path))
    try:
        capture.set(cv2.CAP_PROP_POS_MSEC, file_time * 1000.0)
        ok, frame = capture.read()
    finally:
        capture.release()
    if ok and frame is not None:
        return cv2.resize(frame, (width, height))
    with tempfile.TemporaryDirectory(prefix="kinderclip-frame-") as folder:
        output = Path(folder) / "frame.jpg"
        result = subprocess.run(
            [ffmpeg_bin, "-y", "-ss", f"{file_time:.3f}", "-i", str(path), "-frames:v", "1", str(output)],
            capture_output=True, text=True, check=False,
        )
        if result.returncode != 0 or not output.exists():
            return None
        image = cv2.imread(str(output))
        return cv2.resize(image, (width, height)) if image is not None else None


def sample_camera_frames(
    path: str | Path,
    clap_timestamp: float,
    duration: float,
    sample_fps: float,
    width: int,
    height: int,
    main_clap_timestamp: float | None = None,
    source_duration: float | None = None,
) -> list[tuple[float, np.ndarray]]:
    if sample_fps <= 0:
        raise ValueError("sample_fps must be positive")
    step = 1.0 / sample_fps
    samples: list[tuple[float, np.ndarray]] = []
    time = 0.0
    while time < duration - 1e-9:
        file_time = (
            source_time(time, clap_timestamp) if main_clap_timestamp is None
            else main_timeline_source_time(time, main_clap_timestamp, clap_timestamp)
        )
        if file_time < 0 or (source_duration is not None and file_time >= source_duration):
            time += step
            continue
        frame = sample_frame(path, file_time, width, height)
        if frame is not None:
            samples.append((round(time, 3), frame))
        time += step
    return samples


def frames_for_window(samples: Iterable[tuple[float, np.ndarray]], start: float, end: float) -> list[np.ndarray]:
    return [frame for timeline_time, frame in samples if start <= timeline_time < end]
