"""Master-audio validation for a single continuous source."""

from __future__ import annotations

from typing import Iterable

from .models import CameraInfo
from .sync_manager import camera_availability_on_main_timeline


def validate_master_audio(
    cameras: Iterable[CameraInfo], master_camera_id: str | None, ceremony_duration: float, silent_export: bool = False,
    main_camera_id: str | None = None,
) -> list[str]:
    if silent_export:
        return []
    camera_by_id = {camera.id: camera for camera in cameras}
    if not master_camera_id:
        return ["Select a master audio source or explicitly choose silent export."]
    camera = camera_by_id.get(master_camera_id)
    if camera is None:
        return ["Selected master audio camera is not available."]
    if not camera.readable:
        return [f"Master audio camera '{camera.label}' is unreadable."]
    if not camera.has_audio:
        return [f"Master audio camera '{camera.label}' has no audio stream."]
    if camera.clap_timestamp is None:
        return ["Enter the master audio camera clap timestamp."]
    if main_camera_id:
        main = camera_by_id.get(main_camera_id)
        if main is None or main.clap_timestamp is None:
            return ["Choose a main camera timeline before selecting master audio."]
        availability = camera_availability_on_main_timeline(camera, main, ceremony_duration)
        if availability["start"] > 0 or availability["end"] < ceremony_duration:
            return ["Master audio must cover the whole main-camera timeline. Choose the main camera audio source."]
    elif camera.usable_duration < ceremony_duration:
        return ["Master audio does not cover the requested ceremony duration."]
    return []
