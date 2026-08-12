"""Project workspace and Streamlit session-state helpers."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .persistence import load_json, save_json_atomic


def safe_project_slug(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "kinderclip-project"


def project_workspace(name: str, root: str | Path = "projects") -> Path:
    return Path(root) / safe_project_slug(name)


def project_file(workspace: str | Path) -> Path:
    return Path(workspace) / "project.json"


def has_project_name_conflict(
    name: str,
    root: str | Path = "projects",
    current_workspace: str | Path | None = None,
) -> bool:
    """Return whether a new project name would reuse another saved workspace."""
    candidate = project_workspace(name, root)
    if not project_file(candidate).is_file():
        return False
    if current_workspace is None:
        return True
    return candidate.resolve() != Path(current_workspace).resolve()


def save_project(workspace: str | Path, project: dict[str, Any]) -> None:
    save_json_atomic(project_file(workspace), project)


def load_project(workspace: str | Path) -> dict[str, Any] | None:
    return load_json(project_file(workspace))


def list_saved_projects(root: str | Path) -> list[dict[str, Any]]:
    """Return valid local KinderClip projects, newest first, without reading media."""
    base = Path(root)
    if not base.exists():
        return []
    projects: list[dict[str, Any]] = []
    for workspace in base.iterdir():
        if not workspace.is_dir():
            continue
        project = load_project(workspace)
        if isinstance(project, dict) and project.get("name"):
            projects.append({
                "workspace": str(workspace), "name": str(project["name"]),
                "updated_at": project_file(workspace).stat().st_mtime,
            })
    return sorted(projects, key=lambda item: item["updated_at"], reverse=True)


def _send_to_recycle_bin(path: Path) -> None:
    """Import lazily so normal project use does not depend on this optional action."""
    try:
        from send2trash import send2trash
    except ImportError as exc:  # pragma: no cover - covered by installation instructions
        raise RuntimeError("Recycle Bin support is unavailable. Run: python -m pip install -r requirements.txt") from exc
    send2trash(str(path))


def recycle_project(workspace: str | Path, root: str | Path) -> None:
    """Safely move one direct child project workspace to the operating-system Recycle Bin."""
    projects_root = Path(root).resolve()
    candidate = Path(workspace).resolve()
    if candidate.parent != projects_root or not candidate.is_dir() or not project_file(candidate).is_file():
        raise ValueError("Only a saved KinderClip project inside the projects folder can be deleted.")
    _send_to_recycle_bin(candidate)


def initialise_session(state: Any) -> None:
    state.setdefault("kinderclip_workspace", None)
    state.setdefault("kinderclip_step", "Home")
    state.setdefault("kinderclip_segment_index", 0)
    state.setdefault("kinderclip_pending_delete", None)


def clear_downstream(workspace: str | Path) -> None:
    for name in ("sync_config.json", "camera_analysis.json", "draft_edl.json", "reviewed_edl.json", "review_record.json"):
        candidate = Path(workspace) / name
        if candidate.exists():
            candidate.unlink()
