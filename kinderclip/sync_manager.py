"""Manual clap synchronisation calculations."""

from __future__ import annotations

from typing import Iterable

from .models import CameraInfo


def validate_clap_timestamp(timestamp: float | None, duration: float) -> str | None:
    if timestamp is None:
        return "Enter a clap timestamp."
    if timestamp < 0:
        return "Clap timestamp cannot be negative."
    if timestamp >= duration:
        return "Clap timestamp must be before the end of the video."
    return None


def shared_timeline_duration(cameras: Iterable[CameraInfo]) -> float:
    selected = [camera for camera in cameras if camera.readable]
    if len(selected) < 2:
        raise ValueError("At least two readable cameras are required.")
    errors = [validate_clap_timestamp(camera.clap_timestamp, camera.duration) for camera in selected]
    failures = [error for error in errors if error]
    if failures:
        raise ValueError(failures[0])
    return min(camera.usable_duration for camera in selected)


def source_time(shared_timeline_time: float, clap_timestamp: float) -> float:
    if shared_timeline_time < 0 or clap_timestamp < 0:
        raise ValueError("Timeline time and clap timestamp must be non-negative.")
    return shared_timeline_time + clap_timestamp


def main_timeline_source_time(
    main_timeline_time: float, main_clap_timestamp: float, camera_clap_timestamp: float
) -> float:
    """Map a main-camera timeline position to an individual camera's file time.

    The same clap appears at ``main_clap_timestamp`` in the main camera and
    ``camera_clap_timestamp`` in the other camera.  This keeps early footage
    from the main camera instead of discarding it to start every clip at the
    clap.
    """
    if main_timeline_time < 0 or main_clap_timestamp < 0 or camera_clap_timestamp < 0:
        raise ValueError("Timeline time and clap timestamps must be non-negative.")
    return main_timeline_time - main_clap_timestamp + camera_clap_timestamp


def camera_availability_on_main_timeline(
    camera: CameraInfo, main_camera: CameraInfo, timeline_duration: float | None = None
) -> dict[str, float]:
    """Return the interval where a camera can safely be used on the main timeline."""
    if camera.clap_timestamp is None or main_camera.clap_timestamp is None:
        raise ValueError("Every readable camera needs a clap timestamp.")
    end_limit = main_camera.duration if timeline_duration is None else timeline_duration
    start = main_camera.clap_timestamp - camera.clap_timestamp
    end = start + camera.duration
    return {
        "start": round(max(0.0, start), 3),
        "end": round(min(end_limit, end), 3),
    }


def main_timeline_duration(cameras: Iterable[CameraInfo], main_camera_id: str) -> float:
    camera_list = list(cameras)
    main = next((camera for camera in camera_list if camera.id == main_camera_id and camera.readable), None)
    if main is None:
        raise ValueError("Choose a readable main camera.")
    errors = [validate_clap_timestamp(camera.clap_timestamp, camera.duration) for camera in camera_list if camera.readable]
    failures = [error for error in errors if error]
    if failures:
        raise ValueError(failures[0])
    return main.duration


def sync_config(cameras: Iterable[CameraInfo], target_duration: float, main_camera_id: str | None = None) -> dict:
    camera_list = list(cameras)
    if main_camera_id is None:
        common_duration = shared_timeline_duration(camera_list)
        if target_duration > common_duration:
            raise ValueError("Target duration exceeds the common usable timeline.")
        return {
            "formula": "camera_file_time = shared_timeline_time + clap_time_seconds",
            "target_duration": target_duration,
            "common_duration": common_duration,
            "cameras": {camera.id: camera.clap_timestamp for camera in camera_list if camera.readable},
        }
    timeline_duration = main_timeline_duration(camera_list, main_camera_id)
    if target_duration > timeline_duration:
        raise ValueError("Target duration exceeds the main camera timeline.")
    main = next(camera for camera in camera_list if camera.id == main_camera_id)
    return {
        "timeline_mode": "main_camera",
        "formula": "camera_file_time = main_timeline_time - main_clap_time_seconds + camera_clap_time_seconds",
        "target_duration": target_duration,
        "main_camera_id": main_camera_id,
        "main_timeline_duration": timeline_duration,
        "cameras": {camera.id: camera.clap_timestamp for camera in camera_list if camera.readable},
        "camera_availability": {
            camera.id: camera_availability_on_main_timeline(camera, main, target_duration)
            for camera in camera_list if camera.readable
        },
    }
