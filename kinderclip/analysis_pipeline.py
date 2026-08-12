"""Orchestrates sampling, technical analysis, scoring, and caching."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from .analysis_cache import analysis_fingerprint, load_cached_analysis, save_cached_analysis
from .camera_analyzer import analyse_frames
from .camera_scorer import technical_score
from .frame_sampler import analysis_windows, frames_for_window, sample_camera_frames
from .models import CameraInfo
from .sync_manager import camera_availability_on_main_timeline


def run_analysis(
    cameras: list[CameraInfo], duration: float, config: dict[str, Any], workspace: str | Path,
    progress: Callable[[int, int, int, int], None] | None = None,
    main_camera_id: str | None = None,
) -> dict[str, Any]:
    serialised = [camera.to_dict() for camera in cameras]
    fingerprint = analysis_fingerprint(serialised, duration, config, main_camera_id)
    cached = load_cached_analysis(workspace, fingerprint)
    if cached:
        return cached
    windows = analysis_windows(duration, config["window_seconds"])
    result: dict[str, Any] = {
        "product": "KinderClip", "fingerprint": fingerprint, "duration_seconds": duration,
        "config": config, "windows": windows, "cameras": {}, "main_camera_id": main_camera_id,
    }
    main_camera = next((camera for camera in cameras if camera.id == main_camera_id), None) if main_camera_id else None
    total = len(cameras) * len(windows)
    completed = 0
    for camera_index, camera in enumerate(cameras, start=1):
        if not camera.readable or camera.clap_timestamp is None:
            result["cameras"][camera.id] = {"available": False, "reason": camera.error or "Invalid camera synchronisation", "windows": []}
            completed += len(windows)
            continue
        samples = sample_camera_frames(
            camera.path, camera.clap_timestamp, duration, config["sample_fps"], config["analysis_width"], config["analysis_height"],
            main_clap_timestamp=main_camera.clap_timestamp if main_camera else None, source_duration=camera.duration,
        )
        availability = camera_availability_on_main_timeline(camera, main_camera, duration) if main_camera else {"start": 0.0, "end": duration}
        camera_windows = []
        for window_index, window in enumerate(windows, start=1):
            measurement = analyse_frames(frames_for_window(samples, window["start"], window["end"]), config)
            if window["start"] < availability["start"] - 1e-9 or window["end"] > availability["end"] + 1e-9:
                measurement["available"] = False
                measurement["black_frame"] = True
                measurement["reason"] = "Camera is outside its available interval on the main timeline"
            camera_windows.append({**window, **technical_score(measurement, config)})
            completed += 1
            if progress:
                progress(camera_index, len(cameras), completed, total)
        result["cameras"][camera.id] = {"available": bool(samples), "availability": availability, "windows": camera_windows}
    save_cached_analysis(workspace, fingerprint, result)
    return result
