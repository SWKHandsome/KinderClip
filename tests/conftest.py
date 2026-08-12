from __future__ import annotations

import copy

import pytest

from kinderclip.config import default_config
from kinderclip.models import CameraInfo


@pytest.fixture
def config() -> dict:
    return default_config()


@pytest.fixture
def cameras() -> list[CameraInfo]:
    return [
        CameraInfo("front", "Front left", "front.mp4", 130.0, 1280, 720, 30.0, "h264", True, clap_timestamp=5.0),
        CameraInfo("wide", "Wide back", "wide.mp4", 125.0, 1280, 720, 30.0, "h264", True, clap_timestamp=8.0),
        CameraInfo("side", "Side angle", "side.mp4", 140.0, 1280, 720, 30.0, "h264", False, clap_timestamp=4.0),
    ]


def candidate(score: float, *, available: bool = True, black: bool = False) -> dict:
    return {
        "available": available,
        "black_frame": black,
        "technical_score": score,
        "component_scores": {"sharpness_score": score, "brightness_score": score, "local_motion_score": score},
    }


@pytest.fixture
def candidate_factory():
    return candidate
