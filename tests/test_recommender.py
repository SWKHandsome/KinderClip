from __future__ import annotations

from kinderclip.camera_recommender import count_switches, recommend_cameras


def test_first_window_uses_highest_score(config, candidate_factory):
    result = recommend_cameras([{"a": candidate_factory(80), "b": candidate_factory(70)}], config)
    assert result[0]["camera_id"] == "a"
    assert result[0]["decision_source"] == "highest_score"


def test_small_score_change_does_not_switch_camera(config, candidate_factory):
    windows = [
        {"a": candidate_factory(80), "b": candidate_factory(65)},
        {"a": candidate_factory(75), "b": candidate_factory(83)},
    ]
    result = recommend_cameras(windows, config)
    assert [item["camera_id"] for item in result] == ["a", "a"]


def test_mandatory_variety_uses_acceptable_alternative(config, candidate_factory):
    config["max_consecutive_windows"] = 2
    windows = [{"a": candidate_factory(85), "b": candidate_factory(60)} for _ in range(3)]
    result = recommend_cameras(windows, config)
    assert result[2]["camera_id"] == "b"
    assert result[2]["decision_source"] == "mandatory_variety"


def test_continuity_keeps_camera_when_alternative_below_floor(config, candidate_factory):
    windows = [{"a": candidate_factory(85), "b": candidate_factory(45)} for _ in range(3)]
    result = recommend_cameras(windows, config)
    assert [item["camera_id"] for item in result] == ["a", "a", "a"]


def test_repair_pass_creates_required_switches_when_possible(config, candidate_factory):
    config["max_consecutive_windows"] = 99
    windows = [{"a": candidate_factory(90), "b": candidate_factory(80)} for _ in range(5)]
    result = recommend_cameras(windows, config)
    ids = [item["camera_id"] for item in result]
    assert len(set(ids)) >= 2
    assert count_switches(ids) >= 3
    assert any(item["decision_source"] == "compliance_repair" for item in result)
