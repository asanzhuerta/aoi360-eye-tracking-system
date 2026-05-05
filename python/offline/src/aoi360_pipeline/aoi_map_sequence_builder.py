from __future__ import annotations
"""Build a persistent AOI sequence that Unity can stream at runtime.

The important contract here is identity stability: if the same detected object
survives across keyframes, it keeps the same AOI id and exact color.
"""

import argparse
import math
import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from aoi360_pipeline.aoi_map_builder import (
    build_distinct_hex_color,
    load_and_filter_detections,
    render_aoi_map_from_detections,
)


ProgressCallback = Callable[[int, int, str], None]
LogCallback = Callable[[str], None]


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
    last_bbox: tuple[float, float, float, float]
    keyframe_count: int = 0


def build_default_runtime_pack_path(manifest_path: str | Path | None, video_name: str) -> Path:
    """Keep the raw runtime pack next to the manifest by default."""

    if manifest_path is not None:
        manifest_path = Path(manifest_path)
        return manifest_path.with_name(
            manifest_path.stem.replace("_manifest", "_rgb24") + ".bin"
        )

    return Path("data") / "processed" / "metadata" / f"{Path(video_name).stem}_aoi_sequence_rgb24.bin"


def _emit_log(log_callback: LogCallback | None, message: str) -> None:
    if log_callback is not None:
        log_callback(message)
    else:
        print(message)


def _emit_progress(
    progress_callback: ProgressCallback | None,
    current: int,
    total: int,
    message: str,
) -> None:
    if progress_callback is not None:
        progress_callback(current, total, message)


def infer_reference_frame_size(frame_groups, frames_dir: str | Path) -> tuple[int, int]:
    """Use the first available frame as the source-of-truth export size."""

    if not frame_groups:
        return 3840, 1920

    first_frame_file = str(frame_groups[0][0][1])
    first_frame_path = Path(frames_dir) / first_frame_file
    if not first_frame_path.exists():
        return 3840, 1920

    with Image.open(first_frame_path) as frame_image:
        return frame_image.size


def bbox_iou(box_a: tuple[float, float, float, float], box_b: tuple[float, float, float, float]) -> float:
    ax_min, ay_min, ax_max, ay_max = box_a
    bx_min, by_min, bx_max, by_max = box_b

    inter_x_min = max(ax_min, bx_min)
    inter_y_min = max(ay_min, by_min)
    inter_x_max = min(ax_max, bx_max)
    inter_y_max = min(ay_max, by_max)

    inter_width = max(0.0, inter_x_max - inter_x_min)
    inter_height = max(0.0, inter_y_max - inter_y_min)
    intersection = inter_width * inter_height

    area_a = max(0.0, ax_max - ax_min) * max(0.0, ay_max - ay_min)
    area_b = max(0.0, bx_max - bx_min) * max(0.0, by_max - by_min)
    union = area_a + area_b - intersection

    if union <= 0.0:
        return 0.0

    return intersection / union


def bbox_center_distance(box_a: tuple[float, float, float, float], box_b: tuple[float, float, float, float]) -> float:
    ax_min, ay_min, ax_max, ay_max = box_a
    bx_min, by_min, bx_max, by_max = box_b

    center_a_x = (ax_min + ax_max) * 0.5
    center_a_y = (ay_min + ay_max) * 0.5
    center_b_x = (bx_min + bx_max) * 0.5
    center_b_y = (by_min + by_max) * 0.5

    return math.hypot(center_a_x - center_b_x, center_a_y - center_b_y)


def bbox_area(box: tuple[float, float, float, float]) -> float:
    x_min, y_min, x_max, y_max = box
    return max(0.0, x_max - x_min) * max(0.0, y_max - y_min)


def bbox_area_similarity(box_a: tuple[float, float, float, float], box_b: tuple[float, float, float, float]) -> float:
    area_a = bbox_area(box_a)
    area_b = bbox_area(box_b)
    if area_a <= 0.0 or area_b <= 0.0:
        return 0.0

    return min(area_a, area_b) / max(area_a, area_b)


def infer_keyframe_spacing(frame_groups) -> int:
    frame_indices = [int(frame_index) for (frame_index, _frame_file), _frame_rows in frame_groups]
    positive_deltas = [
        current - previous
        for previous, current in zip(frame_indices, frame_indices[1:])
        if current > previous
    ]
    if not positive_deltas:
        return 0

    return min(positive_deltas)


def associate_tracks(
    frame_groups,
    max_track_frame_gap: int,
    min_track_iou: float,
    max_track_center_distance_ratio: float,
    reference_width: int,
    reference_height: int,
) -> tuple[list[dict[str, object]], dict[int, dict[str, object]]]:
    # The tracker is deliberately simple: we only need stable AOI identities for
    # sparse keyframes, not high-frequency MOT performance. IoU + center
    # distance gives a robust-enough identity handoff for the current pipeline.
    active_tracks: dict[int, TrackState] = {}
    definitions_by_id: dict[int, dict[str, object]] = {}
    sequence_frames: list[dict[str, object]] = []
    next_track_id = 1
    image_diagonal = math.hypot(float(reference_width), float(reference_height))
    max_center_distance_px = image_diagonal * max_track_center_distance_ratio

    for (frame_index, frame_file), frame_detections in frame_groups:
        frame_index = int(frame_index)
        active_tracks = {
            track_id: track
            for track_id, track in active_tracks.items()
            if (frame_index - track.last_frame_index) <= max_track_frame_gap
        }
        frame_rows = frame_detections.sort_values(["confidence", "detection_index"], ascending=[False, True]).copy()
        assigned_track_ids: set[int] = set()
        frame_entries: list[dict[str, object]] = []

        for row in frame_rows.itertuples(index=False):
            label = str(row.label)
            prompt = str(row.prompt)
            bbox = (float(row.x_min), float(row.y_min), float(row.x_max), float(row.y_max))

            best_track: TrackState | None = None
            best_score: tuple[float, float, float, float] | None = None

            for track in active_tracks.values():
                if track.track_id in assigned_track_ids:
                    continue
                if track.label != label:
                    continue

                frame_gap = frame_index - track.last_frame_index
                if frame_gap < 0 or frame_gap > max_track_frame_gap:
                    continue

                iou = bbox_iou(track.last_bbox, bbox)
                center_distance = bbox_center_distance(track.last_bbox, bbox)
                area_similarity = bbox_area_similarity(track.last_bbox, bbox)

                if iou < min_track_iou and center_distance > max_center_distance_px:
                    continue
                if area_similarity < 0.2 and center_distance > (max_center_distance_px * 0.5):
                    continue

                score = (iou, area_similarity, -center_distance, -frame_gap)
                if best_score is None or score > best_score:
                    best_track = track
                    best_score = score

            if best_track is None:
                track_id = next_track_id
                next_track_id += 1
                color = build_distinct_hex_color(track_id)
                best_track = TrackState(
                    track_id=track_id,
                    label=label,
                    prompt=prompt,
                    color=color,
                    name=f"{label}_{track_id:02d}",
                    first_frame_index=frame_index,
                    last_frame_index=frame_index,
                    last_bbox=bbox,
                )
                active_tracks[track_id] = best_track
                definitions_by_id[track_id] = {
                    "id": track_id,
                    "name": best_track.name,
                    "prompt": prompt,
                    "category": label,
                    "parentId": 0,
                    "color": color,
                    "firstFrameIndex": frame_index,
                    "lastFrameIndex": frame_index,
                    "keyframeCount": 0,
                }

            assigned_track_ids.add(best_track.track_id)
            best_track.last_frame_index = frame_index
            best_track.last_bbox = bbox
            best_track.keyframe_count += 1

            definition = definitions_by_id[best_track.track_id]
            definition["lastFrameIndex"] = frame_index
            definition["keyframeCount"] = int(definition["keyframeCount"]) + 1

            frame_entries.append(
                {
                    "aoi_id": best_track.track_id,
                    "aoi_name": best_track.name,
                    "aoi_category": label,
                    "aoi_prompt": prompt,
                    "aoi_color": best_track.color,
                    "frame_index": frame_index,
                    "frame_file": str(frame_file),
                    "detection_index": int(row.detection_index),
                    "label": label,
                    "confidence": float(row.confidence),
                    "x_min": float(row.x_min),
                    "y_min": float(row.y_min),
                    "x_max": float(row.x_max),
                    "y_max": float(row.y_max),
                }
            )

        sequence_frames.append(
            {
                "frameIndex": frame_index,
                "frameFile": str(frame_file),
                "detections": frame_entries,
            }
        )

    return sequence_frames, definitions_by_id


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

    detections = load_and_filter_detections(
        detections_csv=detections_csv,
        include_labels=include_labels,
        min_confidence=min_confidence,
    )

    output_maps_dir = Path(output_maps_dir)
    output_keyframes_dir = Path(output_keyframes_dir)
    output_maps_dir.mkdir(parents=True, exist_ok=True)
    output_keyframes_dir.mkdir(parents=True, exist_ok=True)

    frame_groups = list(detections.groupby(["frame_index", "frame_file"], sort=True))
    original_frame_group_count = len(frame_groups)
    if max_frames is not None:
        frame_groups = frame_groups[: max(0, max_frames)]
    if frame_step is not None and frame_step > 0:
        frame_groups = [
            frame_group
            for frame_group in frame_groups
            if int(frame_group[0][0]) % frame_step == 0
        ]

    if not frame_groups:
        raise RuntimeError("No frame groups remain after applying the current sequence filters.")

    reference_width, reference_height = infer_reference_frame_size(frame_groups, frames_dir)
    _emit_log(
        log_callback,
        (
            "[build_aoi_sequence] Building AOI sequence with "
            f"{len(frame_groups)} keyframes out of {original_frame_group_count} detected frame groups "
            f"at {reference_width}x{reference_height} source resolution."
        ),
    )
    _emit_log(
        log_callback,
        (
            "[build_aoi_sequence] Runtime export settings: "
            f"{output_width or reference_width}x{output_height or reference_height}, "
            f"yaw offset {yaw_offset_degrees} degrees."
        ),
    )
    if frame_step is not None and frame_step > 0:
        _emit_log(
            log_callback,
            f"[build_aoi_sequence] Keeping only absolute video frames that match the step {frame_step}.",
        )

    inferred_keyframe_spacing = infer_keyframe_spacing(frame_groups)
    effective_max_track_frame_gap = max_track_frame_gap
    if inferred_keyframe_spacing > 0:
        # The tracker compares absolute video-frame indices, so when we export
        # sparse keyframes (for example every 30 frames) the effective gap must
        # be at least that spacing or identities can never survive to the next
        # exported frame. Doubling the spacing also tolerates one missing
        # keyframe without fragmenting the AOI id.
        effective_max_track_frame_gap = max(
            max_track_frame_gap,
            inferred_keyframe_spacing * 2,
        )

    if effective_max_track_frame_gap != max_track_frame_gap:
        _emit_log(
            log_callback,
            (
                "[build_aoi_sequence] Increased the effective track gap from "
                f"{max_track_frame_gap} to {effective_max_track_frame_gap} absolute video frames "
                f"to match the exported keyframe spacing ({inferred_keyframe_spacing})."
            ),
        )

    sequence_frames, definitions_by_id = associate_tracks(
        frame_groups=frame_groups,
        max_track_frame_gap=effective_max_track_frame_gap,
        min_track_iou=min_track_iou,
        max_track_center_distance_ratio=max_track_center_distance_ratio,
        reference_width=reference_width,
        reference_height=reference_height,
    )

    manifest_entries: list[dict[str, object]] = []
    written_count = 0
    id_map_resolution: list[int] | None = None
    total_frames = len(sequence_frames)
    resolved_runtime_pack_path: Path | None = None
    runtime_pack_stream = None
    runtime_pack_frame_byte_length: int | None = None
    _emit_progress(progress_callback, 0, total_frames, "Preparing AOI keyframes.")

    if write_runtime_pack:
        # The binary pack is the preferred Unity runtime path because it removes
        # per-keyframe PNG decoding from the playback loop.
        resolved_runtime_pack_path = build_default_runtime_pack_path(
            manifest_path=manifest_path,
            video_name=video_name,
        ) if runtime_pack_path is None else Path(runtime_pack_path)
        resolved_runtime_pack_path.parent.mkdir(parents=True, exist_ok=True)
        runtime_pack_stream = resolved_runtime_pack_path.open("wb")
        _emit_log(
            log_callback,
            f"[build_aoi_sequence] Writing runtime AOI pack to '{resolved_runtime_pack_path}'.",
        )

    try:
        for processed_index, frame in enumerate(sequence_frames, start=1):
            frame_index = int(frame["frameIndex"])
            frame_file = str(frame["frameFile"])
            frame_stem = Path(frame_file).stem
            output_map_path = output_maps_dir / f"{frame_stem}_aoi_map.png"
            output_keyframe_path = output_keyframes_dir / f"{frame_stem}_aoi_keyframe.json"

            if skip_existing and output_map_path.exists() and output_keyframe_path.exists():
                with Image.open(output_map_path) as existing_map_image:
                    if id_map_resolution is None:
                        id_map_resolution = [existing_map_image.width, existing_map_image.height]
                    pack_offset = None
                    pack_length = None
                    if runtime_pack_stream is not None:
                        # Even when reusing prior PNGs, keep the runtime pack in
                        # sync so Unity can stay on the fast path.
                        existing_rgb_bytes = existing_map_image.convert("RGB").tobytes()
                        pack_offset = runtime_pack_stream.tell()
                        pack_length = len(existing_rgb_bytes)
                        runtime_pack_stream.write(existing_rgb_bytes)
                        if runtime_pack_frame_byte_length is None:
                            runtime_pack_frame_byte_length = pack_length

                existing_keyframe_document = json.loads(output_keyframe_path.read_text(encoding="utf-8"))
                manifest_entries.append(
                    {
                        "frameIndex": frame_index,
                        "frameFile": frame_file,
                        "mapFile": output_map_path.name,
                        "keyframeFile": output_keyframe_path.name,
                        "aoiCount": int(len(existing_keyframe_document.get("aois", []))),
                        "packOffset": pack_offset,
                        "packLength": pack_length,
                        "skipped": True,
                    }
                )
                _emit_progress(
                    progress_callback,
                    processed_index,
                    total_frames,
                    f"Skipped existing AOI outputs for {frame_file}.",
                )
                continue

            import pandas as pd

            frame_detections = pd.DataFrame(frame["detections"])
            summary = render_aoi_map_from_detections(
                detections=frame_detections,
                frames_dir=frames_dir,
                output_map_path=output_map_path,
                output_metadata_path=None,
                video_name=video_name,
                fps=fps,
                box_padding=box_padding,
                write_metadata_document=False,
                output_width=output_width,
                output_height=output_height,
                yaw_offset_degrees=yaw_offset_degrees,
            )

            if id_map_resolution is None:
                id_map_resolution = [int(summary["image_width"]), int(summary["image_height"])]

            pack_offset = None
            pack_length = None
            if runtime_pack_stream is not None:
                # Write the packed RGB bytes in frame order so Unity can seek by
                # offset without parsing image files at runtime.
                rgb_bytes = summary["rgb24_bytes"]
                pack_offset = runtime_pack_stream.tell()
                pack_length = len(rgb_bytes)
                runtime_pack_stream.write(rgb_bytes)
                if runtime_pack_frame_byte_length is None:
                    runtime_pack_frame_byte_length = pack_length

            output_keyframe_path.write_text(
                json.dumps(
                    {
                        "video": video_name,
                        "frameIndex": int(summary["frame_index"]),
                        "frameFile": summary["frame_file"],
                        "mapFile": output_map_path.name,
                        "aois": [
                            {
                                "id": int(aoi["id"]),
                                "bbox": aoi["bbox"],
                                "confidence": float(aoi["confidence"]),
                                "sourceDetectionIndex": int(aoi["sourceDetectionIndex"]),
                            }
                            for aoi in summary["aois"]
                        ],
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )

            manifest_entries.append(
                {
                    "frameIndex": int(summary["frame_index"]),
                    "frameFile": summary["frame_file"],
                    "mapFile": output_map_path.name,
                    "keyframeFile": output_keyframe_path.name,
                    "aoiCount": int(summary["aoi_count"]),
                    "packOffset": pack_offset,
                    "packLength": pack_length,
                    "skipped": False,
                }
            )
            written_count += 1
            _emit_progress(
                progress_callback,
                processed_index,
                total_frames,
                f"Wrote AOI keyframe {frame_file} with {summary['aoi_count']} AOIs.",
            )
    finally:
        if runtime_pack_stream is not None:
            runtime_pack_stream.close()

    manifest = {
        "video": video_name,
        "fps": int(fps),
        "sourceFrameResolution": [reference_width, reference_height],
        "idMapResolution": id_map_resolution or [],
        "frameStep": int(frame_step) if frame_step is not None else None,
        "mapsDirectory": str(output_maps_dir),
        "keyframesDirectory": str(output_keyframes_dir),
        "aois": list(definitions_by_id.values()),
        "frameCount": len(manifest_entries),
        "writtenCount": written_count,
        "bakedYawOffsetDegrees": float(yaw_offset_degrees),
        "frames": manifest_entries,
    }

    if resolved_runtime_pack_path is not None and id_map_resolution:
        manifest["runtimePack"] = {
            "file": resolved_runtime_pack_path.name,
            "encoding": "rgb24",
            "frameWidth": int(id_map_resolution[0]),
            "frameHeight": int(id_map_resolution[1]),
            "bytesPerPixel": 3,
            "frameByteLength": int(runtime_pack_frame_byte_length or (id_map_resolution[0] * id_map_resolution[1] * 3)),
        }

    if manifest_path is not None:
        manifest_path = Path(manifest_path)
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    _emit_log(
        log_callback,
        (
            "[build_aoi_sequence] Completed sequence export with "
            f"{len(definitions_by_id)} persistent AOIs across {len(manifest_entries)} keyframes."
        ),
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
    parser.add_argument(
        "--fps",
        type=int,
        default=30,
        help="FPS metadata to write into the AOI metadata JSON files.",
    )
    parser.add_argument(
        "--include-label",
        action="append",
        dest="include_labels",
        help="Optional label filter. Repeat to keep multiple labels.",
    )
    parser.add_argument("--min-confidence", type=float, default=0.35)
    parser.add_argument("--box-padding", type=int, default=0)
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
    parser.add_argument(
        "--output-width",
        type=int,
        default=None,
        help="Optional output AOI map width for runtime-friendly exports.",
    )
    parser.add_argument(
        "--output-height",
        type=int,
        default=None,
        help="Optional output AOI map height for runtime-friendly exports.",
    )
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
    parser = build_parser()
    args = parser.parse_args()
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
