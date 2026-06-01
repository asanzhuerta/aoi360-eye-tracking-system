from __future__ import annotations

"""Summarise frame-level failure-taxonomy signals from exported AOI metadata."""

import argparse
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from aoi360_pipeline.rebuild_runtime_assets import find_repo_root

DEFAULT_VIDEO_IDS = ["test1Camera360", "test2Camera360", "test3Lions360"]
DEFAULT_METADATA_ROOT = Path("data") / "processed" / "metadata"
DEFAULT_ANALYTICS_ROOT = Path("data") / "exports" / "analytics" / "20260525_pilot_P01_P08_clean"
DEFAULT_OUTPUT_ROOT = Path("data") / "exports" / "diagnostics" / "failure_taxonomy"


@dataclass(frozen=True)
class DiagnosticConfig:
    video_ids: list[str]
    seam_delta_u: float
    polar_elevation_deg: float
    small_target_area_ratio: float
    metadata_root: str
    analytics_root: str | None


def _resolve_repo_path(repo_root: Path, candidate: str | Path) -> Path:
    path = Path(candidate)
    if path.is_absolute():
        return path
    return (repo_root / path).resolve()


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _build_box_rows(*, video_id: str, metadata_root: Path, seam_delta_u: float, polar_elevation_deg: float) -> tuple[pd.DataFrame, dict[str, Any], pd.DataFrame]:
    manifest_path = metadata_root / f"{video_id}_aoi_sequence_manifest.json"
    manifest = _load_json(manifest_path)

    width, height = manifest["idMapResolution"]
    total_area = float(width * height)
    keyframe_dir = metadata_root / video_id

    aoi_lookup = {int(aoi["id"]): aoi for aoi in manifest["aois"]}
    frame_rows: list[dict[str, Any]] = []
    box_rows: list[dict[str, Any]] = []

    for frame_meta in manifest["frames"]:
        keyframe_path = keyframe_dir / frame_meta["keyframeFile"]
        keyframe = _load_json(keyframe_path)

        total_bbox_area_ratio = 0.0
        max_bbox_area_ratio = 0.0

        for exported_aoi in keyframe["aois"]:
            aoi_id = int(exported_aoi["id"])
            x_min, y_min, x_max, y_max = [float(value) for value in exported_aoi["bbox"]]
            width_px = x_max - x_min
            height_px = y_max - y_min
            area_ratio = (width_px * height_px) / total_area if total_area else 0.0
            u_center = ((x_min + x_max) / 2.0) / float(width)
            v_center = ((y_min + y_max) / 2.0) / float(height)
            elevation_deg = (0.5 - v_center) * 180.0
            seam = min(u_center, 1.0 - u_center) <= seam_delta_u
            polar = abs(elevation_deg) > polar_elevation_deg
            small = area_ratio < 0.01
            confidence = float(exported_aoi["confidence"])

            total_bbox_area_ratio += area_ratio
            max_bbox_area_ratio = max(max_bbox_area_ratio, area_ratio)

            aoi_meta = aoi_lookup[aoi_id]
            box_rows.append(
                {
                    "video_id": video_id,
                    "frame_index": int(keyframe["frameIndex"]),
                    "frame_file": str(keyframe["frameFile"]),
                    "aoi_id": aoi_id,
                    "aoi_name": str(aoi_meta["name"]),
                    "aoi_category": str(aoi_meta["category"]),
                    "confidence": confidence,
                    "bbox_area_ratio": area_ratio,
                    "bbox_area_pct": area_ratio * 100.0,
                    "u_center": u_center,
                    "v_center": v_center,
                    "elevation_deg": elevation_deg,
                    "seam_case": seam,
                    "polar_case": polar,
                    "small_target_case": small,
                }
            )

        frame_rows.append(
            {
                "video_id": video_id,
                "frame_index": int(keyframe["frameIndex"]),
                "frame_file": str(keyframe["frameFile"]),
                "aoi_count": int(len(keyframe["aois"])),
                "total_bbox_area_ratio": total_bbox_area_ratio,
                "total_bbox_area_pct": total_bbox_area_ratio * 100.0,
                "max_single_bbox_area_ratio": max_bbox_area_ratio,
                "max_single_bbox_area_pct": max_bbox_area_ratio * 100.0,
            }
        )

    return pd.DataFrame(box_rows), manifest, pd.DataFrame(frame_rows)


def _summarise_video(*, video_id: str, manifest: dict[str, Any], box_rows: pd.DataFrame, frame_rows: pd.DataFrame) -> dict[str, Any]:
    return {
        "video_id": video_id,
        "source_frame_width": int(manifest["sourceFrameResolution"][0]),
        "source_frame_height": int(manifest["sourceFrameResolution"][1]),
        "id_map_width": int(manifest["idMapResolution"][0]),
        "id_map_height": int(manifest["idMapResolution"][1]),
        "manifest_frame_count": int(manifest["frameCount"]),
        "manifest_aoi_count": int(len(manifest["aois"])),
        "detected_boxes_total": int(len(box_rows)),
        "mean_aoi_count_per_keyframe": float(frame_rows["aoi_count"].mean()),
        "mean_total_bbox_area_pct": float(frame_rows["total_bbox_area_pct"].mean()),
        "median_total_bbox_area_pct": float(frame_rows["total_bbox_area_pct"].median()),
        "mean_max_single_bbox_area_pct": float(frame_rows["max_single_bbox_area_pct"].mean()),
        "mean_box_area_pct": float(box_rows["bbox_area_pct"].mean()),
        "median_box_area_pct": float(box_rows["bbox_area_pct"].median()),
        "small_target_box_count": int(box_rows["small_target_case"].sum()),
        "small_target_box_ratio": float(box_rows["small_target_case"].mean()),
        "seam_case_box_count": int(box_rows["seam_case"].sum()),
        "seam_case_box_ratio": float(box_rows["seam_case"].mean()),
        "polar_case_box_count": int(box_rows["polar_case"].sum()),
        "polar_case_box_ratio": float(box_rows["polar_case"].mean()),
        "mean_confidence": float(box_rows["confidence"].mean()),
    }


def _summarise_aois(*, video_id: str, manifest: dict[str, Any], box_rows: pd.DataFrame) -> pd.DataFrame:
    grouped = (
        box_rows.groupby(["video_id", "aoi_id", "aoi_name", "aoi_category"], as_index=False)
        .agg(
            keyframe_count=("frame_index", "count"),
            mean_confidence=("confidence", "mean"),
            min_confidence=("confidence", "min"),
            mean_box_area_pct=("bbox_area_pct", "mean"),
            min_box_area_pct=("bbox_area_pct", "min"),
            max_box_area_pct=("bbox_area_pct", "max"),
            small_target_box_count=("small_target_case", "sum"),
            seam_case_box_count=("seam_case", "sum"),
            polar_case_box_count=("polar_case", "sum"),
        )
    )

    manifest_rows = []
    for aoi in manifest["aois"]:
        manifest_rows.append(
            {
                "video_id": video_id,
                "aoi_id": int(aoi["id"]),
                "manifest_keyframe_count": int(aoi["keyframeCount"]),
                "first_frame_index": int(aoi["firstFrameIndex"]),
                "last_frame_index": int(aoi["lastFrameIndex"]),
                "track_span_frames": int(aoi["lastFrameIndex"]) - int(aoi["firstFrameIndex"]),
            }
        )

    return grouped.merge(pd.DataFrame(manifest_rows), on=["video_id", "aoi_id"], how="left")


def _merge_pilot_analytics(
    *,
    video_summary: pd.DataFrame,
    aoi_summary: pd.DataFrame,
    analytics_root: Path | None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if analytics_root is None:
        return video_summary, aoi_summary

    runtime_video_path = analytics_root / "runtime_video_summary.csv"
    runtime_aoi_path = analytics_root / "runtime_video_aoi_summary.csv"
    if not runtime_video_path.exists() or not runtime_aoi_path.exists():
        return video_summary, aoi_summary

    runtime_video = pd.read_csv(runtime_video_path)
    runtime_aoi = pd.read_csv(runtime_aoi_path)

    runtime_video = runtime_video.rename(
        columns={
            "assigned_valid_ratio": "pilot_assigned_valid_ratio",
            "rows_total": "pilot_rows_total",
            "participants_total": "pilot_participants_total",
            "session_runs_total": "pilot_session_runs_total",
        }
    )
    runtime_video = runtime_video[
        [
            "video_id",
            "pilot_participants_total",
            "pilot_session_runs_total",
            "pilot_rows_total",
            "pilot_assigned_valid_ratio",
        ]
    ]

    runtime_aoi = runtime_aoi.rename(
        columns={
            "session_hit_count": "pilot_session_hit_count",
            "session_hit_ratio": "pilot_session_hit_ratio",
            "participants_with_hits": "pilot_participants_with_hits",
            "total_visit_count": "pilot_total_visit_count",
            "mean_time_to_first_fixation_ms_when_hit": "pilot_mean_tff_ms_when_hit",
            "mean_dwell_time_ms_when_hit": "pilot_mean_dwell_ms_when_hit",
        }
    )
    runtime_aoi = runtime_aoi[
        [
            "video_id",
            "aoi_id",
            "pilot_session_hit_count",
            "pilot_session_hit_ratio",
            "pilot_participants_with_hits",
            "pilot_total_visit_count",
            "pilot_mean_tff_ms_when_hit",
            "pilot_mean_dwell_ms_when_hit",
        ]
    ]

    return video_summary.merge(runtime_video, on="video_id", how="left"), aoi_summary.merge(
        runtime_aoi, on=["video_id", "aoi_id"], how="left"
    )


def run_diagnostics(
    *,
    video_ids: list[str],
    metadata_root: Path,
    analytics_root: Path | None,
    output_root: Path,
    seam_delta_u: float,
    polar_elevation_deg: float,
) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    destination = output_root / timestamp
    destination.mkdir(parents=True, exist_ok=True)

    all_box_rows: list[pd.DataFrame] = []
    all_frame_rows: list[pd.DataFrame] = []
    video_summary_rows: list[dict[str, Any]] = []
    aoi_summary_frames: list[pd.DataFrame] = []

    for video_id in video_ids:
        box_rows, manifest, frame_rows = _build_box_rows(
            video_id=video_id,
            metadata_root=metadata_root,
            seam_delta_u=seam_delta_u,
            polar_elevation_deg=polar_elevation_deg,
        )
        all_box_rows.append(box_rows)
        all_frame_rows.append(frame_rows)
        video_summary_rows.append(
            _summarise_video(video_id=video_id, manifest=manifest, box_rows=box_rows, frame_rows=frame_rows)
        )
        aoi_summary_frames.append(_summarise_aois(video_id=video_id, manifest=manifest, box_rows=box_rows))

    box_summary = pd.concat(all_box_rows, ignore_index=True)
    frame_summary = pd.concat(all_frame_rows, ignore_index=True)
    video_summary = pd.DataFrame(video_summary_rows)
    aoi_summary = pd.concat(aoi_summary_frames, ignore_index=True)
    video_summary, aoi_summary = _merge_pilot_analytics(
        video_summary=video_summary,
        aoi_summary=aoi_summary,
        analytics_root=analytics_root,
    )

    box_summary.to_csv(destination / "failure_taxonomy_box_rows.csv", index=False)
    frame_summary.to_csv(destination / "failure_taxonomy_frame_summary.csv", index=False)
    video_summary.to_csv(destination / "failure_taxonomy_video_summary.csv", index=False)
    aoi_summary.to_csv(destination / "failure_taxonomy_aoi_summary.csv", index=False)

    config = DiagnosticConfig(
        video_ids=video_ids,
        seam_delta_u=seam_delta_u,
        polar_elevation_deg=polar_elevation_deg,
        small_target_area_ratio=0.01,
        metadata_root=str(metadata_root),
        analytics_root=str(analytics_root) if analytics_root is not None else None,
    )
    (destination / "failure_taxonomy_metadata.json").write_text(
        json.dumps(asdict(config), indent=2),
        encoding="utf-8",
    )
    return destination


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--video-id",
        action="append",
        dest="video_ids",
        help="Video id to include. Defaults to the frozen three-stimulus test corpus.",
    )
    parser.add_argument(
        "--metadata-root",
        default=str(DEFAULT_METADATA_ROOT),
        help="Directory that contains <video>_aoi_sequence_manifest.json and keyframe JSON folders.",
    )
    parser.add_argument(
        "--analytics-root",
        default=str(DEFAULT_ANALYTICS_ROOT),
        help="Optional analytics root with runtime_video_summary.csv and runtime_video_aoi_summary.csv.",
    )
    parser.add_argument(
        "--output-root",
        default=str(DEFAULT_OUTPUT_ROOT),
        help="Directory under which the timestamped diagnostic folder will be written.",
    )
    parser.add_argument(
        "--seam-delta-u",
        type=float,
        default=0.05,
        help="Normalised UV margin used to classify seam proximity.",
    )
    parser.add_argument(
        "--polar-elevation-deg",
        type=float,
        default=60.0,
        help="Absolute elevation threshold used to classify polar distortion cases.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    repo_root = find_repo_root(Path(__file__).resolve())
    video_ids = args.video_ids or DEFAULT_VIDEO_IDS
    metadata_root = _resolve_repo_path(repo_root, args.metadata_root)
    analytics_root = _resolve_repo_path(repo_root, args.analytics_root) if args.analytics_root else None
    output_root = _resolve_repo_path(repo_root, args.output_root)

    destination = run_diagnostics(
        video_ids=video_ids,
        metadata_root=metadata_root,
        analytics_root=analytics_root,
        output_root=output_root,
        seam_delta_u=float(args.seam_delta_u),
        polar_elevation_deg=float(args.polar_elevation_deg),
    )
    print(f"Failure-taxonomy diagnostics written to {destination}")


if __name__ == "__main__":
    main()
