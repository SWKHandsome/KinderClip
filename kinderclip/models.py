"""Typed data exchanged by KinderClip backend modules."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class CameraInfo:
    id: str
    label: str
    path: str
    duration: float
    width: int
    height: int
    frame_rate: float
    codec: str
    has_audio: bool
    readable: bool = True
    clap_timestamp: float | None = None
    error: str | None = None

    @property
    def usable_duration(self) -> float:
        if self.clap_timestamp is None:
            return 0.0
        return max(0.0, self.duration - self.clap_timestamp)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CameraInfo":
        return cls(**data)

    @property
    def source_path(self) -> Path:
        return Path(self.path)


@dataclass(slots=True)
class ValidationIssue:
    message: str
    field: str | None = None
    segment_id: str | None = None
    blocking: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
