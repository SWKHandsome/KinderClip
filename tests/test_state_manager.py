from __future__ import annotations

import os

import pytest

from kinderclip.state_manager import has_project_name_conflict, list_saved_projects, recycle_project, save_project


def test_saved_projects_are_discovered_newest_first(tmp_path):
    older = tmp_path / "older"
    newer = tmp_path / "newer"
    save_project(older, {"name": "Older graduation"})
    save_project(newer, {"name": "Newer graduation"})
    os.utime(older / "project.json", (100, 100))
    os.utime(newer / "project.json", (200, 200))
    discovered = list_saved_projects(tmp_path)
    assert [item["name"] for item in discovered] == ["Newer graduation", "Older graduation"]


def test_project_name_conflict_blocks_new_project_but_allows_its_current_project(tmp_path):
    workspace = tmp_path / "graduation-2026"
    save_project(workspace, {"name": "Graduation 2026"})
    assert has_project_name_conflict("Graduation 2026", tmp_path)
    assert not has_project_name_conflict("Graduation 2026", tmp_path, workspace)


def test_recycle_project_delegates_only_a_direct_saved_project(tmp_path, monkeypatch):
    workspace = tmp_path / "demo"
    save_project(workspace, {"name": "Demo"})
    moved: list[str] = []
    monkeypatch.setattr("kinderclip.state_manager._send_to_recycle_bin", lambda path: moved.append(str(path)))
    recycle_project(workspace, tmp_path)
    assert moved == [str(workspace.resolve())]


def test_recycle_project_rejects_paths_outside_projects_folder(tmp_path):
    outside = tmp_path.parent / "outside-project"
    outside.mkdir(exist_ok=True)
    save_project(outside, {"name": "Outside"})
    with pytest.raises(ValueError, match="Only a saved KinderClip project"):
        recycle_project(outside, tmp_path)
