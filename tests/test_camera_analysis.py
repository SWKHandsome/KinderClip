from __future__ import annotations

import cv2
import numpy as np

from kinderclip.camera_analyzer import analyse_frames, brightness_metrics, regional_motion, sharpness
from kinderclip.camera_scorer import technical_score


def checkerboard(size: int = 180) -> np.ndarray:
    grid = np.indices((size, size)).sum(axis=0) % 2 * 255
    return cv2.cvtColor(grid.astype(np.uint8), cv2.COLOR_GRAY2BGR)


def test_clear_frame_has_more_sharpness_than_blurred_copy():
    clear = checkerboard()
    blurred = cv2.GaussianBlur(clear, (21, 21), 0)
    assert sharpness(clear) > sharpness(blurred)


def test_normal_brightness_scores_above_dark_brightness(config):
    normal = np.full((90, 90, 3), 128, dtype=np.uint8)
    dark = np.full((90, 90, 3), 5, dtype=np.uint8)
    normal_result = analyse_frames([normal, normal], config)
    dark_result = analyse_frames([dark, dark], config)
    assert normal_result["components"]["brightness_score"] > dark_result["components"]["brightness_score"]


def test_regional_and_global_motion_are_distinct(config):
    base = np.zeros((90, 90, 3), dtype=np.uint8)
    local = base.copy()
    local[:30, :30] = 255
    global_frame = np.full((90, 90, 3), 255, dtype=np.uint8)
    local_motion = regional_motion(base, local, config["motion_threshold"])
    global_motion = regional_motion(base, global_frame, config["motion_threshold"])
    assert local_motion["global_motion_ratio"] < global_motion["global_motion_ratio"]


def test_black_sequence_is_flagged_and_penalised(config):
    black = np.zeros((90, 90, 3), dtype=np.uint8)
    measurement = analyse_frames([black, black], config)
    scored = technical_score(measurement, config)
    assert measurement["black_frame"]
    assert scored["technical_score"] == 0.0


def test_global_motion_adds_shake_penalty(config):
    base = np.zeros((90, 90, 3), dtype=np.uint8)
    moving = np.full((90, 90, 3), 255, dtype=np.uint8)
    result = analyse_frames([base, moving], config)
    assert result["shake_penalty"] > 0
