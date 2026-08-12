"""Pre-render EDL validation with actionable, segment-specific errors."""

from __future__ import annotations

from typing import Any

from .audio_manager import validate_master_audio
from .camera_recommender import count_switches
from .models import CameraInfo, ValidationIssue


def _issue(message: str, field: str | None = None, segment_id: str | None = None) -> ValidationIssue:
    return ValidationIssue(message=message, field=field, segment_id=segment_id)


def validate_edl(edl: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    issues: list[ValidationIssue] = []
    sources = [CameraInfo.from_dict(item) for item in edl.get("sources", [])]
    readable = [source for source in sources if source.readable]
    if len(readable) < 2:
        issues.append(_issue("At least two readable source cameras are required.", "sources"))
    project = edl.get("project", {})
    duration = float(project.get("ceremony_duration", 0))
    if not 60 <= duration <= 174:
        issues.append(_issue("Ceremony duration must be between 60 and 174 seconds.", "ceremony_duration"))
    for source in readable:
        if source.clap_timestamp is None or source.clap_timestamp < 0 or source.clap_timestamp >= source.duration:
            issues.append(_issue(f"Camera '{source.label}' has an invalid clap timestamp.", "clap_timestamp"))
    for error in validate_master_audio(
        sources, project.get("master_audio_camera"), duration, project.get("silent_export", False), project.get("main_camera_id")
    ):
        issues.append(_issue(error, "master_audio_camera"))
    segments = edl.get("segments", [])
    if not segments:
        issues.append(_issue("The edit contains no segments.", "segments"))
    selected_ids: list[str] = []
    camera_ids = {source.id for source in readable}
    expected_start = 0.0
    for index, segment in enumerate(segments):
        segment_id = segment.get("id")
        start, end = float(segment.get("start", -1)), float(segment.get("end", -1))
        if abs(start - expected_start) > 0.001:
            issues.append(_issue("Segments must be ordered, continuous, and non-overlapping.", "timeline", segment_id))
        if end - start < config["min_segment_seconds"] - 1e-9:
            issues.append(_issue("Segment is shorter than the five-second minimum.", "timeline", segment_id))
        if start < 0 or end > duration + 0.001:
            issues.append(_issue("Segment is outside the ceremony timeline.", "timeline", segment_id))
        expected_start = end
        original_boundary = float(segment.get("analysis_start", start))
        if index > 0 and abs(start - original_boundary) > config["max_boundary_adjustment"] + 0.001:
            issues.append(_issue("Adjusted boundary exceeds the permitted two-second range.", "timeline", segment_id))
        selected = segment.get("selected_camera")
        selected_ids.append(selected or "")
        option = segment.get("camera_options", {}).get(selected, {})
        if selected not in camera_ids or not option.get("available", True) or option.get("black_frame", False):
            issues.append(_issue("Selected camera is unavailable or mostly black.", "selected_camera", segment_id))
        if segment.get("transition") not in {"Cut", "Crossfade", "Fade"}:
            issues.append(_issue("Select a valid transition.", "transition", segment_id))
        if segment.get("review_status") not in {"reviewed", "overridden"}:
            issues.append(_issue("This segment has not been reviewed.", "review_status", segment_id))
        if selected != segment.get("recommended_camera") and not str(segment.get("override_reason", "")).strip():
            issues.append(_issue("A camera override needs a reason.", "override_reason", segment_id))
    if segments and abs(expected_start - duration) > 0.001:
        issues.append(_issue("Segment timeline does not match the requested ceremony duration.", "timeline"))
    used = {camera_id for camera_id in selected_ids if camera_id}
    if len(used) < 2:
        issues.append(_issue("At least two camera angles must be used.", "camera_variety"))
    if count_switches(selected_ids) < 3:
        issues.append(_issue("At least three camera switches are required when acceptable alternatives exist.", "camera_variety"))
    if not str(project.get("opening_title", "")).strip():
        issues.append(_issue("Opening title is required.", "opening_title"))
    if not str(project.get("lower_third", "")).strip():
        issues.append(_issue("Lower-third text is required.", "lower_third"))
    if not str(project.get("closing_credit", "")).strip():
        issues.append(_issue("Closing credit is required.", "closing_credit"))
    if not edl.get("human_approved", False):
        issues.append(_issue("Record human approval before rendering.", "human_approved"))
    if not edl.get("responsible_use_accepted", False):
        issues.append(_issue(
            "Read and accept the Privacy, Consent & Responsible-Use Agreement before rendering.",
            "responsible_use_accepted",
        ))
    return {"valid": not issues, "issues": [item.to_dict() for item in issues], "final_duration": duration + config["title_seconds"] + config["credits_seconds"]}
