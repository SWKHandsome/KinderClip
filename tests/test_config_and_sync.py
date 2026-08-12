from __future__ import annotations

import pytest

from kinderclip.config import default_config, validate_config
from kinderclip.models import CameraInfo
from kinderclip.sync_manager import (
    camera_availability_on_main_timeline,
    main_timeline_duration,
    main_timeline_source_time,
    shared_timeline_duration,
    source_time,
    sync_config,
    validate_clap_timestamp,
)


def test_default_scoring_weights_are_valid():
    assert validate_config(default_config()) == []


def test_rejects_scoring_weights_that_do_not_total_one(config):
    config["sharpness_weight"] = 0.5
    assert "positive scoring weights must total 1.0" in validate_config(config)


def test_clap_timestamp_must_be_inside_source_duration():
    assert validate_clap_timestamp(-0.1, 20.0)
    assert validate_clap_timestamp(20.0, 20.0)
    assert validate_clap_timestamp(19.9, 20.0) is None


def test_shared_duration_uses_shortest_post_clap_camera(cameras):
    assert shared_timeline_duration(cameras) == 117.0


def test_source_time_maps_shared_time_from_clap():
    assert source_time(12.5, 8.0) == 20.5


def test_sync_config_rejects_target_beyond_common_timeline(cameras):
    with pytest.raises(ValueError, match="common usable"):
        sync_config(cameras, 118.0)


def test_main_camera_timeline_keeps_early_main_video_and_maps_late_camera():
    main = CameraInfo("one", "Camera 1", "one.mp4", 120.0, 1280, 720, 30, "h264", True, clap_timestamp=57.0)
    late = CameraInfo("two", "Camera 2", "two.mp4", 43.0, 1280, 720, 30, "h264", True, clap_timestamp=0.0)
    assert main_timeline_duration([main, late], "one") == 120.0
    assert camera_availability_on_main_timeline(late, main, 120.0) == {"start": 57.0, "end": 100.0}
    assert main_timeline_source_time(57.0, 57.0, 0.0) == 0.0


def test_main_timeline_sync_config_does_not_shorten_to_late_camera():
    main = CameraInfo("one", "Camera 1", "one.mp4", 120.0, 1280, 720, 30, "h264", True, clap_timestamp=57.0)
    late = CameraInfo("two", "Camera 2", "two.mp4", 43.0, 1280, 720, 30, "h264", True, clap_timestamp=0.0)
    result = sync_config([main, late], 90.0, "one")
    assert result["timeline_mode"] == "main_camera"
    assert result["main_timeline_duration"] == 120.0
    assert result["camera_availability"]["two"] == {"start": 57.0, "end": 90.0}
