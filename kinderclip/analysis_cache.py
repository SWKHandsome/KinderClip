"""Analysis fingerprints and cache helpers."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .persistence import load_json, save_json_atomic


def analysis_fingerprint(
    cameras: list[dict[str, Any]], duration: float, config: dict[str, Any], main_camera_id: str | None = None
) -> str:
    identities = []
    for camera in sorted(cameras, key=lambda item: item["id"]):
        path = Path(camera["path"])
        stat = path.stat() if path.exists() else None
        identities.append({
            "id": camera["id"], "path": str(path.resolve()) if path.exists() else str(path),
            "size": stat.st_size if stat else None, "mtime_ns": stat.st_mtime_ns if stat else None,
            "clap_timestamp": camera.get("clap_timestamp"),
        })
    payload = json.dumps({"cameras": identities, "duration": duration, "config": config, "main_camera_id": main_camera_id}, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def cache_path(workspace: str | Path, fingerprint: str) -> Path:
    return Path(workspace) / "cache" / f"analysis-{fingerprint}.json"


def load_cached_analysis(workspace: str | Path, fingerprint: str) -> dict[str, Any] | None:
    return load_json(cache_path(workspace, fingerprint))


def save_cached_analysis(workspace: str | Path, fingerprint: str, payload: dict[str, Any]) -> None:
    save_json_atomic(cache_path(workspace, fingerprint), payload)
