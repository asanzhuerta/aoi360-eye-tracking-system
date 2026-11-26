"""Build a persistent AOI sequence that Unity can stream at runtime.

The important contract here is identity stability: if the same detected object
survives across keyframes, it keeps the same AOI id and exact colour.

Outputs per keyframe: ``<frame>_aoi_map.png`` and ``<frame>_aoi_keyframe.json``.
Outputs per video: ``<video>_aoi_sequence_manifest.json`` and, optionally, a raw
RGB24 runtime pack (``<video>_aoi_sequence_rgb24.bin``) with every map
concatenated in keyframe order, so Unity can seek by offset without decoding PNGs.
"""

from __future__ import annotations

import argparse
import json
import math
from concurrent.futures import Executor, Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
from PIL import Image

from aoi360_pipeline.aoi_map_builder import (
    AoiBox,
    build_aoi_entries,
    build_distinct_hex_color,
    load_and_filter_detections,
    paint_aoi_map,
    read_frame_size,
    write_json,
)
from aoi360_pipeline.callbacks import (
    LogCallback,
    ProgressCallback,
    emit_log,
    emit_progress,
)
from aoi360_pipeline.geometry import (  # noqa: F401  (re-exported for compatibility)
    Box,
    bbox_area,
    bbox_area_similarity,
    bbox_center_distance,
    bbox_iou,
)

DEFAULT_SOURCE_RESOLUTION = (3840, 1920)
# PNG encoding and file creation release the GIL, so keyframe files are
# written by a small pool while the next keyframe is being painted.
_WRITER_THREADS = 4


@dataclass
class TrackState:
    """Mutable state for a lightweight per-object track across sparse keyframes."""

    track_id: int
    label: str
    prompt: str
    color: str
    name: str
    first_frame_index: int
    last_frame_index: int
    last_bbox: Box
    keyframe_count: int = 0

    def to_definition(self) -> dict[str, object]:
        return {
            "id": self.track_id,
            "name": self.name,
            "prompt": self.prompt,
            "category": self.label,
            "parentId": 0,
            "color": self.color,
            "firstFrameIndex": self.first_frame_index,
            "lastFrameIndex": self.last_frame_index,
            "keyframeCount": self.keyframe_count,
        }


@dataclass
class Keyframe:
    frame_index: int
    frame_file: str
    boxes: list[AoiBox] = field(default_factory=list)


@dataclass(frozen=True)
class TrackerSettings:
    max_frame_gap: int
    min_iou: float
    max_center_distance_px: float


def build_default_runtime_pack_path(manifest_path: str | Path | None, video_name: str) -> Path:
    """Keep the raw runtime pack next to the manifest by default."""
    if manifest_path is not None:
        manifest_path = Path(manifest_path)
        return manifest_path.with_name(manifest_path.stem.replace("_manifest", "_rgb24") + ".bin")

    return Path("data") / "processed" / "metadata" / f"{Path(video_name).stem}_aoi_sequence_rgb24.bin"


def group_keyframes(detections: pd.DataFrame) -> list[Keyframe]:
    """Group detections by frame, ordered by frame; boxes by confidence (desc) then index."""
    ordered = detections.sort_values(
        ["frame_index", "frame_file", "confidence", "detection_index"],
        ascending=[True, True, False, True],
        kind="stable",
    )
    keyframes: list[Keyframe] = []
    current: Keyframe | None = None
    for row in ordered.itertuples(index=False):
        frame_index = int(row.frame_index)
        frame_file = str(row.frame_file)
        if current is None or (current.frame_index, current.frame_file) != (frame_index, frame_file):
            current = Keyframe(frame_index, frame_file)
            keyframes.append(current)
        current.boxes.append(
            AoiBox(
                detection_index=int(row.detection_index),
                label=str(row.label),
                prompt=str(row.prompt),
                confidence=float(row.confidence),
                x_min=float(row.x_min),
                y_min=float(row.y_min),
                x_max=float(row.x_max),
                y_max=float(row.y_max),
            )
        )
    return keyframes


def infer_reference_frame_size(keyframes: list[Keyframe], frames_dir: str | Path) -> tuple[int, int]:
    """Use the first keyframe image as the source-of-truth export size."""
    if not keyframes:
        return DEFAULT_SOURCE_RESOLUTION

    first_frame_path = Path(frames_dir) / keyframes[0].frame_file
    if not first_frame_path.exists():
        return DEFAULT_SOURCE_RESOLUTION

    with Image.open(first_frame_path) as frame_image:
        return frame_image.size


def infer_keyframe_spacing(keyframes: list[Keyframe]) -> int:
    """Smallest positive gap between consecutive keyframe indices (0 if none)."""
    indices = [keyframe.frame_index for keyframe in keyframes]
    deltas = [current - previous for previous, current in zip(indices, indices[1:]) if current > previous]
    return min(deltas) if deltas else 0


def _match_track(
    box: AoiBox,
    frame_index: int,
    active_tracks: dict[int, TrackState],
    assigned_track_ids: set[int],
    settings: TrackerSettings,
) -> TrackState | None:
    """Best unassigned track with the same label, ranked by IoU, area, distance, gap."""
    best_track: TrackState | None = None
    best_score: tuple[float, float, float, float] | None = None

    for track in active_tracks.values():
        if track.track_id in assigned_track_ids or track.label != box.label:
            continue

        frame_gap = frame_index - track.last_frame_index
        if frame_gap < 0 or frame_gap > settings.max_frame_gap:
            continue

        iou = bbox_iou(track.last_bbox, box.bbox)
        center_distance = bbox_center_distance(track.last_bbox, box.bbox)
        area_similarity = bbox_area_similarity(track.last_bbox, box.bbox)

        if iou < settings.min_iou and center_distance > settings.max_center_distance_px:
            continue
        if area_similarity < 0.2 and center_distance > settings.max_center_distance_px * 0.5:
            continue

        score = (iou, area_similarity, -center_distance, -frame_gap)
        if best_score is None or score > best_score:
            best_track = track
            best_score = score

    return best_track


def associate_tracks(
    keyframes: list[Keyframe],
    max_track_frame_gap: int,
    min_track_iou: float,
    max_track_center_distance_ratio: float,
    reference_width: int,
    reference_height: int,
) -> tuple[list[Keyframe], list[TrackState]]:
    """Assign persistent AOI ids to boxes across keyframes.

    The tracker is deliberately simple: stable AOI identities are only needed
    for sparse keyframes, not high-frequency multi-object tracking. IoU plus
    centre distance gives a robust-enough identity handoff.

    Returns keyframes whose boxes carry ``aoi_id``/``name``/``color``, and the
    tracks in creation order.
    """
    settings = TrackerSettings(
        max_frame_gap=max_track_frame_gap,
        min_iou=min_track_iou,
        max_center_distance_px=math.hypot(float(reference_width), float(reference_height))
        * max_track_center_distance_ratio,
    )
    active_tracks: dict[int, TrackState] = {}
    all_tracks: list[TrackState] = []
    tracked_keyframes: list[Keyframe] = []

    for keyframe in keyframes:
        frame_index = keyframe.frame_index
        active_tracks = {
            track_id: track
            for track_id, track in active_tracks.items()
            if frame_index - track.last_frame_index <= settings.max_frame_gap
        }
        assigned_track_ids: set[int] = set()
        tracked = Keyframe(frame_index, keyframe.frame_file)

        for box in keyframe.boxes:
            track = _match_track(box, frame_index, active_tracks, assigned_track_ids, settings)
            if track is None:
                track_id = len(all_tracks) + 1
                track = TrackState(
                    track_id=track_id,
                    label=box.label,
                    prompt=box.prompt,
                    color=build_distinct_hex_color(track_id),
                    name=f"{box.label}_{track_id:02d}",
                    first_frame_index=frame_index,
                    last_frame_index=frame_index,
                    last_bbox=box.bbox,
                )
                active_tracks[track_id] = track
                all_tracks.append(track)

            assigned_track_ids.add(track.track_id)
            track.last_frame_index = frame_index
            track.last_bbox = box.bbox
            track.keyframe_count += 1

            tracked.boxes.append(
                AoiBox(
                    detection_index=box.detection_index,
                    label=box.label,
                    prompt=box.prompt,
                    confidence=box.confidence,
                    x_min=box.x_min,
                    y_min=box.y_min,
                    x_max=box.x_max,
                    y_max=box.y_max,
                    aoi_id=track.track_id,
                    name=track.name,
                    color=track.color,
                )
            )
        tracked_keyframes.append(tracked)

    return tracked_keyframes, all_tracks


def _select_keyframes(keyframes: list[Keyframe], max_frames: int | None, frame_step: int | None) -> list[Keyframe]:
    if max_frames is not None:
        keyframes = keyframes[: max(0, max_frames)]
    if frame_step is not None and frame_step > 0:
        keyframes = [keyframe for keyframe in keyframes if keyframe.frame_index % frame_step == 0]
    return keyframes


def _effective_track_gap(max_track_frame_gap: int, keyframe_spacing: int) -> int:
    # The tracker compares absolute video-frame indices, so with sparse keyframes
    # (for example every 30 frames) the gap must be at least that spacing or
    # identities can never survive to the next keyframe. Doubling it also
    # tolerates one missing keyframe without fragmenting the AOI id.
    if keyframe_spacing <= 0:
        return max_track_frame_gap
    return max(max_track_frame_gap, keyframe_spacing * 2)


class _RuntimePackWriter:
    """Appends RGB24 frames to the runtime pack and records their offsets."""

    def __init__(self, path: Path | None):
        self.path = path
        self.frame_byte_length: int | None = None
        self._stream = None
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            self._stream = path.open("wb")

    def append(self, rgb_bytes: bytes) -> tuple[int | None, int | None]:
        if self._stream is None:
            return None, None
        offset = self._stream.tell()
        self._stream.write(rgb_bytes)
        if self.frame_byte_length is None:
            self.frame_byte_length = len(rgb_bytes)
        return offset, len(rgb_bytes)

    def close(self) -> None:
        if self._stream is not None:
            self._stream.close()


def _reuse_existing_keyframe(
    keyframe: Keyframe,
    map_path: Path,
    keyframe_path: Path,
    pack: _RuntimePackWriter,
) -> tuple[dict[str, object], list[int]]:
    with Image.open(map_path) as existing_map:
        resolution = [existing_map.width, existing_map.height]
        # Even when reusing prior PNGs, keep the runtime pack in sync so Unity
        # can stay on the fast path.
        pack_offset, pack_length = (
            pack.append(existing_map.convert("RGB").tobytes()) if pack.path is not None else (None, None)
        )

    existing_document = json.loads(keyframe_path.read_text(encoding="utf-8"))
    entry = {
        "frameIndex": keyframe.frame_index,
        "frameFile": keyframe.frame_file,
        "mapFile": map_path.name,
        "keyframeFile": keyframe_path.name,
        "aoiCount": int(len(existing_document.get("aois", []))),
        "packOffset": pack_offset,
        "packLength": pack_length,
        "skipped": True,
    }
    return entry, resolution


def _write_keyframe(
    keyframe: Keyframe,
    map_path: Path,
    keyframe_path: Path,
    pack: _RuntimePackWriter,
    writer: Executor,
    video_name: str,
    source_size: tuple[int, int],
    map_size: tuple[int, int],
    box_padding: int,
    yaw_offset_degrees: float,
) -> tuple[list[Future], dict[str, object]]:
    """Paint one keyframe, append it to the pack, and queue its PNG and JSON writes."""
    width, height = map_size
    entries = build_aoi_entries(
        keyframe.boxes,
        width=width,
        height=height,
        box_padding=box_padding,
        source_width=source_size[0],
        source_height=source_size[1],
    )
    aoi_map = paint_aoi_map(entries, width, height, yaw_offset_degrees)
    pack_offset, pack_length = pack.append(aoi_map.tobytes())
    pending: list[Future] = [writer.submit(aoi_map.save, map_path)]
    pending.append(writer.submit(
        write_json,
        keyframe_path,
        {
            "video": video_name,
            "frameIndex": keyframe.frame_index,
            "frameFile": keyframe.frame_file,
            "mapFile": map_path.name,
            "aois": [
                {
                    "id": entry.id,
                    "bbox": entry.bbox,
                    "confidence": entry.confidence,
                    "sourceDetectionIndex": entry.source_detection_index,
                }
                for entry in entries
            ],
        },
    ))
    return pending, {
        "frameIndex": keyframe.frame_index,
        "frameFile": keyframe.frame_file,
        "mapFile": map_path.name,
        "keyframeFile": keyframe_path.name,
        "aoiCount": len(entries),
        "packOffset": pack_offset,
        "packLength": pack_length,
        "skipped": False,
    }


def build_aoi_sequence(
    detections_csv: str | Path,
    frames_dir: str | Path,
    output_maps_dir: str | Path,
    output_keyframes_dir: str | Path,
    video_name: str,
    fps: int = 30,
    include_labels: list[str] | None = None,
    min_confidence: float = 0.35,
    box_padding: int = 0,
    frame_nms_iou_threshold: float | None = None,
    normalize_labels_to_prompt_vocab: bool = False,
    max_track_frame_gap: int = 20,
    min_track_iou: float = 0.05,
    max_track_center_distance_ratio: float = 0.08,
    max_frames: int | None = None,
    manifest_path: str | Path | None = None,
    skip_existing: bool = False,
    frame_step: int | None = None,
    output_width: int | None = None,
    output_height: int | None = None,
    yaw_offset_degrees: float = 0.0,
    runtime_pack_path: str | Path | None = None,
    write_runtime_pack: bool = True,
    progress_callback: ProgressCallback | None = None,
    log_callback: LogCallback | None = None,
) -> dict[str, object]:
    """Export PNG keyframes, lightweight metadata, and an optional raw runtime pack."""
    frames_dir = Path(frames_dir)
    output_maps_dir = Path(output_maps_dir)
    output_keyframes_dir = Path(output_keyframes_dir)
    if box_padding < 0:
        raise ValueError("box_padding must be >= 0")
    if fps < 0:
        raise ValueError("fps must be >= 0")

    detections = load_and_filter_detections(
        detections_csv=detections_csv,
        include_labels=include_labels,
        min_confidence=min_confidence,
        frame_nms_iou_threshold=frame_nms_iou_threshold,
        normalize_labels_to_prompt_vocab=normalize_labels_to_prompt_vocab,
    )
    output_maps_dir.mkdir(parents=True, exist_ok=True)
    output_keyframes_dir.mkdir(parents=True, exist_ok=True)

    all_keyframes = group_keyframes(detections)
    keyframes = _select_keyframes(all_keyframes, max_frames, frame_step)
    if not keyframes:
        raise RuntimeError("No frame groups remain after applying the current sequence filters.")
    if not frames_dir.exists():
        raise FileNotFoundError(f"Frames directory not found: {frames_dir}")

    reference_width, reference_height = infer_reference_frame_size(keyframes, frames_dir)
    emit_log(
        log_callback,
        "[build_aoi_sequence] Building AOI sequence with "
        f"{len(keyframes)} keyframes out of {len(all_keyframes)} detected frame groups "
        f"at {reference_width}x{reference_height} source resolution.",
    )
    emit_log(
        log_callback,
        "[build_aoi_sequence] Runtime export settings: "
        f"{output_width or reference_width}x{output_height or reference_height}, "
        f"yaw offset {yaw_offset_degrees} degrees.",
    )
    if frame_step is not None and frame_step > 0:
        emit_log(
            log_callback,
            f"[build_aoi_sequence] Keeping only absolute video frames that match the step {frame_step}.",
        )

    keyframe_spacing = infer_keyframe_spacing(keyframes)
    effective_track_gap = _effective_track_gap(max_track_frame_gap, keyframe_spacing)
    if effective_track_gap != max_track_frame_gap:
        emit_log(
            log_callback,
            "[build_aoi_sequence] Increased the effective track gap from "
            f"{max_track_frame_gap} to {effective_track_gap} absolute video frames "
            f"to match the exported keyframe spacing ({keyframe_spacing}).",
        )

    tracked_keyframes, tracks = associate_tracks(
        keyframes=keyframes,
        max_track_frame_gap=effective_track_gap,
        min_track_iou=min_track_iou,
        max_track_center_distance_ratio=max_track_center_distance_ratio,
        reference_width=reference_width,
        reference_height=reference_height,
    )

    resolved_pack_path: Path | None = None
    if write_runtime_pack:
        resolved_pack_path = (
            Path(runtime_pack_path)
            if runtime_pack_path is not None
            else build_default_runtime_pack_path(manifest_path=manifest_path, video_name=video_name)
        )
        emit_log(log_callback, f"[build_aoi_sequence] Writing runtime AOI pack to '{resolved_pack_path}'.")

    manifest_entries: list[dict[str, object]] = []
    written_count = 0
    id_map_resolution: list[int] | None = None
    total = len(tracked_keyframes)
    emit_progress(progress_callback, 0, total, "Preparing AOI keyframes.")

    pack = _RuntimePackWriter(resolved_pack_path)
    pending_writes: list[Future] = []
    writer = ThreadPoolExecutor(max_workers=_WRITER_THREADS)
    try:
        for position, keyframe in enumerate(tracked_keyframes, start=1):
            frame_stem = Path(keyframe.frame_file).stem
            map_path = output_maps_dir / f"{frame_stem}_aoi_map.png"
            keyframe_path = output_keyframes_dir / f"{frame_stem}_aoi_keyframe.json"

            if skip_existing and map_path.exists() and keyframe_path.exists():
                entry, resolution = _reuse_existing_keyframe(keyframe, map_path, keyframe_path, pack)
                id_map_resolution = id_map_resolution or resolution
                manifest_entries.append(entry)
                emit_progress(progress_callback, position, total, f"Skipped existing AOI outputs for {keyframe.frame_file}.")
                continue

            # Frames of one video share a size; reading it per keyframe also
            # checks that the frame the detections refer to exists.
            source_size = read_frame_size(frames_dir, keyframe.frame_file)
            map_size = (int(output_width or source_size[0]), int(output_height or source_size[1]))
            writes, entry = _write_keyframe(
                keyframe,
                map_path,
                keyframe_path,
                pack,
                writer,
                video_name=video_name,
                source_size=source_size,
                map_size=map_size,
                box_padding=box_padding,
                yaw_offset_degrees=yaw_offset_degrees,
            )
            pending_writes.extend(writes)
            id_map_resolution = id_map_resolution or list(map_size)
            manifest_entries.append(entry)
            written_count += 1
            emit_progress(
                progress_callback,
                position,
                total,
                f"Wrote AOI keyframe {keyframe.frame_file} with {entry['aoiCount']} AOIs.",
            )
    finally:
        pack.close()
        writer.shutdown(wait=True)
    for write in pending_writes:
        write.result()  # re-raise any write error

    manifest: dict[str, object] = {
        "video": video_name,
        "fps": int(fps),
        "sourceFrameResolution": [reference_width, reference_height],
        "idMapResolution": id_map_resolution or [],
        "frameStep": int(frame_step) if frame_step is not None else None,
        "mapsDirectory": str(output_maps_dir),
        "keyframesDirectory": str(output_keyframes_dir),
        "aois": [track.to_definition() for track in tracks],
        "frameCount": len(manifest_entries),
        "writtenCount": written_count,
        "bakedYawOffsetDegrees": float(yaw_offset_degrees),
        "frames": manifest_entries,
    }

    if resolved_pack_path is not None and id_map_resolution:
        frame_width, frame_height = id_map_resolution
        manifest["runtimePack"] = {
            "file": resolved_pack_path.name,
            "encoding": "rgb24",
            "frameWidth": int(frame_width),
            "frameHeight": int(frame_height),
            "bytesPerPixel": 3,
            "frameByteLength": int(pack.frame_byte_length or frame_width * frame_height * 3),
        }

    if manifest_path is not None:
        write_json(Path(manifest_path), manifest)

    emit_log(
        log_callback,
        "[build_aoi_sequence] Completed sequence export with "
        f"{len(tracks)} persistent AOIs across {len(manifest_entries)} keyframes.",
    )
    return manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build Unity-compatible AOI maps and metadata JSON files for every detected frame."
    )
    parser.add_argument(
        "--detections-csv",
        default="data/interim/detections/video_360_grounding_dino_boxes.csv",
        help="Detections CSV produced by the open-vocabulary detector step.",
    )
    parser.add_argument(
        "--frames-dir",
        default="data/frames/video_360",
        help="Directory that contains the extracted frame images.",
    )
    parser.add_argument(
        "--output-maps-dir",
        default="data/processed/id_maps/video_360",
        help="Directory where one AOI map PNG per frame will be written.",
    )
    parser.add_argument(
        "--output-metadata-dir",
        default="data/processed/metadata/video_360",
        help="Directory where one lightweight AOI keyframe JSON per frame will be written.",
    )
    parser.add_argument(
        "--manifest-path",
        default="data/processed/metadata/video_360_aoi_sequence_manifest.json",
        help="JSON manifest summarizing all per-frame AOI exports.",
    )
    parser.add_argument(
        "--video-name",
        default="video_360.mp4",
        help="Video filename to write into each metadata JSON and the sequence manifest.",
    )
    parser.add_argument("--fps", type=int, default=30, help="FPS metadata to write into the AOI metadata JSON files.")
    parser.add_argument(
        "--include-label",
        action="append",
        dest="include_labels",
        help="Optional label filter. Repeat to keep multiple labels.",
    )
    parser.add_argument("--min-confidence", type=float, default=0.35)
    parser.add_argument("--box-padding", type=int, default=0)
    parser.add_argument(
        "--frame-nms-iou-threshold",
        type=float,
        default=None,
        help="Optional per-frame, per-label NMS IoU threshold to suppress duplicate detections before AOI tracking.",
    )
    parser.add_argument(
        "--normalize-labels-to-prompt-vocab",
        action="store_true",
        help="Canonicalize detector labels to the closest label phrase present in the original prompt.",
    )
    parser.add_argument(
        "--max-track-frame-gap",
        type=int,
        default=20,
        help="Maximum absolute video-frame gap allowed when linking two detections into the same AOI track.",
    )
    parser.add_argument("--min-track-iou", type=float, default=0.05)
    parser.add_argument("--max-track-center-distance-ratio", type=float, default=0.08)
    parser.add_argument("--max-frames", type=int, default=None)
    parser.add_argument("--skip-existing", action="store_true")
    parser.add_argument(
        "--frame-step",
        type=int,
        default=None,
        help="Optional absolute video-frame step for exported AOI keyframes, e.g. 30 keeps only frame 0,30,60...",
    )
    parser.add_argument("--output-width", type=int, default=None, help="Optional output AOI map width.")
    parser.add_argument("--output-height", type=int, default=None, help="Optional output AOI map height.")
    parser.add_argument(
        "--yaw-offset-degrees",
        type=float,
        default=0.0,
        help="Bake a horizontal equirectangular yaw offset into every exported AOI map.",
    )
    parser.add_argument(
        "--runtime-pack-path",
        default=None,
        help="Optional binary runtime-pack output path. Defaults next to the manifest.",
    )
    parser.add_argument(
        "--disable-runtime-pack",
        action="store_true",
        help="Disable the binary RGB24 runtime pack export and keep only PNG keyframes.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    manifest = build_aoi_sequence(
        detections_csv=args.detections_csv,
        frames_dir=args.frames_dir,
        output_maps_dir=args.output_maps_dir,
        output_keyframes_dir=args.output_metadata_dir,
        video_name=args.video_name,
        fps=args.fps,
        include_labels=args.include_labels,
        min_confidence=args.min_confidence,
        box_padding=args.box_padding,
        frame_nms_iou_threshold=args.frame_nms_iou_threshold,
        normalize_labels_to_prompt_vocab=args.normalize_labels_to_prompt_vocab,
        max_track_frame_gap=args.max_track_frame_gap,
        min_track_iou=args.min_track_iou,
        max_track_center_distance_ratio=args.max_track_center_distance_ratio,
        max_frames=args.max_frames,
        manifest_path=args.manifest_path,
        skip_existing=args.skip_existing,
        frame_step=args.frame_step,
        output_width=args.output_width,
        output_height=args.output_height,
        yaw_offset_degrees=args.yaw_offset_degrees,
        runtime_pack_path=args.runtime_pack_path,
        write_runtime_pack=not args.disable_runtime_pack,
    )

    print(f"Frames in manifest: {manifest['frameCount']}")
    print(f"Frames written now: {manifest['writtenCount']}")
    print(f"Maps directory: {manifest['mapsDirectory']}")
    print(f"Keyframes directory: {manifest['keyframesDirectory']}")


if __name__ == "__main__":
    main()
