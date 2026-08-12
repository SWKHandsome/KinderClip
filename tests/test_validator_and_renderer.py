from __future__ import annotations

import subprocess

from kinderclip.edl_generator import review_record, set_responsible_use_acceptance, update_review_segment
from kinderclip.edl_validator import validate_edl
from kinderclip.renderer import audio_mux_command, escape_drawtext, escape_font_file, join_command, segment_command, title_card_command
from tests.test_edl_and_persistence import make_edl


def reviewed_edl(cameras, candidate_factory):
    edl = make_edl(cameras, candidate_factory)
    for segment in edl["segments"]:
        update_review_segment(edl, segment["id"], segment["selected_camera"], "Cut")
    edl["human_approved"] = True
    set_responsible_use_acceptance(edl, True)
    return edl


def test_validator_accepts_complete_review(cameras, candidate_factory, config):
    result = validate_edl(reviewed_edl(cameras, candidate_factory), config)
    assert result["valid"]
    assert result["final_duration"] == 66.0


def test_validator_flags_unreviewed_segment(cameras, candidate_factory, config):
    edl = reviewed_edl(cameras, candidate_factory)
    edl["segments"][0]["review_status"] = "pending"
    result = validate_edl(edl, config)
    assert any("not been reviewed" in issue["message"] for issue in result["issues"])


def test_validator_requires_responsible_use_agreement(cameras, candidate_factory, config):
    edl = reviewed_edl(cameras, candidate_factory)
    set_responsible_use_acceptance(edl, False)
    result = validate_edl(edl, config)
    assert not result["valid"]
    assert any(issue["field"] == "responsible_use_accepted" for issue in result["issues"])


def test_responsible_use_acceptance_is_recorded_for_audit(cameras, candidate_factory, config):
    edl = reviewed_edl(cameras, candidate_factory)
    record = review_record(edl, validate_edl(edl, config))
    assert record["responsible_use_accepted"] is True
    assert record["responsible_use_agreement_version"]
    assert record["responsible_use_accepted_at"]


def test_drawtext_escaping_is_safe_for_ffmpeg_filters():
    assert escape_drawtext("Kid: 100%\\great") == "Kid\\: 100\\%\\\\great"


def test_windows_font_path_is_explicitly_escaped_for_ffmpeg_filters():
    assert escape_font_file(r"C:\Windows\Fonts\arial.ttf") == "C\\:/Windows/Fonts/arial.ttf"


def test_renderer_commands_include_required_output_properties(tmp_path, config):
    title = title_card_command("Welcome", tmp_path / "title.mp4", config, 3.0)
    segment = segment_command(tmp_path / "source.mp4", 8.0, 10.0, tmp_path / "segment.mp4", config, "Class")
    joined = join_command(tmp_path / "a.mp4", tmp_path / "b.mp4", tmp_path / "joined.mp4", "Crossfade", 13.0, config)
    assert "libx264" in title and "yuv420p" in title
    assert "fontfile=" in title[title.index("-vf") + 1]
    assert "-an" in segment and "scale=1280:720" in segment[segment.index("-vf") + 1]
    assert "xfade=transition=fade" in joined[joined.index("-filter_complex") + 1]


def test_audio_command_delays_audio_through_title(tmp_path, config):
    command = audio_mux_command(tmp_path / "visual.mp4", tmp_path / "master.mp4", 8.0, 60.0, tmp_path / "final.mp4", config, False)
    graph = command[command.index("-filter_complex") + 1]
    assert "anullsrc" in graph and "concat=n=3" in graph
    assert command[command.index("-ss") + 1] == "8.000"
