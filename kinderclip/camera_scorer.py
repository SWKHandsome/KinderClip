"""Technical scoring only; continuity rules intentionally live elsewhere."""

from __future__ import annotations

from typing import Any


def technical_score(measurement: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    components = measurement.get("components", {})
    sharpness = float(components.get("sharpness_score", 0.0))
    brightness = float(components.get("brightness_score", 0.0))
    local_motion = float(components.get("local_motion_score", 0.0))
    shake = float(measurement.get("shake_penalty", 0.0))
    black = float(measurement.get("black_frame_penalty", 0.0))
    score = (
        config["sharpness_weight"] * sharpness
        + config["brightness_weight"] * brightness
        + config["local_motion_weight"] * local_motion
        - shake - black
    )
    return {
        **measurement,
        "technical_score": round(max(0.0, min(100.0, score)), 4),
        "component_scores": {
            "sharpness_score": round(sharpness, 4),
            "brightness_score": round(brightness, 4),
            "local_motion_score": round(local_motion, 4),
            "shake_penalty": round(shake, 4),
            "black_frame_penalty": round(black, 4),
        },
    }
