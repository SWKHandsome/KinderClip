"""Staged FFmpeg rendering from an approved KinderClip EDL."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any, Callable

from .sync_manager import main_timeline_source_time


FONT_CANDIDATES = (
    Path("C:/Windows/Fonts/arial.ttf"),
    Path("C:/Windows/Fonts/segoeui.ttf"),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    Path("/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf"),
    Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
)


def ffmpeg_available(ffmpeg_bin: str = "ffmpeg") -> bool:
    return shutil.which(ffmpeg_bin) is not None


def escape_drawtext(value: str) -> str:
    """Escape text embedded in an FFmpeg drawtext filter value."""
    return value.replace("\\", "\\\\").replace("'", "\\'").replace(":", "\\:").replace("%", "\\%").replace("\n", "\\n")


def resolve_font_file(config: dict[str, Any]) -> Path:
    """Find an explicit, readable font so FFmpeg never needs Fontconfig discovery."""
    configured = str(config.get("font_file", "")).strip()
    if configured:
        chosen = Path(configured)
        if chosen.is_file():
            return chosen
        raise RuntimeError(f"Configured KinderClip font was not found: {chosen}")
    for candidate in FONT_CANDIDATES:
        if candidate.is_file():
            return candidate
    raise RuntimeError(
        "KinderClip could not find a usable font. Set font_file in analysis_config.json to a .ttf font, "
        "for example C:\\Windows\\Fonts\\arial.ttf."
    )


def escape_font_file(value: str | Path) -> str:
    """Format a font path for FFmpeg's colon-separated filter syntax."""
    return str(value).replace("\\", "/").replace("'", "\\'").replace(":", "\\:")


def _run(command: list[str], log_path: Path, runner: Callable[..., Any] = subprocess.run) -> None:
    result = runner(command, capture_output=True, text=True, check=False)
    with log_path.open("a", encoding="utf-8") as log:
        log.write("$ " + " ".join(command) + "\n")
        log.write(result.stdout or "")
        log.write(result.stderr or "")
        log.write("\n")
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "FFmpeg rendering failed")


def title_card_command(
    text: str, output: Path, config: dict[str, Any], duration: float, font_file: str | Path | None = None
) -> list[str]:
    font = escape_font_file(font_file or resolve_font_file(config))
    drawtext = (
        f"drawtext=fontfile='{font}':text='{escape_drawtext(text)}':fontcolor=white:fontsize=48:"
        "x=(w-text_w)/2:y=(h-text_h)/2"
    )
    return [
        "ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c=#102A43:s={config['output_width']}x{config['output_height']}:r={config['output_fps']}",
        "-t", f"{duration:.3f}", "-vf", drawtext, "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(output),
    ]


def segment_command(
    source: Path, source_start: float, duration: float, output: Path, config: dict[str, Any], lower_third: str | None = None,
    font_file: str | Path | None = None,
) -> list[str]:
    filters = [f"scale={config['output_width']}:{config['output_height']}:force_original_aspect_ratio=decrease", f"pad={config['output_width']}:{config['output_height']}:(ow-iw)/2:(oh-ih)/2", f"fps={config['output_fps']}", "setsar=1"]
    if lower_third:
        font = escape_font_file(font_file or resolve_font_file(config))
        filters.append(
            f"drawtext=fontfile='{font}':text='{escape_drawtext(lower_third)}':fontcolor=white:fontsize=28:"
            "x=40:y=h-70:box=1:boxcolor=black@0.55:boxborderw=12"
        )
    return [
        "ffmpeg", "-y", "-ss", f"{source_start:.3f}", "-t", f"{duration:.3f}", "-i", str(source),
        "-vf", ",".join(filters), "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(output),
    ]


def join_command(left: Path, right: Path, output: Path, transition: str, left_duration: float, config: dict[str, Any]) -> list[str]:
    if transition == "Cut":
        filter_graph = "[0:v][1:v]concat=n=2:v=1:a=0[v]"
    else:
        kind = "fade" if transition == "Crossfade" else "fadeblack"
        offset = max(0.0, left_duration - config["transition_seconds"])
        filter_graph = f"[0:v][1:v]xfade=transition={kind}:duration={config['transition_seconds']:.3f}:offset={offset:.3f}[v]"
    return [
        "ffmpeg", "-y", "-i", str(left), "-i", str(right), "-filter_complex", filter_graph,
        "-map", "[v]", "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(output),
    ]


def audio_mux_command(
    visual: Path, master_source: Path, clap_timestamp: float, ceremony_duration: float, output: Path, config: dict[str, Any], silent_export: bool,
) -> list[str]:
    if silent_export:
        return ["ffmpeg", "-y", "-i", str(visual), "-c:v", "copy", "-an", str(output)]
    title = config["title_seconds"]
    credits = config["credits_seconds"]
    fade = min(config["audio_fade_seconds"], ceremony_duration / 2)
    graph = (
        f"[1:a]atrim=duration={ceremony_duration:.3f},asetpts=PTS-STARTPTS,"
        f"afade=t=in:st=0:d={fade:.3f},afade=t=out:st={max(0.0, ceremony_duration - fade):.3f}:d={fade:.3f}[ceremony];"
        f"anullsrc=r=48000:cl=stereo,atrim=duration={title:.3f}[intro];"
        f"anullsrc=r=48000:cl=stereo,atrim=duration={credits:.3f}[outro];"
        "[intro][ceremony][outro]concat=n=3:v=0:a=1[a]"
    )
    return [
        "ffmpeg", "-y", "-i", str(visual), "-ss", f"{clap_timestamp:.3f}", "-i", str(master_source),
        "-filter_complex", graph, "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(output),
    ]


def render_edl(
    edl: dict[str, Any], workspace: str | Path, config: dict[str, Any], progress: Callable[[str], None] | None = None,
    ffmpeg_bin: str = "ffmpeg", runner: Callable[..., Any] = subprocess.run,
) -> Path:
    """Render visual stages then combine a single delayed master audio stream."""
    if not ffmpeg_available(ffmpeg_bin):
        raise RuntimeError("FFmpeg is not available on PATH.")
    root = Path(workspace)
    temporary = root / "render_tmp"
    temporary.mkdir(parents=True, exist_ok=True)
    log_path = root / "render_log.txt"
    log_path.write_text("KinderClip render log\n", encoding="utf-8")
    sources = {source["id"]: source for source in edl["sources"]}
    project = edl["project"]
    main_source = sources.get(project.get("main_camera_id", ""))
    main_clap = float(main_source.get("clap_timestamp", 0.0)) if main_source else 0.0
    font_file = resolve_font_file(config)

    def execute(command: list[str]) -> None:
        command[0] = ffmpeg_bin
        _run(command, log_path, runner)

    title = temporary / "opening-title.mp4"
    credits = temporary / "closing-credits.mp4"
    if progress:
        progress("Creating opening title")
    execute(title_card_command(project["opening_title"], title, config, config["title_seconds"], font_file))
    if progress:
        progress("Rendering ceremony segments")
    rendered: list[tuple[Path, float]] = []
    segments = edl["segments"]
    for index, segment in enumerate(segments):
        incoming = index > 0 and segment.get("transition") in {"Crossfade", "Fade"}
        outgoing = index + 1 < len(segments) and segments[index + 1].get("transition") in {"Crossfade", "Fade"}
        overlap = config["transition_seconds"] / 2
        shared_start = segment["start"] - (overlap if incoming else 0.0)
        shared_end = segment["end"] + (overlap if outgoing else 0.0)
        source = sources[segment["selected_camera"]]
        clap = float(source["clap_timestamp"])
        output = temporary / f"segment-{index + 1:03d}.mp4"
        execute(segment_command(
            Path(source["path"]), main_timeline_source_time(shared_start, main_clap, clap), shared_end - shared_start, output, config,
            project["lower_third"] if index == 0 else None, font_file,
        ))
        rendered.append((output, shared_end - shared_start))
        if progress:
            progress(f"Rendered segment {index + 1} of {len(segments)}")
    if progress:
        progress("Creating closing credits")
    execute(title_card_command(project["closing_credit"], credits, config, config["credits_seconds"], font_file))

    visual, visual_duration = title, config["title_seconds"]
    for index, (segment_file, segment_duration) in enumerate(rendered):
        if progress:
            progress(f"Joining visual stage {index + 1} of {len(rendered) + 1}")
        joined = temporary / f"joined-{index:03d}.mp4"
        transition = "Cut" if index == 0 else segments[index].get("transition", "Cut")
        execute(join_command(visual, segment_file, joined, transition, visual_duration, config))
        visual = joined
        visual_duration = visual_duration + segment_duration - (config["transition_seconds"] if transition != "Cut" else 0.0)
    final_visual = temporary / "visual-with-ceremony.mp4"
    if progress:
        progress(f"Joining visual stage {len(rendered) + 1} of {len(rendered) + 1}")
    execute(join_command(visual, credits, final_visual, "Cut", visual_duration, config))
    final_output = root / "final_video.mp4"
    master = sources.get(project.get("master_audio_camera", ""))
    if not project.get("silent_export", False) and master is None:
        raise RuntimeError("Selected master audio source is missing from the EDL.")
    if progress:
        progress("Adding continuous master audio")
    execute(audio_mux_command(
        final_visual, Path(master["path"]) if master else Path(""),
        main_timeline_source_time(0.0, main_clap, float(master["clap_timestamp"])) if master else 0.0,
        float(project["ceremony_duration"]), final_output, config, bool(project.get("silent_export", False)),
    ))
    if not final_output.exists() or final_output.stat().st_size == 0:
        raise RuntimeError("FFmpeg completed without creating a final video.")
    if progress:
        progress("Final video completed")
    return final_output


def cleanup_temporary_files(workspace: str | Path) -> None:
    temporary = Path(workspace) / "render_tmp"
    if temporary.exists():
        shutil.rmtree(temporary)
