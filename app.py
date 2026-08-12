"""KinderClip Streamlit application."""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Any

import streamlit as st

from kinderclip.analysis_pipeline import run_analysis
from kinderclip.audio_manager import validate_master_audio
from kinderclip.camera_recommender import count_switches, recommend_cameras
from kinderclip.config import load_config
from kinderclip.edl_generator import (
    adjust_boundary,
    generate_draft_edl,
    review_record,
    set_responsible_use_acceptance,
    update_review_segment,
)
from kinderclip.edl_validator import validate_edl
from kinderclip.frame_sampler import sample_frame
from kinderclip.media_probe import media_preflight_message, probe_media
from kinderclip.models import CameraInfo
from kinderclip.persistence import load_json, save_json_atomic
from kinderclip.renderer import cleanup_temporary_files, render_edl
from kinderclip.state_manager import (
    initialise_session,
    list_saved_projects,
    load_project,
    project_workspace,
    recycle_project,
    save_project,
)
from kinderclip.sync_manager import (
    camera_availability_on_main_timeline,
    main_timeline_duration,
    main_timeline_source_time,
    sync_config,
    validate_clap_timestamp,
)


ROOT = Path(__file__).resolve().parent
BASE_CONFIG = load_config(ROOT / "analysis_config.json")
STEPS = ["Home", "Project setup", "Synchronisation", "Camera analysis", "Review edit", "Export"]


def _identifier(name: str, index: int) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return cleaned or f"camera_{index + 1}"


def _project_name_conflicts(name: str, current_workspace: Path | None) -> bool:
    """Check whether a new setup would overwrite another saved project."""
    candidate = project_workspace(name, ROOT / "projects")
    if not (candidate / "project.json").is_file():
        return False
    return current_workspace is None or candidate.resolve() != current_workspace.resolve()


def _workspace() -> Path | None:
    value = st.session_state.get("kinderclip_workspace")
    return Path(value) if value else None


def _project() -> dict[str, Any] | None:
    workspace = _workspace()
    return load_project(workspace) if workspace else None


def _cameras(project: dict[str, Any] | None = None) -> list[CameraInfo]:
    loaded = project or _project() or {}
    return [CameraInfo.from_dict(item) for item in loaded.get("cameras", [])]


def _save_edl(edl: dict[str, Any]) -> None:
    workspace = _workspace()
    if workspace is None:
        raise RuntimeError("Create a project first.")
    save_json_atomic(workspace / "reviewed_edl.json", edl)


def _edl() -> dict[str, Any] | None:
    workspace = _workspace()
    return load_json(workspace / "reviewed_edl.json") if workspace else None


def _available_step(project: dict[str, Any] | None, workspace: Path | None) -> int:
    if not project or len([camera for camera in _cameras(project) if camera.readable]) < 2:
        return 1
    if not workspace or not (workspace / "sync_config.json").exists():
        return 2
    if not (workspace / "camera_analysis.json").exists():
        return 3
    if not (workspace / "reviewed_edl.json").exists():
        return 4
    return 5


def _resume_step(project: dict[str, Any], workspace: Path) -> str:
    """Choose the first incomplete workflow stage for a restored project."""
    if not (workspace / "sync_config.json").exists():
        return "Synchronisation"
    if not (workspace / "camera_analysis.json").exists():
        return "Camera analysis"
    edl = load_json(workspace / "reviewed_edl.json")
    if not edl or any(segment.get("review_status") not in {"reviewed", "overridden"} for segment in edl.get("segments", [])):
        return "Review edit"
    return "Export"


def _sidebar(project: dict[str, Any] | None, workspace: Path | None) -> str:
    unlocked = _available_step(project, workspace)
    current = st.session_state.get("kinderclip_step", STEPS[0])
    if STEPS.index(current) > unlocked:
        current = STEPS[unlocked]
    with st.sidebar:
        st.title("KinderClip")
        st.caption("Local multi-camera graduation video editor")
        for index, step in enumerate(STEPS):
            if index < unlocked:
                status = "Complete"
            elif index == unlocked:
                status = "In progress"
            else:
                status = "Locked"
            st.markdown(f"**{index + 1}. {step}**  \n:small_blue_diamond: {status}")
        st.divider()
        if project:
            st.caption(f"Project: {project['name']}")
            st.caption(f"Ceremony duration: {project['ceremony_duration']:.0f} seconds")
        choices = STEPS[: unlocked + 1]
        selected = st.radio("Go to", choices, index=choices.index(current), label_visibility="collapsed")
    st.session_state["kinderclip_step"] = selected
    return selected


def _project_status(workspace: Path) -> str:
    if (workspace / "final_video.mp4").exists():
        return "Final video rendered"
    edl = load_json(workspace / "reviewed_edl.json")
    if edl:
        reviewed = sum(segment.get("review_status") in {"reviewed", "overridden"} for segment in edl.get("segments", []))
        return f"Review: {reviewed} of {len(edl.get('segments', []))} segments complete"
    if (workspace / "camera_analysis.json").exists():
        return "Analysis complete — review ready"
    if (workspace / "sync_config.json").exists():
        return "Synchronisation complete — analysis ready"
    return "Project setup needs synchronisation"


def _render_progress_percent(message: str) -> int:
    """Convert deterministic renderer stages into an honest, monotonic UI estimate."""
    message_lower = message.lower()
    segment_match = re.search(r"rendered segment (\d+) of (\d+)", message_lower)
    join_match = re.search(r"joining visual stage (\d+) of (\d+)", message_lower)
    if "opening title" in message_lower:
        return 5
    if "rendering ceremony segments" in message_lower:
        return 10
    if segment_match:
        complete, total = (int(value) for value in segment_match.groups())
        return min(70, 10 + round(60 * complete / max(1, total)))
    if "closing credits" in message_lower:
        return 72
    if join_match:
        complete, total = (int(value) for value in join_match.groups())
        return min(92, 74 + round(18 * complete / max(1, total)))
    if "continuous master audio" in message_lower:
        return 95
    if "completed" in message_lower:
        return 100
    return 1


def home_page() -> None:
    st.header("Welcome to KinderClip")
    st.write("Choose a saved project to continue, or create a new graduation video project.")
    st.markdown(
        """
        <style>
        div[class*="st-key-create_new_project"] button {
            background-color: #16a34a !important;
            border-color: #16a34a !important;
            color: #ffffff !important;
        }
        div[class*="st-key-delete_project_"] button,
        div[class*="st-key-confirm_delete_"] button {
            background-color: #dc2626 !important;
            border-color: #dc2626 !important;
            color: #ffffff !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    if st.button("Create new project", key="create_new_project", type="primary"):
        st.session_state["kinderclip_workspace"] = None
        st.session_state["kinderclip_segment_index"] = 0
        st.session_state["kinderclip_step"] = "Project setup"
        st.rerun()
    saved_projects = list_saved_projects(ROOT / "projects")
    if not saved_projects:
        st.info("No saved projects yet. Create a new project to begin.")
        return
    st.subheader("Saved projects")
    pending_delete = st.session_state.get("kinderclip_pending_delete")
    for saved in saved_projects:
        workspace = Path(saved["workspace"])
        project = load_project(workspace)
        if not project:
            continue
        slug = workspace.name
        with st.container(border=True):
            info, continue_column, delete_column = st.columns([5, 1.4, 1.4])
            with info:
                st.markdown(f"**{project['name']}**")
                st.caption(f"{_project_status(workspace)} · Ceremony footage: {project.get('ceremony_duration', 0):.0f} seconds")
            if continue_column.button("Continue", key=f"continue_project_{slug}", type="primary"):
                st.session_state["kinderclip_workspace"] = str(workspace)
                st.session_state["kinderclip_segment_index"] = 0
                st.session_state["kinderclip_step"] = _resume_step(project, workspace)
                st.rerun()
            if delete_column.button("Delete", key=f"delete_project_{slug}", type="primary"):
                st.session_state["kinderclip_pending_delete"] = str(workspace)
                st.rerun()
            if pending_delete == str(workspace):
                st.warning(f"Delete '{project['name']}'? Its uploaded videos, analysis files, and final video will move to the Windows Recycle Bin.")
                confirmation = st.checkbox("I understand this project will be removed from KinderClip.", key=f"delete_confirmation_{slug}")
                cancel, confirm, _ = st.columns([1.2, 1.4, 5])
                if cancel.button("Cancel", key=f"cancel_delete_{slug}"):
                    st.session_state["kinderclip_pending_delete"] = None
                    st.rerun()
                if confirm.button("Move to Recycle Bin", key=f"confirm_delete_{slug}", type="primary", disabled=not confirmation):
                    try:
                        recycle_project(workspace, ROOT / "projects")
                    except (RuntimeError, ValueError) as exc:
                        st.error(str(exc))
                    else:
                        if _workspace() == workspace:
                            st.session_state["kinderclip_workspace"] = None
                            st.session_state["kinderclip_segment_index"] = 0
                        st.session_state["kinderclip_pending_delete"] = None
                        st.success(f"'{project['name']}' was moved to the Windows Recycle Bin.")
                        st.rerun()


def _save_upload(upload: Any, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("wb") as handle:
        handle.write(upload.getbuffer())


def _next_step_button(label: str, key: str, destination: str, container: Any | None = None) -> None:
    """Render a navigation-only green button; it never repeats the current action."""
    st.markdown(
        """
        <style>
        .st-key-next_to_synchronisation button,
        .st-key-next_to_analysis button,
        .st-key-next_to_review button,
        .st-key-next_to_export button {
            background-color: #16a34a !important;
            border-color: #16a34a !important;
            color: #ffffff !important;
        }
        .st-key-next_to_synchronisation button:hover,
        .st-key-next_to_analysis button:hover,
        .st-key-next_to_review button:hover,
        .st-key-next_to_export button:hover {
            background-color: #15803d !important;
            border-color: #15803d !important;
            color: #ffffff !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    target = container or st
    if target.button(label, key=key, type="primary"):
        st.session_state["kinderclip_step"] = destination
        st.rerun()


def project_setup(preflight: str | None) -> None:
    st.header("Project setup")
    st.write("Create a KinderClip project and inspect two to four local MP4 camera recordings.")
    existing = _project() or {}
    with st.form("project_setup_form", clear_on_submit=False):
        name = st.text_input("Project name", value=existing.get("name", "KinderClip graduation"))
        ceremony_duration = st.number_input("Ceremony footage duration (seconds)", min_value=60.0, max_value=174.0, step=1.0, value=float(existing.get("ceremony_duration", 90.0)), help="Three-second title and credits clips make the final video six seconds longer.")
        opening_title = st.text_input("Opening title", value=existing.get("opening_title", "Kindergarten Graduation"))
        lower_third = st.text_input("Lower-third text", value=existing.get("lower_third", "Class of 2026"))
        closing_credit = st.text_input("Closing credit", value=existing.get("closing_credit", "Thank you to our families and teachers"))
        uploads = st.file_uploader("Camera recordings (2–4 MP4 files)", type=["mp4"], accept_multiple_files=True)
        labels: dict[int, str] = {}
        for index, upload in enumerate(uploads or []):
            labels[index] = st.text_input(
                f"Camera {index + 1} label", value=Path(upload.name).stem.replace("_", " ").title(), key=f"upload-label-{index}"
            )
        inspect = st.form_submit_button("Inspect videos", disabled=preflight is not None)
    if preflight:
        st.warning(preflight)
    if not inspect:
        if existing and len([camera for camera in _cameras(existing) if camera.readable]) >= 2:
            st.success("Project setup is complete. Continue when you are ready to synchronise the cameras.")
            _next_step_button("Next: Synchronisation", "next_to_synchronisation", "Synchronisation")
        return
    if not name.strip() or not opening_title.strip() or not lower_third.strip() or not closing_credit.strip():
        st.error("Enter a project name, opening title, lower-third text, and closing credit.")
        return
    if not uploads or not 2 <= len(uploads) <= 4:
        st.error("Upload between two and four MP4 camera recordings.")
        return
    if any(not label.strip() for label in labels.values()) or len({label.strip().casefold() for label in labels.values()}) != len(labels):
        st.error("Give every camera a unique, non-empty label.")
        return
    workspace = project_workspace(name, ROOT / "projects")
    if _project_name_conflicts(name, _workspace()):
        saved_project = load_project(workspace) or {}
        saved_name = saved_project.get("name", name.strip())
        st.error(
            f"A project named '{saved_name}' already exists. Choose a different project name, "
            "or return to Home and select Continue for the existing project."
        )
        return
    if workspace.exists() and (workspace / "camera_analysis.json").exists():
        st.warning("Inspecting replacement files starts a new setup and removes the previous analysis and draft edit.")
        for artifact in ("sync_config.json", "camera_analysis.json", "draft_edl.json", "reviewed_edl.json", "review_record.json"):
            target = workspace / artifact
            if target.exists():
                target.unlink()
    source_dir = workspace / "sources"
    cameras: list[dict[str, Any]] = []
    for index, upload in enumerate(uploads):
        label = labels[index].strip()
        camera_id = _identifier(label, index)
        destination = source_dir / f"{camera_id}.mp4"
        _save_upload(upload, destination)
        media = probe_media(destination, camera_id, label)
        cameras.append(media.to_dict())
    readable = [camera for camera in cameras if camera["readable"]]
    project = {
        "product": "KinderClip", "name": name.strip(), "ceremony_duration": float(ceremony_duration),
        "opening_title": opening_title.strip(), "lower_third": lower_third.strip(), "closing_credit": closing_credit.strip(),
        "cameras": cameras, "main_camera_id": None, "master_audio_camera": None, "silent_export": False,
    }
    save_project(workspace, project)
    st.session_state["kinderclip_workspace"] = str(workspace)
    st.session_state["kinderclip_segment_index"] = 0
    if len(readable) < 2:
        st.error("Fewer than two recordings could be read. Replace the failed files shown below.")
    else:
        st.success(f"Inspected {len(readable)} readable camera recordings.")
        _next_step_button("Next: Synchronisation", "next_to_synchronisation", "Synchronisation")
    for camera in cameras:
        status = "Ready" if camera["readable"] else camera.get("error", "Unreadable")
        st.info(f"{camera['label']}: {camera['duration']:.1f}s, {camera['width']}×{camera['height']}, audio: {'available' if camera['has_audio'] else 'not available'} — {status}")


def synchronisation(preflight: str | None) -> None:
    st.header("Synchronisation")
    st.write("Choose the continuous main video, then enter where the same clap appears inside every recording. Other cameras are used only when they overlap the main video.")
    project = _project()
    if not project:
        st.info("Create a project first.")
        return
    cameras = _cameras(project)
    readable = [camera for camera in cameras if camera.readable]
    workspace = _workspace()
    assert workspace is not None
    prior_sync = load_json(workspace / "sync_config.json", {})
    existing_analysis = (workspace / "camera_analysis.json").exists()
    if preflight:
        st.warning(preflight)
    if existing_analysis:
        st.warning("Changing a clap timestamp or master-audio choice removes the current analysis and edit draft. Uploaded videos and project details remain available.")
    with st.form("sync_form"):
        clap_values: dict[str, float] = {}
        for camera in readable:
            clap_values[camera.id] = st.number_input(
                f"{camera.label} clap timestamp (seconds)", min_value=0.0, max_value=max(0.0, camera.duration - 0.001),
                value=float(camera.clap_timestamp or 0.0), step=0.1,
            )
        main_default = project.get("main_camera_id") if project.get("main_camera_id") in [camera.id for camera in readable] else readable[0].id
        main_camera_id = st.selectbox(
            "Main video timeline", [camera.id for camera in readable], index=[camera.id for camera in readable].index(main_default),
            format_func=lambda value: next(camera.label for camera in readable if camera.id == value),
            help="Use the longest recording here. KinderClip keeps it before and after other cameras become available.",
        )
        audio_options = [camera for camera in readable if camera.has_audio]
        audio_default = project.get("master_audio_camera") if project.get("master_audio_camera") in [camera.id for camera in audio_options] else (main_camera_id if main_camera_id in [camera.id for camera in audio_options] else (audio_options[0].id if audio_options else None))
        selected_audio = st.selectbox(
            "Master audio source", [camera.id for camera in audio_options], index=[camera.id for camera in audio_options].index(audio_default),
            format_func=lambda value: next(camera.label for camera in audio_options if camera.id == value),
            help="This source must cover the whole main-video timeline. Usually choose the main camera.",
        ) if audio_options else None
        silent = st.checkbox("Export without audio (explicit choice)", value=bool(project.get("silent_export", False)))
        confirm_change = st.checkbox("I understand that changing synchronisation removes the existing analysis and edit draft.") if existing_analysis else True
        save = st.form_submit_button("Save and continue", disabled=preflight is not None)
    if not save:
        if prior_sync:
            st.success("Synchronisation is already saved. Continue when you are ready to analyse the cameras.")
            _next_step_button("Next: Camera analysis", "next_to_analysis", "Camera analysis")
        return
    for camera in cameras:
        if camera.id in clap_values:
            camera.clap_timestamp = clap_values[camera.id]
    errors = [validate_clap_timestamp(camera.clap_timestamp, camera.duration) for camera in readable]
    if any(errors):
        st.error(next(error for error in errors if error))
        return
    try:
        timeline_duration = main_timeline_duration(cameras, main_camera_id)
    except ValueError as exc:
        st.error(str(exc))
        return
    if project["ceremony_duration"] > timeline_duration:
        st.error(f"The selected ceremony duration exceeds the main camera timeline of {timeline_duration:.1f} seconds.")
        return
    changed = (
        any(float(prior_sync.get("cameras", {}).get(camera.id, -1)) != float(camera.clap_timestamp or 0.0) for camera in readable)
        or prior_sync.get("main_camera_id") != main_camera_id
        or prior_sync.get("master_audio_camera") != selected_audio
        or bool(prior_sync.get("silent_export", False)) != silent
    )
    if existing_analysis and changed and not confirm_change:
        st.error("Confirm the synchronisation change before replacing the current analysis and edit draft.")
        return
    project["cameras"] = [camera.to_dict() for camera in cameras]
    project["main_camera_id"] = main_camera_id
    project["master_audio_camera"] = selected_audio
    project["silent_export"] = silent
    audio_errors = validate_master_audio(cameras, selected_audio, project["ceremony_duration"], silent, main_camera_id)
    if audio_errors:
        st.error(audio_errors[0])
        return
    if existing_analysis and changed:
        for artifact in ("camera_analysis.json", "draft_edl.json", "reviewed_edl.json", "review_record.json"):
            target = workspace / artifact
            if target.exists():
                target.unlink()
    save_project(workspace, project)
    details = sync_config(cameras, project["ceremony_duration"], main_camera_id) | {"master_audio_camera": selected_audio, "silent_export": silent}
    save_json_atomic(workspace / "sync_config.json", details)
    st.success(f"Synchronisation saved. Main video timeline: {timeline_duration:.1f} seconds.")
    st.caption("Other cameras are used only inside these available intervals on the main timeline:")
    for camera in readable:
        interval = details["camera_availability"][camera.id]
        st.write(f"{camera.label}: {interval['start']:.1f}–{interval['end']:.1f} seconds")
    _next_step_button("Next: Camera analysis", "next_to_analysis", "Camera analysis")


def camera_analysis(preflight: str | None) -> None:
    st.header("Camera analysis")
    project = _project()
    workspace = _workspace()
    if not project or not workspace:
        st.info("Complete project setup and synchronisation first.")
        return
    config = dict(BASE_CONFIG)
    st.write(f"KinderClip will analyse {len(project['cameras'])} cameras over {project['ceremony_duration']:.0f} seconds in ten-second windows.")
    with st.expander("Advanced analysis settings"):
        config["window_seconds"] = st.number_input("Analysis window (seconds)", min_value=5.0, max_value=30.0, value=float(config["window_seconds"]), step=1.0)
        config["sample_fps"] = st.number_input("Samples per second", min_value=0.5, max_value=3.0, value=float(config["sample_fps"]), step=0.5)
        config["switch_threshold"] = st.number_input("Camera-change score threshold", min_value=1.0, max_value=40.0, value=float(config["switch_threshold"]), step=1.0)
        config["quality_floor"] = st.number_input("Minimum acceptable alternative score", min_value=1.0, max_value=100.0, value=float(config["quality_floor"]), step=1.0)
    analysis_exists = (workspace / "camera_analysis.json").exists()
    if analysis_exists:
        st.warning("Starting analysis again replaces the current analysis and edit draft.")
    if preflight:
        st.warning(preflight)
    action_column, next_column, _ = st.columns([1.35, 1.2, 5])
    action_button = action_column.empty()
    action_label = "Run camera analysis again" if analysis_exists else "Start camera analysis"
    start_analysis = action_button.button(action_label, disabled=preflight is not None)
    if analysis_exists:
        _next_step_button("Next: Review edit", "next_to_review", "Review edit", next_column)
    if not start_analysis:
        return
    action_button.empty()
    action_button.button("Analysing cameras...", key="analysis_in_progress", disabled=True)
    analysis_status = st.status("Preparing camera analysis...", expanded=True)
    analysis_status.write("Reading the camera recordings and preparing analysis frames...")
    progress_bar = st.progress(0, text="Preparing analysis")
    cameras = _cameras(project)
    try:
        def report(camera_number: int, camera_count: int, completed: int, total: int) -> None:
            message = f"Analysing camera {camera_number} of {camera_count}: {completed} of {total} windows"
            progress_bar.progress(completed / max(1, total), text=message)
            analysis_status.update(label=message, state="running", expanded=True)
        analysis = run_analysis(cameras, project["ceremony_duration"], config, workspace, report, project.get("main_camera_id"))
    except Exception as exc:
        analysis_status.update(label="Camera analysis failed", state="error", expanded=True)
        st.error(f"Camera analysis could not finish: {exc}")
        return
    candidates = []
    for index in range(len(analysis["windows"])):
        candidates.append({
            camera_id: (details["windows"][index] if index < len(details.get("windows", [])) else {"available": False, "black_frame": True, "technical_score": 0.0})
            for camera_id, details in analysis["cameras"].items()
        })
    recommendations = recommend_cameras(candidates, config)
    edl = generate_draft_edl(project, [camera.to_dict() for camera in cameras], analysis, recommendations)
    save_json_atomic(workspace / "analysis_config.json", config)
    save_json_atomic(workspace / "camera_analysis.json", analysis)
    save_json_atomic(workspace / "draft_edl.json", edl)
    save_json_atomic(workspace / "reviewed_edl.json", edl)
    progress_bar.progress(1.0, text="Analysis and edit draft complete")
    analysis_status.update(label="Camera analysis complete", state="complete", expanded=False)
    st.success(f"Analysed {len(analysis['windows'])} windows and created a reviewable edit draft.")
    st.session_state["kinderclip_segment_index"] = 0
    _next_step_button("Next: Review edit", "next_to_review", "Review edit")


def _thumbnail(path: str, clap: float, timeline_time: float) -> Any | None:
    try:
        frame = sample_frame(path, clap + timeline_time, 320, 180)
        if frame is None:
            return None
        import cv2
        return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    except Exception:
        return None


def review_edit() -> None:
    st.header("Review edit")
    edl = _edl()
    workspace = _workspace()
    if not edl or not workspace:
        st.info("Run camera analysis to create an edit draft.")
        return
    config = load_json(workspace / "analysis_config.json", BASE_CONFIG)
    index = min(st.session_state.get("kinderclip_segment_index", 0), len(edl["segments"]) - 1)
    st.session_state["kinderclip_segment_index"] = index
    segment = edl["segments"][index]
    sources = {source["id"]: source for source in edl["sources"]}
    main_source = sources.get(edl["project"].get("main_camera_id", ""))
    main_clap = float(main_source.get("clap_timestamp", 0.0)) if main_source else 0.0
    st.subheader(f"Segment {index + 1} of {len(edl['segments'])}")
    st.caption(f"Timeline: {segment['start']:.1f}–{segment['end']:.1f} seconds · Status: {segment['review_status'].title()}")
    midpoint = (segment["start"] + segment["end"]) / 2
    options = [
        camera_id for camera_id, option in segment["camera_options"].items()
        if option.get("available", True) and not option.get("black_frame", False)
    ]
    cards = st.columns(max(1, len(options)))
    for column, camera_id in zip(cards, options):
        option = segment["camera_options"][camera_id]
        source = sources[camera_id]
        with column:
            file_time = main_timeline_source_time(midpoint, main_clap, float(source.get("clap_timestamp") or 0.0))
            image = _thumbnail(source["path"], 0.0, file_time)
            if image is not None:
                st.image(image, caption=source["label"], use_container_width=True)
            else:
                st.caption(f"Preview unavailable: {source['label']}")
            st.write(f"Score: {option.get('technical_score', 0):.1f}")
            if camera_id == segment["recommended_camera"]:
                st.success("System recommendation")
    st.info(f"System recommendation: **{sources.get(segment['recommended_camera'], {}).get('label', 'Unavailable')}** · {segment['recommendation_reason']} · Decision source: {segment['decision_source'].replace('_', ' ')}")
    selected = st.selectbox("Final camera", options, index=options.index(segment["selected_camera"]), key=f"camera-{segment['id']}", format_func=lambda item: sources[item]["label"])
    transition = st.selectbox("Transition", ["Cut", "Crossfade", "Fade"], index=["Cut", "Crossfade", "Fade"].index(segment.get("transition", "Cut")), key=f"transition-{segment['id']}")
    override = st.text_input("Override reason", value=segment.get("override_reason", ""), key=f"override-{segment['id']}")
    boundary = segment["start"]
    if index > 0:
        original = segment["analysis_start"]
        boundary = st.number_input(
            "Cut boundary before this segment (seconds)", min_value=float(original - config["max_boundary_adjustment"]),
            max_value=float(original + config["max_boundary_adjustment"]), value=float(segment["start"]), step=float(config["boundary_step"]), key=f"boundary-{segment['id']}",
            help="Both adjacent segments change together. KinderClip rejects cuts that make a segment shorter than five seconds.",
        )
    reviewed = sum(item["review_status"] in {"reviewed", "overridden"} for item in edl["segments"])
    chosen_ids = [item["selected_camera"] for item in edl["segments"]]
    st.caption(f"Reviewed: {reviewed} of {len(edl['segments'])} · Overrides: {sum(item['selected_camera'] != item['recommended_camera'] for item in edl['segments'])} · Cameras used: {len(set(chosen_ids))} · Switches: {count_switches(chosen_ids)}")
    previous, save, next_page = st.columns(3)

    def save_current() -> bool:
        try:
            update_review_segment(edl, segment["id"], selected, transition, override)
            if index > 0 and abs(float(boundary) - float(segment["start"])) > 0.0001:
                adjust_boundary(edl, index, float(boundary), config)
            _save_edl(edl)
            return True
        except ValueError as exc:
            st.error(str(exc))
            return False

    if previous.button("Previous", disabled=index == 0):
        if save_current():
            st.session_state["kinderclip_segment_index"] = index - 1
            st.rerun()
    if save.button("Save segment"):
        if save_current():
            st.success("Segment saved.")
    if next_page.button("Next", disabled=index >= len(edl["segments"]) - 1):
        if save_current():
            st.session_state["kinderclip_segment_index"] = index + 1
            st.rerun()
    if all(item["review_status"] in {"reviewed", "overridden"} for item in edl["segments"]):
        st.success("All edit segments are reviewed. Continue to the export checklist when ready.")
        _next_step_button("Next: Export", "next_to_export", "Export")


@st.dialog("Privacy, Consent & Responsible-Use Agreement")
def _responsible_use_agreement_dialog(viewed_key: str) -> None:
    """Show the information users must read before the agreement can be selected."""
    st.markdown("""
KinderClip is a **local, semi-automated** video-editing tool. It makes technical camera
recommendations, but people remain responsible for the footage, decisions, and final video.

### 1. Children's privacy

Children's faces, names, voices, school uniforms, and activities can identify them. Treat all
raw and exported footage as sensitive. Limit access to authorised school staff and approved
families, store files securely, do not upload raw footage to cloud AI tools or public storage,
and delete files when the school's retention period ends.

### 2. Parental consent

Before using this project, confirm that the relevant parents or guardians gave permission for
recording and that the permission covers editing and KinderClip's AI-assisted technical
analysis. Confirm whether the final video may be shared privately only or publicly, and follow
that decision for every export.

### 3. Malaysia PDPA 2010 (Act 709)

Identifiable footage may contain personal data when it includes faces, names, voices, uniforms,
or other details that directly or indirectly identify a child. You are responsible for deciding
whether the [Personal Data Protection Act 2010 (Act 709)](https://www.pdp.gov.my/ppdpv1/en/akta/pdp-act-2010-en/)
and your school's policies apply to this use. Seek appropriate advice when needed.

### 4. Copyright and sharing

Use only music, school songs, performance audio, images, and other material that the school is
allowed to use. Keep records of licences for royalty-free material. Check that your permissions
also cover intended sharing on YouTube, Facebook, school websites, or private family channels.

### 5. AI and professional responsibility

KinderClip may recommend a wrong angle, miss an important moment, or give uneven attention to
children. Human review is compulsory. Do not describe the result as fully automatic: the tool is
semi-automatic and the final decisions are made by people.

### 6. Software licensing

KinderClip uses open-source components, including Streamlit, OpenCV, and FFmpeg. Check their
licences and any organisation rules before commercial or wider deployment.
""")
    st.divider()
    st.caption("After reading the agreement, use the button below to return to Export. You will still need to tick the agreement checkbox there.")
    if st.button("I have read the agreement", type="primary", key=f"{viewed_key}_complete"):
        st.session_state[viewed_key] = True
        st.rerun()


def export_page(preflight: str | None) -> None:
    st.header("Export")
    edl = _edl()
    workspace = _workspace()
    if not edl or not workspace:
        st.info("Review the edit before exporting.")
        return
    config = load_json(workspace / "analysis_config.json", BASE_CONFIG)
    approval = st.checkbox(
        "I reviewed the camera choices, cut points, text, and audio source.",
        value=bool(edl.get("human_approved", False)),
    )
    st.markdown("**Privacy, Consent & Responsible-Use Agreement**")
    workspace_key = re.sub(r"[^a-zA-Z0-9_]", "_", workspace.name)
    agreement_viewed_key = f"kinderclip_agreement_viewed_{workspace_key}"
    agreement_viewed = bool(st.session_state.get(agreement_viewed_key, False) or edl.get("responsible_use_accepted", False))
    if st.button("View agreement", key=f"view_agreement_{workspace_key}"):
        _responsible_use_agreement_dialog(agreement_viewed_key)
    agreement = st.checkbox(
        "I have read and agree to the Privacy, Consent & Responsible-Use Agreement.",
        value=bool(edl.get("responsible_use_accepted", False)),
        disabled=not agreement_viewed,
        help="Open and read the agreement before this checkbox becomes available.",
    )
    if not agreement_viewed:
        st.caption("Open the agreement, scroll to the end, and select “I have read the agreement” to unlock this checkbox.")
    if st.button("Save approval status"):
        edl["human_approved"] = approval
        set_responsible_use_acceptance(edl, agreement)
        validation = validate_edl(edl, config)
        _save_edl(edl)
        save_json_atomic(workspace / "review_record.json", review_record(edl, validation))
        st.rerun()
    validation = validate_edl(edl, config)
    st.subheader("Export checklist")
    if validation["valid"]:
        st.success(f"Ready to render. Final duration: {validation['final_duration']:.0f} seconds.")
    else:
        for issue in validation["issues"]:
            st.error(issue["message"])
    if preflight:
        st.warning(preflight)
    render_button = st.empty()
    render = render_button.button("Render final video", disabled=not validation["valid"] or preflight is not None)
    preview_shown = False
    if render:
        render_button.empty()
        render_button.button("Rendering final video…", key="render_in_progress", disabled=True)
        render_status = st.status("Rendering final video…", expanded=True)
        progress_bar = st.progress(0, text="Preparing render")

        def update_render_progress(message: str) -> None:
            percent = _render_progress_percent(message)
            progress_bar.progress(percent, text=message)
            render_status.update(label=f"Rendering final video — {percent}%", state="running", expanded=True)
            render_status.write(message)

        try:
            update_render_progress("Preparing render")
            result = render_edl(edl, workspace, config, update_render_progress)
            progress_bar.progress(100, text="Final video rendered")
            render_status.update(label="Rendering complete", state="complete", expanded=False)
            st.success(f"Rendering complete: {result.name}")
            st.subheader("Final video preview")
            with st.spinner("Loading final video preview…"):
                final_video = result.read_bytes()
            st.video(final_video)
            st.download_button("Download final video", data=final_video, file_name="KinderClip-final.mp4", mime="video/mp4")
            preview_shown = True
        except Exception as exc:
            render_status.update(label="Rendering failed", state="error", expanded=True)
            st.error(f"Rendering failed. See render_log.txt for details. {exc}")
    output = workspace / "final_video.mp4"
    if output.exists() and not preview_shown:
        st.subheader("Final video preview")
        with st.spinner("Loading final video preview…"):
            final_video = output.read_bytes()
        st.video(final_video)
        st.download_button("Download final video", data=final_video, file_name="KinderClip-final.mp4", mime="video/mp4")
        if st.button("Delete temporary files"):
            cleanup_temporary_files(workspace)
            st.success("Temporary render files were removed. The final video remains available.")


def main() -> None:
    st.set_page_config(page_title="KinderClip", page_icon="🎬", layout="wide")
    initialise_session(st.session_state)
    project = _project()
    workspace = _workspace()
    step = _sidebar(project, workspace)
    preflight = media_preflight_message()
    if step == "Home":
        home_page()
    elif step == "Project setup":
        project_setup(preflight)
    elif step == "Synchronisation":
        synchronisation(preflight)
    elif step == "Camera analysis":
        camera_analysis(preflight)
    elif step == "Review edit":
        review_edit()
    else:
        export_page(preflight)
    st.divider()
    st.caption("KinderClip processes footage locally. Use simulated footage unless written permission covers this project.")


if __name__ == "__main__":
    main()
