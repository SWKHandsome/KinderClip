from __future__ import annotations

from pathlib import Path

import pytest

from kinderclip.edl_generator import adjust_boundary, generate_draft_edl, update_review_segment
from kinderclip.persistence import load_json, save_json_atomic


def make_analysis(candidate_factory):
    windows = [{"start": index * 10.0, "end": (index + 1) * 10.0} for index in range(6)]
    return {
        "windows": windows,
        "cameras": {
            "front": {"windows": [candidate_factory(85) for _ in windows]},
            "wide": {"windows": [candidate_factory(75) for _ in windows]},
        },
    }


def make_edl(cameras, candidate_factory):
    analysis = make_analysis(candidate_factory)
    recommendations = [
        {"camera_id": "front" if index % 2 == 0 else "wide", "technical_score": 85,
         "component_scores": {}, "decision_source": "highest_score", "reason": "Highest technical score"}
        for index in range(6)
    ]
    project = {"name": "KinderClip test", "ceremony_duration": 60.0, "opening_title": "Welcome", "lower_third": "Class of 2026", "closing_credit": "Thank you", "master_audio_camera": "front", "silent_export": False}
    return generate_draft_edl(project, [camera.to_dict() for camera in cameras[:2]], analysis, recommendations)


def test_generated_edl_has_stable_segment_ids(cameras, candidate_factory):
    edl = make_edl(cameras, candidate_factory)
    assert [segment["id"] for segment in edl["segments"]] == [f"segment-{index:03d}" for index in range(1, 7)]


def test_camera_override_requires_reason(cameras, candidate_factory):
    edl = make_edl(cameras, candidate_factory)
    with pytest.raises(ValueError, match="Give a reason"):
        update_review_segment(edl, "segment-001", "wide", "Cut")


def test_boundary_adjustment_updates_both_adjacent_segments(cameras, candidate_factory, config):
    edl = make_edl(cameras, candidate_factory)
    adjust_boundary(edl, 1, 11.0, config)
    assert edl["segments"][0]["end"] == 11.0
    assert edl["segments"][1]["start"] == 11.0
    assert edl["segments"][1]["boundary_adjustment"] == 1.0


def test_boundary_adjustment_rejects_too_short_segment(cameras, candidate_factory, config):
    edl = make_edl(cameras, candidate_factory)
    config["max_boundary_adjustment"] = 6.0
    with pytest.raises(ValueError, match="shorter than five"):
        adjust_boundary(edl, 1, 4.5, config)


def test_atomic_json_save_writes_valid_payload(tmp_path):
    destination = tmp_path / "reviewed_edl.json"
    save_json_atomic(destination, {"product": "KinderClip", "ok": True})
    assert load_json(destination) == {"product": "KinderClip", "ok": True}


def test_atomic_json_save_retries_a_temporary_windows_file_lock(tmp_path, monkeypatch):
    destination = tmp_path / "project.json"
    real_replace = __import__("os").replace
    calls = 0

    def locked_once(source, target):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise PermissionError(5, "Access is denied", str(target))
        real_replace(source, target)

    monkeypatch.setattr("kinderclip.persistence.os.replace", locked_once)
    monkeypatch.setattr("kinderclip.persistence.time.sleep", lambda _: None)
    save_json_atomic(destination, {"project": "saved"})
    assert calls == 2
    assert load_json(destination) == {"project": "saved"}


def test_atomic_json_save_rejects_invalid_payload(tmp_path):
    destination = tmp_path / "reviewed_edl.json"
    with pytest.raises(ValueError, match="Refusing"):
        save_json_atomic(destination, {"ok": False}, validator=lambda _: ["bad document"])
    assert not destination.exists()
