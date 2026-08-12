"""Configuration loading and validation."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any


DEFAULT_CONFIG: dict[str, Any] = {
    "window_seconds": 10.0,
    "sample_fps": 1.0,
    "analysis_width": 640,
    "analysis_height": 360,
    "output_width": 1280,
    "output_height": 720,
    "output_fps": 30,
    "sharpness_reference": 500.0,
    "brightness_target": 128.0,
    "brightness_tolerance": 72.0,
    "dark_pixel_threshold": 25.0,
    "bright_pixel_threshold": 235.0,
    "black_frame_fraction": 0.8,
    "motion_threshold": 12.0,
    "global_motion_threshold": 0.6,
    "max_shake_penalty": 30.0,
    "black_frame_penalty": 100.0,
    "sharpness_weight": 0.45,
    "brightness_weight": 0.30,
    "local_motion_weight": 0.25,
    "switch_threshold": 10.0,
    "quality_floor": 50.0,
    "max_consecutive_windows": 2,
    "repair_score_gap": 15.0,
    "min_segment_seconds": 5.0,
    "max_boundary_adjustment": 2.0,
    "boundary_step": 0.5,
    "transition_seconds": 0.5,
    "audio_fade_seconds": 0.5,
    "title_seconds": 3.0,
    "credits_seconds": 3.0,
    "font_file": "",
}


def default_config() -> dict[str, Any]:
    return deepcopy(DEFAULT_CONFIG)


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    config = default_config()
    if path is not None and Path(path).exists():
        with Path(path).open(encoding="utf-8") as handle:
            config.update(json.load(handle))
    errors = validate_config(config)
    if errors:
        raise ValueError("Invalid analysis configuration: " + "; ".join(errors))
    return config


def validate_config(config: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    positive = (
        "window_seconds", "sample_fps", "analysis_width", "analysis_height",
        "output_width", "output_height", "output_fps", "sharpness_reference",
        "brightness_tolerance", "motion_threshold", "max_shake_penalty",
        "black_frame_penalty", "switch_threshold", "quality_floor",
        "min_segment_seconds", "max_boundary_adjustment", "boundary_step",
        "transition_seconds", "audio_fade_seconds", "title_seconds", "credits_seconds",
    )
    for key in positive:
        if float(config.get(key, 0)) <= 0:
            errors.append(f"{key} must be greater than zero")
    for key in ("black_frame_fraction", "global_motion_threshold"):
        if not 0 <= float(config.get(key, -1)) <= 1:
            errors.append(f"{key} must be between 0 and 1")
    if not 0 <= float(config.get("dark_pixel_threshold", -1)) < 256:
        errors.append("dark_pixel_threshold must be between 0 and 255")
    if not 0 <= float(config.get("bright_pixel_threshold", -1)) < 256:
        errors.append("bright_pixel_threshold must be between 0 and 255")
    if float(config.get("dark_pixel_threshold", 0)) >= float(config.get("bright_pixel_threshold", 0)):
        errors.append("dark_pixel_threshold must be lower than bright_pixel_threshold")
    weight_total = sum(float(config.get(key, 0)) for key in (
        "sharpness_weight", "brightness_weight", "local_motion_weight"
    ))
    if abs(weight_total - 1.0) > 0.0001:
        errors.append("positive scoring weights must total 1.0")
    if int(config.get("max_consecutive_windows", 0)) < 1:
        errors.append("max_consecutive_windows must be at least 1")
    return errors
