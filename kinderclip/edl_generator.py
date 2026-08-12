"""Draft EDL construction and human-review mutations."""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

from .camera_recommender import DECISION_LABELS


RESPONSIBLE_USE_AGREEMENT_VERSION = "2026-08-06"


def _segment_id(index: int) -> str:
    return f"segment-{index + 1:03d}"


def generate_draft_edl(
    project: dict[str, Any], cameras: list[dict[str, Any]], analysis: dict[str, Any], recommendations: list[dict[str, Any]],
) -> dict[str, Any]:
    windows = analysis["windows"]
    if len(windows) != len(recommendations):
        raise ValueError("Analysis windows and recommendations must have the same length.")
    segments: list[dict[str, Any]] = []
    for index, (window, recommendation) in enumerate(zip(windows, recommendations)):
        options = {
            camera_id: camera_data["windows"][index]
            for camera_id, camera_data in analysis["cameras"].items()
            if index < len(camera_data.get("windows", []))
        }
        selected = recommendation["camera_id"]
        segments.append({
            "id": _segment_id(index),
            "analysis_start": window["start"], "analysis_end": window["end"],
            "start": window["start"], "end": window["end"],
            "boundary_changed": False, "boundary_adjustment": 0.0,
            "recommended_camera": selected, "selected_camera": selected,
            "technical_score": recommendation["technical_score"],
            "component_scores": recommendation.get("component_scores", {}),
            "recommendation_reason": recommendation["reason"],
            "decision_source": recommendation["decision_source"],
            "transition": "Cut", "review_status": "pending", "override_reason": "",
            "camera_options": options,
        })
    return {
        "product": "KinderClip", "version": 1,
        "created_at": datetime.now(UTC).isoformat(), "updated_at": datetime.now(UTC).isoformat(),
        "project": deepcopy(project), "sources": deepcopy(cameras), "segments": segments,
        "human_approved": False, "responsible_use_accepted": False,
        "responsible_use_agreement_version": RESPONSIBLE_USE_AGREEMENT_VERSION,
    }


def update_review_segment(
    edl: dict[str, Any], segment_id: str, selected_camera: str, transition: str,
    override_reason: str = "",
) -> None:
    segment = next((item for item in edl["segments"] if item["id"] == segment_id), None)
    if segment is None:
        raise ValueError("Unknown segment")
    if selected_camera not in segment["camera_options"]:
        raise ValueError("Selected camera is not available for this segment")
    if selected_camera != segment["recommended_camera"] and not override_reason.strip():
        raise ValueError("Give a reason when changing the recommended camera")
    if transition not in {"Cut", "Crossfade", "Fade"}:
        raise ValueError("Unsupported transition")
    segment["selected_camera"] = selected_camera
    segment["transition"] = transition
    segment["override_reason"] = override_reason.strip()
    if selected_camera != segment["recommended_camera"]:
        segment["decision_source"] = "human_override"
        segment["recommendation_reason"] = DECISION_LABELS["human_override"]
        segment["review_status"] = "overridden"
    else:
        segment["review_status"] = "reviewed"
    edl["human_approved"] = False
    edl["updated_at"] = datetime.now(UTC).isoformat()


def adjust_boundary(edl: dict[str, Any], current_segment_index: int, new_boundary: float, config: dict[str, Any]) -> None:
    """Move the shared boundary before a segment and retain the analysis original."""
    segments = edl["segments"]
    if current_segment_index <= 0 or current_segment_index >= len(segments):
        raise ValueError("Only a boundary between two segments can be adjusted")
    previous, current = segments[current_segment_index - 1], segments[current_segment_index]
    original = current["analysis_start"]
    step = config["boundary_step"]
    if abs(new_boundary - original) > config["max_boundary_adjustment"] + 1e-9:
        raise ValueError("Boundary adjustment exceeds the permitted range")
    if abs((new_boundary - original) / step - round((new_boundary - original) / step)) > 1e-6:
        raise ValueError("Boundary adjustment must use the configured step")
    if new_boundary - previous["start"] < config["min_segment_seconds"]:
        raise ValueError("This adjustment would make the previous segment shorter than five seconds")
    if current["end"] - new_boundary < config["min_segment_seconds"]:
        raise ValueError("This adjustment would make the current segment shorter than five seconds")
    previous["end"] = round(new_boundary, 3)
    current["start"] = round(new_boundary, 3)
    previous["boundary_changed"] = current["boundary_changed"] = not abs(new_boundary - original) < 1e-9
    previous["boundary_adjustment"] = current["boundary_adjustment"] = round(new_boundary - original, 3)
    edl["human_approved"] = False
    edl["updated_at"] = datetime.now(UTC).isoformat()


def set_responsible_use_acceptance(edl: dict[str, Any], accepted: bool) -> None:
    """Record or withdraw the user's explicit responsible-use confirmation."""
    edl["responsible_use_accepted"] = accepted
    edl["responsible_use_agreement_version"] = RESPONSIBLE_USE_AGREEMENT_VERSION
    if accepted:
        edl["responsible_use_accepted_at"] = datetime.now(UTC).isoformat()
    else:
        edl.pop("responsible_use_accepted_at", None)
    edl["updated_at"] = datetime.now(UTC).isoformat()


def review_record(edl: dict[str, Any], validation: dict[str, Any]) -> dict[str, Any]:
    segments = edl["segments"]
    return {
        "product": "KinderClip", "recorded_at": datetime.now(UTC).isoformat(),
        "approved": edl.get("human_approved", False),
        "responsible_use_accepted": edl.get("responsible_use_accepted", False),
        "responsible_use_agreement_version": edl.get("responsible_use_agreement_version"),
        "responsible_use_accepted_at": edl.get("responsible_use_accepted_at"),
        "master_audio_camera": edl["project"].get("master_audio_camera"),
        "silent_export": edl["project"].get("silent_export", False),
        "override_count": sum(item["selected_camera"] != item["recommended_camera"] for item in segments),
        "boundary_adjustment_count": sum(item.get("boundary_changed", False) for item in segments) // 2,
        "validation": validation,
    }
