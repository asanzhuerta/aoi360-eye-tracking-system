from __future__ import annotations
"""Orchestrate the full offline AOI rebuild pipeline from one entry point.

This module is intentionally thin: it coordinates the extraction, detection,
and AOI export stages while keeping each stage in its own focused module.
"""

import argparse
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from aoi360_pipeline.aoi_map_sequence_builder import build_aoi_sequence
from aoi360_pipeline.frame_extraction import extract_frames
from aoi360_pipeline.grounding_dino import detect_frames

ProgressCallback = Callable[[str, int, int, str], None]
LogCallback = Callable[[str], None]


@dataclass(frozen=True)
class RuntimeBuildPaths:
    """Stable output layout shared by the CLI, GUI, and Unity sync tools."""

    frames_dir: Path
    detections_csv: Path
    output_maps_dir: Path
    output_metadata_dir: Path
    manifest_path: Path
    runtime_pack_path: Path


def find_repo_root(start: str | Path | None = None) -> Path:
    """Walk up from the current path until the project root shape is found."""

    current = Path(start or Path.cwd()).resolve()
    for candidate in [current, *current.parents]:
        if (candidate / "python").exists() and (candidate / "unity").exists():
            return candidate
    return current


def derive_runtime_build_paths(
    video_path: str | Path,
    repo_root: str | Path | None = None,
    frames_dir: str | Path | None = None,
    detections_csv: str | Path | None = None,
    output_maps_dir: str | Path | None = None,
    output_metadata_dir: str | Path | None = None,
    manifest_path: str | Path | None = None,
) -> RuntimeBuildPaths:
    # Keep derived paths in one place so every entry point writes the exact same
    # folder structure and Unity can rely on a predictable handoff contract.
    video_path = Path(video_path)
    root = find_repo_root(repo_root)
    video_stem = video_path.stem

    resolved_frames_dir = Path(frames_dir) if frames_dir is not None else root / "data" / "frames" / video_stem
    resolved_detections_csv = (
        Path(detections_csv)
        if detections_csv is not None
        else root / "data" / "interim" / "detections" / f"{video_stem}_grounding_dino_boxes.csv"
    )
    resolved_output_maps_dir = (
        Path(output_maps_dir)
        if output_maps_dir is not None
        else root / "data" / "processed" / "id_maps" / video_stem
    )
    resolved_output_metadata_dir = (
        Path(output_metadata_dir)
        if output_metadata_dir is not None
        else root / "data" / "processed" / "metadata" / video_stem
    )
    resolved_manifest_path = (
        Path(manifest_path)
        if manifest_path is not None
        else root / "data" / "processed" / "metadata" / f"{video_stem}_aoi_sequence_manifest.json"
    )
    resolved_runtime_pack_path = resolved_manifest_path.with_name(
        resolved_manifest_path.stem.replace("_manifest", "_rgb24") + ".bin"
    )

    return RuntimeBuildPaths(
        frames_dir=resolved_frames_dir,
        detections_csv=resolved_detections_csv,
        output_maps_dir=resolved_output_maps_dir,
        output_metadata_dir=resolved_output_metadata_dir,
        manifest_path=resolved_manifest_path,
        runtime_pack_path=resolved_runtime_pack_path,
    )


def _emit_log(log_callback: LogCallback | None, message: str) -> None:
    if log_callback is not None:
        log_callback(message)
    else:
        print(message)


def _emit_progress(
    progress_callback: ProgressCallback | None,
    stage: str,
    current: int,
    total: int,
    message: str,
) -> None:
    if progress_callback is not None:
        progress_callback(stage, current, total, message)


def clean_paths(paths: list[Path]) -> None:
    """Delete generated artifacts without touching source assets."""

    for path in paths:
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
        elif path.exists():
            path.unlink()


def rebuild_runtime_assets(
    video_path: str | Path,
    text_prompt: str,
    frames_dir: str | Path | None = None,
    detections_csv: str | Path | None = None,
    output_maps_dir: str | Path | None = None,
    output_metadata_dir: str | Path | None = None,
    manifest_path: str | Path | None = None,
    fps: int = 30,
    every_n_frames: int = 10,
    frame_step: int = 30,
    output_width: int = 1024,
    output_height: int = 512,
    min_confidence: float = 0.35,
    box_threshold: float = 0.35,
    text_threshold: float = 0.25,
    include_labels: list[str] | None = None,
    clean: bool = False,
    yaw_offset_degrees: float = 270.0,
    progress_callback: ProgressCallback | None = None,
    log_callback: LogCallback | None = None,
) -> dict[str, object]:
    # This function is the application service for the offline pipeline. It
    # delegates the heavy lifting to the stage-specific modules and keeps the
    # outer workflow easy to trigger from scripts, the GUI, or future tooling.
    video_path = Path(video_path)
    resolved_paths = derive_runtime_build_paths(
        video_path=video_path,
        frames_dir=frames_dir,
        detections_csv=detections_csv,
        output_maps_dir=output_maps_dir,
        output_metadata_dir=output_metadata_dir,
        manifest_path=manifest_path,
    )
    frames_dir = resolved_paths.frames_dir
    detections_csv = resolved_paths.detections_csv
    output_maps_dir = resolved_paths.output_maps_dir
    output_metadata_dir = resolved_paths.output_metadata_dir
    manifest_path = resolved_paths.manifest_path
    runtime_pack_path = resolved_paths.runtime_pack_path

    if clean:
        _emit_log(log_callback, "[rebuild_runtime_assets] Cleaning previously generated assets.")
        clean_paths([
            frames_dir,
            detections_csv,
            output_maps_dir,
            output_metadata_dir,
            manifest_path,
            runtime_pack_path,
        ])

    _emit_log(log_callback, f"[rebuild_runtime_assets] Video selected: {video_path}")
    _emit_log(log_callback, f"[rebuild_runtime_assets] Frames directory: {frames_dir}")
    _emit_log(log_callback, f"[rebuild_runtime_assets] Detections CSV: {detections_csv}")
    _emit_log(log_callback, f"[rebuild_runtime_assets] AOI maps directory: {output_maps_dir}")
    _emit_log(log_callback, f"[rebuild_runtime_assets] AOI metadata directory: {output_metadata_dir}")
    _emit_log(log_callback, f"[rebuild_runtime_assets] Manifest path: {manifest_path}")
    _emit_log(log_callback, f"[rebuild_runtime_assets] Runtime pack path: {runtime_pack_path}")

    _emit_progress(progress_callback, "extract", 0, 1, "Starting frame extraction.")
    extraction_summary = extract_frames(
        video_path=video_path,
        output_dir=frames_dir,
        every_n_frames=every_n_frames,
        progress_callback=lambda current, total, message: _emit_progress(
            progress_callback, "extract", current, total, message
        ),
        log_callback=log_callback,
    )

    _emit_progress(progress_callback, "detect", 0, 1, "Starting Grounding DINO detections.")
    detections = detect_frames(
        frames_dir=frames_dir,
        output_csv=detections_csv,
        text_prompt=text_prompt,
        box_threshold=box_threshold,
        text_threshold=text_threshold,
        progress_callback=lambda current, total, message: _emit_progress(
            progress_callback, "detect", current, total, message
        ),
        log_callback=log_callback,
    )

    _emit_progress(progress_callback, "build", 0, 1, "Starting AOI sequence export.")
    manifest = build_aoi_sequence(
        detections_csv=detections_csv,
        frames_dir=frames_dir,
        output_maps_dir=output_maps_dir,
        output_keyframes_dir=output_metadata_dir,
        manifest_path=manifest_path,
        video_name=video_path.name,
        fps=fps,
        include_labels=include_labels,
        min_confidence=min_confidence,
        frame_step=frame_step,
        output_width=output_width,
        output_height=output_height,
        yaw_offset_degrees=yaw_offset_degrees,
        runtime_pack_path=runtime_pack_path,
        progress_callback=lambda current, total, message: _emit_progress(
            progress_callback, "build", current, total, message
        ),
        log_callback=log_callback,
    )

    _emit_progress(progress_callback, "done", 1, 1, "Runtime assets rebuilt successfully.")
    _emit_log(log_callback, "[rebuild_runtime_assets] Pipeline completed successfully.")

    return {
        "video_path": str(video_path),
        "frames_dir": str(frames_dir),
        "detections_csv": str(detections_csv),
        "maps_dir": str(output_maps_dir),
        "metadata_dir": str(output_metadata_dir),
        "manifest_path": str(manifest_path),
        "runtime_pack_path": str(runtime_pack_path),
        "frames_read": extraction_summary["frames_read"],
        "frames_saved": extraction_summary["frames_saved"],
        "detections_count": int(len(detections)),
        "keyframe_count": int(manifest["frameCount"]),
        "written_count": int(manifest["writtenCount"]),
        "source_frame_resolution": manifest.get("sourceFrameResolution", []),
        "id_map_resolution": manifest.get("idMapResolution", []),
        "baked_yaw_offset_degrees": float(manifest.get("bakedYawOffsetDegrees", yaw_offset_degrees)),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Rebuild the runtime-ready AOI assets for a 360 video from scratch."
    )
    parser.add_argument("--video-path", default="data/input_videos/video_360.mp4")
    parser.add_argument("--frames-dir", default=None, help="Optional override. Defaults to data/frames/<video-stem>.")
    parser.add_argument(
        "--detections-csv",
        default=None,
        help="Optional override. Defaults to data/interim/detections/<video-stem>_grounding_dino_boxes.csv.",
    )
    parser.add_argument("--output-maps-dir", default=None, help="Optional override. Defaults to data/processed/id_maps/<video-stem>.")
    parser.add_argument(
        "--output-metadata-dir",
        default=None,
        help="Optional override. Defaults to data/processed/metadata/<video-stem>.",
    )
    parser.add_argument(
        "--manifest-path",
        default=None,
        help="Optional override. Defaults to data/processed/metadata/<video-stem>_aoi_sequence_manifest.json.",
    )
    parser.add_argument("--text-prompt", default="person. face. bottle. screen. product.")
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--every-n-frames", type=int, default=10)
    parser.add_argument(
        "--frame-step",
        type=int,
        default=30,
        help="Absolute video-frame step for exported AOI keyframes. Default 30 keeps one AOI map per second at 30 fps.",
    )
    parser.add_argument(
        "--output-width",
        type=int,
        default=1024,
        help="Runtime-oriented AOI map width. Defaults to 1024 for smoother standalone VR playback.",
    )
    parser.add_argument(
        "--output-height",
        type=int,
        default=512,
        help="Runtime-oriented AOI map height. Defaults to 512 for smoother standalone VR playback.",
    )
    parser.add_argument(
        "--yaw-offset-degrees",
        type=float,
        default=270.0,
        help="Bake this horizontal equirectangular yaw offset into every exported AOI map. Defaults to 270 degrees for the current Unity 360 setup.",
    )
    parser.add_argument("--min-confidence", type=float, default=0.35)
    parser.add_argument("--box-threshold", type=float, default=0.35)
    parser.add_argument("--text-threshold", type=float, default=0.25)
    parser.add_argument("--include-label", action="append", dest="include_labels")
    parser.add_argument("--clean", action="store_true")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    summary = rebuild_runtime_assets(
        video_path=args.video_path,
        frames_dir=args.frames_dir,
        detections_csv=args.detections_csv,
        output_maps_dir=args.output_maps_dir,
        output_metadata_dir=args.output_metadata_dir,
        manifest_path=args.manifest_path,
        text_prompt=args.text_prompt,
        fps=args.fps,
        every_n_frames=args.every_n_frames,
        frame_step=args.frame_step,
        output_width=args.output_width,
        output_height=args.output_height,
        min_confidence=args.min_confidence,
        box_threshold=args.box_threshold,
        text_threshold=args.text_threshold,
        include_labels=args.include_labels,
        clean=args.clean,
        yaw_offset_degrees=args.yaw_offset_degrees,
    )

    print(f"Video: {summary['video_path']}")
    print(f"Frames read/saved: {summary['frames_read']} / {summary['frames_saved']}")
    print(f"Detections: {summary['detections_count']}")
    print(f"AOI keyframes written: {summary['written_count']} / {summary['keyframe_count']}")
    print(f"Source frame resolution: {summary['source_frame_resolution']}")
    print(f"Runtime AOI map resolution: {summary['id_map_resolution']}")
    print(f"Baked yaw offset: {summary['baked_yaw_offset_degrees']}")
    print(f"Frames dir: {summary['frames_dir']}")
    print(f"Detections CSV: {summary['detections_csv']}")
    print(f"AOI maps dir: {summary['maps_dir']}")
    print(f"AOI metadata dir: {summary['metadata_dir']}")
    print(f"Manifest: {summary['manifest_path']}")
    print(f"Runtime pack: {summary['runtime_pack_path']}")


if __name__ == "__main__":
    main()
