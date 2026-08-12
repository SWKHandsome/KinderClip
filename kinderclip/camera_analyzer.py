"""CPU-only technical frame measurements; no semantic video inference."""

from __future__ import annotations

from typing import Any, Iterable

import numpy as np


def _cv2():
    import cv2
    return cv2


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def sharpness(frame: np.ndarray) -> float:
    cv2 = _cv2()
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def brightness_metrics(frame: np.ndarray, dark_threshold: float, bright_threshold: float) -> dict[str, float]:
    cv2 = _cv2()
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame
    return {
        "mean": float(np.mean(gray)),
        "dark_fraction": float(np.mean(gray < dark_threshold)),
        "bright_fraction": float(np.mean(gray > bright_threshold)),
    }


def regional_motion(previous: np.ndarray, current: np.ndarray, threshold: float) -> dict[str, float]:
    cv2 = _cv2()
    previous_gray = cv2.cvtColor(previous, cv2.COLOR_BGR2GRAY) if previous.ndim == 3 else previous
    current_gray = cv2.cvtColor(current, cv2.COLOR_BGR2GRAY) if current.ndim == 3 else current
    difference = cv2.absdiff(previous_gray, current_gray)
    height, width = difference.shape[:2]
    values: list[float] = []
    for row in range(3):
        for column in range(3):
            y0, y1 = row * height // 3, (row + 1) * height // 3
            x0, x1 = column * width // 3, (column + 1) * width // 3
            values.append(float(np.mean(difference[y0:y1, x0:x1])))
    active = sum(value >= threshold for value in values)
    return {
        "regional_difference": float(np.mean(values)),
        "active_regions": float(active),
        "global_motion_ratio": active / 9.0,
    }


def analyse_frames(frames: Iterable[np.ndarray], config: dict[str, Any]) -> dict[str, Any]:
    samples = list(frames)
    if not samples:
        return {
            "available": False, "reason": "No readable samples", "raw": {},
            "components": {"sharpness_score": 0.0, "brightness_score": 0.0, "local_motion_score": 0.0},
            "black_frame": True, "shake_penalty": 0.0,
        }
    sharpness_values = [sharpness(frame) for frame in samples]
    brightness = [brightness_metrics(frame, config["dark_pixel_threshold"], config["bright_pixel_threshold"]) for frame in samples]
    movement = [regional_motion(samples[index - 1], samples[index], config["motion_threshold"]) for index in range(1, len(samples))]
    mean_sharpness = float(np.mean(sharpness_values))
    mean_brightness = float(np.mean([item["mean"] for item in brightness]))
    dark_fraction = float(np.mean([item["dark_fraction"] for item in brightness]))
    bright_fraction = float(np.mean([item["bright_fraction"] for item in brightness]))
    black_fraction = float(np.mean([item["mean"] < config["dark_pixel_threshold"] for item in brightness]))
    global_ratio = float(np.mean([item["global_motion_ratio"] for item in movement])) if movement else 0.0
    regional_difference = float(np.mean([item["regional_difference"] for item in movement])) if movement else 0.0
    active_ratio = float(np.mean([item["active_regions"] / 9.0 for item in movement])) if movement else 0.0
    brightness_score = _clamp(100.0 * (1.0 - abs(mean_brightness - config["brightness_target"]) / config["brightness_tolerance"]))
    brightness_score = _clamp(brightness_score - ((dark_fraction + bright_fraction) * 30.0))
    sharpness_score = _clamp(100.0 * mean_sharpness / config["sharpness_reference"])
    excess_global = max(0.0, global_ratio - config["global_motion_threshold"])
    denominator = max(0.0001, 1.0 - config["global_motion_threshold"])
    shake_penalty = config["max_shake_penalty"] * excess_global / denominator
    local_motion_score = _clamp(100.0 * active_ratio * (1.0 - min(1.0, excess_global / denominator)))
    black_frame = black_fraction >= config["black_frame_fraction"]
    return {
        "available": True,
        "black_frame": black_frame,
        "raw": {
            "sharpness": mean_sharpness,
            "brightness": mean_brightness,
            "dark_pixel_fraction": dark_fraction,
            "bright_pixel_fraction": bright_fraction,
            "black_sample_fraction": black_fraction,
            "regional_difference": regional_difference,
            "global_motion_ratio": global_ratio,
            "local_active_ratio": active_ratio,
        },
        "components": {
            "sharpness_score": sharpness_score,
            "brightness_score": brightness_score,
            "local_motion_score": local_motion_score,
        },
        "shake_penalty": round(shake_penalty, 4),
        "black_frame_penalty": config["black_frame_penalty"] if black_frame else 0.0,
    }
