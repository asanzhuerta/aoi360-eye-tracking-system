from __future__ import annotations

"""Run a small manual-vs-detector IoU validation over a seeded test-frame subset."""

import argparse
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd

from aoi360_pipeline.benchmark_detectors import parse_video_prompt_overrides
from aoi360_pipeline.detectors import (
    SUPPORTED_DETECTORS,
    default_detections_csv_name,
    detect_frames_with_backend,
    detector_display_name,
    normalize_detector_name,
    resolve_default_model_id,
)
from aoi360_pipeline.rebuild_runtime_assets import find_repo_root
from aoi360_pipeline.runtime_environment import inspect_torch_runtime

DEFAULT_MANIFEST_CSV = Path("data") / "manual_gt" / "benchmark_iou" / "frame_subset_manifest.csv"
DEFAULT_MANUAL_BOXES_CSV = Path("data") / "manual_gt" / "benchmark_iou" / "manual_boxes.csv"
DEFAULT_FRAME_ROOT = Path("data") / "manual_gt" / "benchmark_iou" / "frame_subset"
DEFAULT_PROMPT_FILE = Path("data") / "promts" / "3videosPromt.json"
DEFAULT_OUTPUT_ROOT = Path("data") / "exports" / "benchmarks" / "spatial_iou"
DEFAULT_DETECTORS = ["grounding_dino", "owlv2", "yolo_world"]

MANIFEST_REQUIRED_COLUMNS = ["video_id", "frame_file", "scene_group"]
MANUAL_REQUIRED_COLUMNS = ["video_id", "frame_file", "label", "x_min", "y_min", "x_max", "y_max"]


@dataclass(frozen=True)
class ValidationDataset:
    video_id: str
    scene_group: str
    frames_dir: Path
    frame_count: int
    text_prompt: str


def _resolve_repo_path(repo_root: Path, candidate: str | Path) -> Path:
    path = Path(candidate)
    if path.is_absolute():
        return path
    return (repo_root / path).resolve()


def _load_manifest(manifest_csv: Path) -> pd.DataFrame:
    manifest = pd.read_csv(manifest_csv)
    missing = [column for column in MANIFEST_REQUIRED_COLUMNS if column not in manifest.columns]
    if missing:
        raise ValueError(f"Manifest is missing required columns: {', '.join(missing)}")
    if manifest.empty:
        raise ValueError("Frame subset manifest is empty.")

    manifest = manifest.copy()
    for column in ["video_id", "frame_file", "scene_group"]:
        manifest[column] = manifest[column].astype(str).str.strip()

    duplicated = manifest.duplicated(subset=["video_id", "frame_file"], keep=False)
    if duplicated.any():
        duplicates = manifest.loc[duplicated, ["video_id", "frame_file"]]
        raise ValueError(
            "Frame subset manifest contains duplicated frame rows: "
            + ", ".join(f"{row.video_id}/{row.frame_file}" for row in duplicates.itertuples(index=False))
        )

    return manifest


def _load_manual_boxes(manual_boxes_csv: Path, manifest: pd.DataFrame) -> pd.DataFrame:
    manual_boxes = pd.read_csv(manual_boxes_csv)
    missing = [column for column in MANUAL_REQUIRED_COLUMNS if column not in manual_boxes.columns]
    if missing:
        raise ValueError(f"Manual boxes CSV is missing required columns: {', '.join(missing)}")
    if manual_boxes.empty:
        raise ValueError(
            "Manual boxes CSV is empty. Fill data/manual_gt/benchmark_iou/manual_boxes.csv before running IoU validation."
        )

    manual_boxes = manual_boxes.copy()
    for column in ["video_id", "frame_file", "label"]:
        manual_boxes[column] = manual_boxes[column].astype(str).str.strip()

    for column in ["x_min", "y_min", "x_max", "y_max"]:
        manual_boxes[column] = pd.to_numeric(manual_boxes[column], errors="raise")

    invalid_boxes = manual_boxes[
        (manual_boxes["x_max"] <= manual_boxes["x_min"]) | (manual_boxes["y_max"] <= manual_boxes["y_min"])
    ]
    if not invalid_boxes.empty:
        raise ValueError("Manual boxes CSV contains invalid coordinates where max <= min.")

    manifest_pairs = set(zip(manifest["video_id"], manifest["frame_file"], strict=False))
    unknown_pairs = [
        (row.video_id, row.frame_file)
        for row in manual_boxes.loc[:, ["video_id", "frame_file"]].itertuples(index=False)
        if (row.video_id, row.frame_file) not in manifest_pairs
    ]
    if unknown_pairs:
        preview = ", ".join(f"{video}/{frame}" for video, frame in unknown_pairs[:5])
        raise ValueError(f"Manual boxes reference frames not present in the manifest: {preview}")

    manual_boxes["gt_id"] = range(1, len(manual_boxes) + 1)
    return manual_boxes


def _build_validation_datasets(
    *,
    manifest: pd.DataFrame,
    frame_root: Path,
    prompt_mapping: dict[str, str],
) -> list[ValidationDataset]:
    datasets: list[ValidationDataset] = []
    for video_id, group in manifest.groupby("video_id", sort=True):
        scene_groups = group["scene_group"].dropna().astype(str).str.strip().unique().tolist()
        if len(scene_groups) != 1:
            raise ValueError(f"Manifest rows for {video_id} contain multiple scene_group values: {scene_groups}")

        if video_id not in prompt_mapping:
            raise ValueError(f"No prompt mapping found for benchmark video '{video_id}'.")

        frames_dir = frame_root / video_id
        if not frames_dir.exists():
            raise FileNotFoundError(f"Frame subset directory not found: {frames_dir}")

        expected_files = set(group["frame_file"].tolist())
        existing_files = {path.name for path in frames_dir.glob("*") if path.is_file()}
        missing_files = sorted(expected_files - existing_files)
        if missing_files:
            raise FileNotFoundError(
                f"Frame subset directory {frames_dir} is missing expected files: {', '.join(missing_files)}"
            )

        datasets.append(
            ValidationDataset(
                video_id=video_id,
                scene_group=scene_groups[0],
                frames_dir=frames_dir,
                frame_count=len(expected_files),
                text_prompt=prompt_mapping[video_id],
            )
        )

    return datasets


def _compute_iou(gt_row: pd.Series, pred_row: pd.Series) -> float:
    x_left = max(float(gt_row["x_min"]), float(pred_row["x_min"]))
    y_top = max(float(gt_row["y_min"]), float(pred_row["y_min"]))
    x_right = min(float(gt_row["x_max"]), float(pred_row["x_max"]))
    y_bottom = min(float(gt_row["y_max"]), float(pred_row["y_max"]))

    if x_right <= x_left or y_bottom <= y_top:
        return 0.0

    intersection = (x_right - x_left) * (y_bottom - y_top)
    gt_area = (float(gt_row["x_max"]) - float(gt_row["x_min"])) * (float(gt_row["y_max"]) - float(gt_row["y_min"]))
    pred_area = (float(pred_row["x_max"]) - float(pred_row["x_min"])) * (
        float(pred_row["y_max"]) - float(pred_row["y_min"])
    )
    union = gt_area + pred_area - intersection
    if union <= 0:
        return 0.0
    return float(intersection / union)


def _match_group(gt_group: pd.DataFrame, pred_group: pd.DataFrame) -> tuple[list[dict[str, object]], int, int]:
    candidate_pairs: list[tuple[float, int, int]] = []
    for gt_row in gt_group.itertuples():
        for pred_row in pred_group.itertuples():
            iou = _compute_iou(pd.Series(gt_row._asdict()), pd.Series(pred_row._asdict()))
            if iou > 0:
                candidate_pairs.append((iou, int(gt_row.gt_id), int(pred_row.pred_id)))

    candidate_pairs.sort(key=lambda item: item[0], reverse=True)

    matched_gt: set[int] = set()
    matched_pred: set[int] = set()
    chosen_pairs: dict[int, tuple[float, int]] = {}

    for iou, gt_id, pred_id in candidate_pairs:
        if gt_id in matched_gt or pred_id in matched_pred:
            continue
        matched_gt.add(gt_id)
        matched_pred.add(pred_id)
        chosen_pairs[gt_id] = (iou, pred_id)

    result_rows: list[dict[str, object]] = []
    pred_lookup = pred_group.set_index("pred_id", drop=False)
    for gt_row in gt_group.itertuples(index=False):
        match = chosen_pairs.get(int(gt_row.gt_id))
        matched = match is not None
        iou = float(match[0]) if match else 0.0
        pred_row = pred_lookup.loc[match[1]] if match else None
        result_rows.append(
            {
                "gt_id": int(gt_row.gt_id),
                "pred_id": int(pred_row["pred_id"]) if pred_row is not None else pd.NA,
                "iou": iou,
                "matched_any_iou": matched,
                "pred_confidence": float(pred_row["confidence"]) if pred_row is not None else pd.NA,
                "pred_source": str(pred_row["source"]) if pred_row is not None else pd.NA,
                "pred_model_id": str(pred_row["model_id"]) if pred_row is not None else pd.NA,
                "pred_x_min": float(pred_row["x_min"]) if pred_row is not None else pd.NA,
                "pred_y_min": float(pred_row["y_min"]) if pred_row is not None else pd.NA,
                "pred_x_max": float(pred_row["x_max"]) if pred_row is not None else pd.NA,
                "pred_y_max": float(pred_row["y_max"]) if pred_row is not None else pd.NA,
            }
        )

    return result_rows, len(matched_gt), len(pred_group) - len(matched_pred)


def _evaluate_detector_rows(
    *,
    detector: str,
    detector_name: str,
    scene_map: dict[tuple[str, str], str],
    manual_boxes: pd.DataFrame,
    detections: pd.DataFrame,
    iou_threshold: float,
) -> tuple[pd.DataFrame, dict[str, int]]:
    manual_with_scene = manual_boxes.copy()
    manual_with_scene["scene_group"] = manual_with_scene.apply(
        lambda row: scene_map[(row["video_id"], row["frame_file"])], axis=1
    )

    detector_detections = detections[detections["detector"] == detector].copy()
    detector_detections["pred_id"] = range(1, len(detector_detections) + 1)

    result_rows: list[dict[str, object]] = []
    total_gt = 0
    total_pred = len(detector_detections)
    threshold_matches = 0
    unmatched_pred_total = 0

    group_keys = sorted(
        {
            (row.video_id, row.frame_file, row.label)
            for row in manual_with_scene.loc[:, ["video_id", "frame_file", "label"]].itertuples(index=False)
        }
        | {
            (row.video_id, row.frame_file, row.label)
            for row in detector_detections.loc[:, ["video_id", "frame_file", "label"]].itertuples(index=False)
        }
    )

    for video_id, frame_file, label in group_keys:
        gt_group = manual_with_scene[
            (manual_with_scene["video_id"] == video_id)
            & (manual_with_scene["frame_file"] == frame_file)
            & (manual_with_scene["label"] == label)
        ].copy()
        pred_group = detector_detections[
            (detector_detections["video_id"] == video_id)
            & (detector_detections["frame_file"] == frame_file)
            & (detector_detections["label"] == label)
        ].copy()

        total_gt += len(gt_group)
        if gt_group.empty:
            unmatched_pred_total += len(pred_group)
            continue

        matched_rows, _, unmatched_pred_count = _match_group(gt_group, pred_group)
        unmatched_pred_total += unmatched_pred_count

        matched_lookup = {row["gt_id"]: row for row in matched_rows}
        for gt_row in gt_group.itertuples(index=False):
            row_match = matched_lookup[int(gt_row.gt_id)]
            passed_threshold = bool(row_match["iou"] >= iou_threshold and row_match["matched_any_iou"])
            if passed_threshold:
                threshold_matches += 1
            result_rows.append(
                {
                    "detector": detector,
                    "detector_name": detector_name,
                    "video_id": video_id,
                    "scene_group": scene_map[(video_id, frame_file)],
                    "frame_file": frame_file,
                    "label": label,
                    "gt_id": int(gt_row.gt_id),
                    "gt_x_min": float(gt_row.x_min),
                    "gt_y_min": float(gt_row.y_min),
                    "gt_x_max": float(gt_row.x_max),
                    "gt_y_max": float(gt_row.y_max),
                    "pred_id": row_match["pred_id"],
                    "pred_confidence": row_match["pred_confidence"],
                    "pred_source": row_match["pred_source"],
                    "pred_model_id": row_match["pred_model_id"],
                    "pred_x_min": row_match["pred_x_min"],
                    "pred_y_min": row_match["pred_y_min"],
                    "pred_x_max": row_match["pred_x_max"],
                    "pred_y_max": row_match["pred_y_max"],
                    "iou": float(row_match["iou"]),
                    "matched_any_iou": bool(row_match["matched_any_iou"]),
                    "match_at_threshold": passed_threshold,
                }
            )

    rows_df = pd.DataFrame(result_rows)
    summary_counts = {
        "gt_box_count": total_gt,
        "pred_box_count": total_pred,
        "true_positive_count": threshold_matches,
        "false_positive_count": max(total_pred - threshold_matches, 0),
        "false_negative_count": max(total_gt - threshold_matches, 0),
        "unmatched_prediction_count": unmatched_pred_total,
    }
    return rows_df, summary_counts


def _build_summary(
    *,
    rows: pd.DataFrame,
    manual_boxes: pd.DataFrame,
    detections: pd.DataFrame,
    counts_by_detector: dict[str, dict[str, int]],
    iou_threshold: float,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    summary_rows: list[dict[str, object]] = []
    scene_rows: list[dict[str, object]] = []
    video_rows: list[dict[str, object]] = []

    for detector, detector_rows in rows.groupby("detector", sort=True):
        detector_name = str(detector_rows["detector_name"].iloc[0])
        counts = counts_by_detector[detector]
        tp = counts["true_positive_count"]
        pred_count = counts["pred_box_count"]
        gt_count = counts["gt_box_count"]
        summary_rows.append(
            {
                "detector": detector,
                "detector_name": detector_name,
                "mean_iou": float(detector_rows["iou"].mean()) if not detector_rows.empty else 0.0,
                "precision_at_threshold": float(tp / pred_count) if pred_count else 0.0,
                "recall_at_threshold": float(tp / gt_count) if gt_count else 0.0,
                "gt_box_count": gt_count,
                "pred_box_count": pred_count,
                "true_positive_count": tp,
                "false_positive_count": counts["false_positive_count"],
                "false_negative_count": counts["false_negative_count"],
                "iou_threshold": iou_threshold,
            }
        )

        for scene_group, scene_group_rows in detector_rows.groupby("scene_group", sort=True):
            scene_gt_count = len(manual_boxes[manual_boxes["scene_group"] == scene_group])
            scene_tp = int(scene_group_rows["match_at_threshold"].sum())
            scene_pred_count = len(
                detections[(detections["detector"] == detector) & (detections["scene_group"] == scene_group)]
            )
            scene_rows.append(
                {
                    "detector": detector,
                    "detector_name": detector_name,
                    "scene_group": scene_group,
                    "mean_iou": float(scene_group_rows["iou"].mean()) if not scene_group_rows.empty else 0.0,
                    "precision_at_threshold": float(scene_tp / scene_pred_count) if scene_pred_count else 0.0,
                    "recall_at_threshold": float(scene_tp / scene_gt_count) if scene_gt_count else 0.0,
                    "gt_box_count": scene_gt_count,
                    "pred_box_count": scene_pred_count,
                    "matched_box_count": scene_tp,
                    "iou_threshold": iou_threshold,
                }
            )

        for video_id, video_rows_group in detector_rows.groupby("video_id", sort=True):
            video_gt_count = len(manual_boxes[manual_boxes["video_id"] == video_id])
            video_tp = int(video_rows_group["match_at_threshold"].sum())
            video_pred_count = len(detections[(detections["detector"] == detector) & (detections["video_id"] == video_id)])
            video_rows.append(
                {
                    "detector": detector,
                    "detector_name": detector_name,
                    "video_id": video_id,
                    "scene_group": str(video_rows_group["scene_group"].iloc[0]),
                    "mean_iou": float(video_rows_group["iou"].mean()) if not video_rows_group.empty else 0.0,
                    "precision_at_threshold": float(video_tp / video_pred_count) if video_pred_count else 0.0,
                    "recall_at_threshold": float(video_tp / video_gt_count) if video_gt_count else 0.0,
                    "gt_box_count": video_gt_count,
                    "pred_box_count": video_pred_count,
                    "matched_box_count": video_tp,
                    "iou_threshold": iou_threshold,
                }
            )

    return pd.DataFrame(summary_rows), pd.DataFrame(scene_rows), pd.DataFrame(video_rows)


def _run_detectors(
    *,
    datasets: list[ValidationDataset],
    detectors: list[str],
    output_dir: Path,
    box_threshold: float,
    text_threshold: float,
    batch_size: int,
    inference_max_width: int | None,
    inference_max_height: int | None,
    preload_workers: int,
    precision: str,
) -> pd.DataFrame:
    detections_output_dir = output_dir / "detections"
    detections_output_dir.mkdir(parents=True, exist_ok=True)

    all_detections: list[pd.DataFrame] = []
    for detector in detectors:
        detector_name = detector_display_name(detector)
        model_id = resolve_default_model_id(detector)
        for dataset in datasets:
            print(
                f"[verify_spatial_iou] Running {detector_name} on {dataset.video_id} "
                f"({dataset.frame_count} frames, scene_group={dataset.scene_group})."
            )
            output_csv = detections_output_dir / default_detections_csv_name(dataset.video_id, detector)
            detections = detect_frames_with_backend(
                detector=detector,
                frames_dir=dataset.frames_dir,
                output_csv=output_csv,
                text_prompt=dataset.text_prompt,
                box_threshold=box_threshold,
                text_threshold=text_threshold,
                model_id=model_id,
                batch_size=batch_size,
                inference_max_width=inference_max_width,
                inference_max_height=inference_max_height,
                preload_workers=preload_workers,
                precision=precision,
            ).copy()
            detections["video_id"] = dataset.video_id
            detections["scene_group"] = dataset.scene_group
            detections["detector"] = detector
            detections["detector_name"] = detector_name
            all_detections.append(detections)

    if not all_detections:
        raise RuntimeError("No detections were produced during the spatial IoU validation run.")

    return pd.concat(all_detections, ignore_index=True)


def run_spatial_iou_validation(
    *,
    repo_root: str | Path | None = None,
    manifest_csv: str | Path = DEFAULT_MANIFEST_CSV,
    manual_boxes_csv: str | Path = DEFAULT_MANUAL_BOXES_CSV,
    frame_root: str | Path = DEFAULT_FRAME_ROOT,
    output_root: str | Path = DEFAULT_OUTPUT_ROOT,
    prompt_file: str | Path = DEFAULT_PROMPT_FILE,
    detectors: list[str] | None = None,
    iou_threshold: float = 0.5,
    box_threshold: float = 0.35,
    text_threshold: float = 0.25,
    batch_size: int = 0,
    inference_max_width: int | None = 1920,
    inference_max_height: int | None = 960,
    preload_workers: int = 0,
    precision: str = "auto",
) -> dict[str, object]:
    repo_root_path = find_repo_root(repo_root)
    manifest_path = _resolve_repo_path(repo_root_path, manifest_csv)
    manual_boxes_path = _resolve_repo_path(repo_root_path, manual_boxes_csv)
    frame_root_path = _resolve_repo_path(repo_root_path, frame_root)
    output_root_path = _resolve_repo_path(repo_root_path, output_root)
    prompt_file_path = _resolve_repo_path(repo_root_path, prompt_file)

    manifest = _load_manifest(manifest_path)
    manual_boxes = _load_manual_boxes(manual_boxes_path, manifest)
    prompt_mapping = parse_video_prompt_overrides(prompt_file=prompt_file_path)

    datasets = _build_validation_datasets(
        manifest=manifest,
        frame_root=frame_root_path,
        prompt_mapping=prompt_mapping,
    )

    selected_detectors = [normalize_detector_name(detector) for detector in (detectors or DEFAULT_DETECTORS)]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = output_root_path / timestamp
    output_dir.mkdir(parents=True, exist_ok=True)

    detections = _run_detectors(
        datasets=datasets,
        detectors=selected_detectors,
        output_dir=output_dir,
        box_threshold=box_threshold,
        text_threshold=text_threshold,
        batch_size=batch_size,
        inference_max_width=inference_max_width,
        inference_max_height=inference_max_height,
        preload_workers=preload_workers,
        precision=precision,
    )

    scene_map = {
        (row.video_id, row.frame_file): row.scene_group
        for row in manifest.loc[:, ["video_id", "frame_file", "scene_group"]].itertuples(index=False)
    }
    manual_boxes_with_scene = manual_boxes.copy()
    manual_boxes_with_scene["scene_group"] = manual_boxes_with_scene.apply(
        lambda row: scene_map[(row["video_id"], row["frame_file"])], axis=1
    )

    per_detector_rows: list[pd.DataFrame] = []
    counts_by_detector: dict[str, dict[str, int]] = {}
    for detector in selected_detectors:
        rows_df, counts = _evaluate_detector_rows(
            detector=detector,
            detector_name=detector_display_name(detector),
            scene_map=scene_map,
            manual_boxes=manual_boxes,
            detections=detections,
            iou_threshold=iou_threshold,
        )
        per_detector_rows.append(rows_df)
        counts_by_detector[detector] = counts

    iou_rows = pd.concat(per_detector_rows, ignore_index=True)
    summary_by_detector, summary_by_scene_group, summary_by_video = _build_summary(
        rows=iou_rows,
        manual_boxes=manual_boxes_with_scene,
        detections=detections,
        counts_by_detector=counts_by_detector,
        iou_threshold=iou_threshold,
    )

    iou_rows.to_csv(output_dir / "spatial_iou_rows.csv", index=False)
    summary_by_detector.to_csv(output_dir / "spatial_iou_summary_by_detector.csv", index=False)
    summary_by_scene_group.to_csv(output_dir / "spatial_iou_summary_by_scene_group.csv", index=False)
    summary_by_video.to_csv(output_dir / "spatial_iou_summary_by_video.csv", index=False)

    metadata = {
        "output_dir": str(output_dir),
        "manifest_csv": str(manifest_path),
        "manual_boxes_csv": str(manual_boxes_path),
        "frame_root": str(frame_root_path),
        "prompt_file": str(prompt_file_path),
        "detectors": selected_detectors,
        "supported_detectors": SUPPORTED_DETECTORS,
        "iou_threshold": iou_threshold,
        "box_threshold": box_threshold,
        "text_threshold": text_threshold,
        "batch_size": batch_size,
        "inference_max_width": inference_max_width,
        "inference_max_height": inference_max_height,
        "preload_workers": preload_workers,
        "precision": precision,
        "dataset_rows": len(manifest),
        "manual_box_count": len(manual_boxes),
        "runtime": asdict(inspect_torch_runtime()),
    }
    (output_dir / "spatial_iou_metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    return {
        "output_dir": str(output_dir),
        "rows_path": str(output_dir / "spatial_iou_rows.csv"),
        "summary_by_detector_path": str(output_dir / "spatial_iou_summary_by_detector.csv"),
        "summary_by_scene_group_path": str(output_dir / "spatial_iou_summary_by_scene_group.csv"),
        "summary_by_video_path": str(output_dir / "spatial_iou_summary_by_video.csv"),
        "metadata_path": str(output_dir / "spatial_iou_metadata.json"),
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate detector boxes against manual benchmark annotations through IoU."
    )
    parser.add_argument("--manifest-csv", default=str(DEFAULT_MANIFEST_CSV))
    parser.add_argument("--manual-boxes-csv", default=str(DEFAULT_MANUAL_BOXES_CSV))
    parser.add_argument("--frame-root", default=str(DEFAULT_FRAME_ROOT))
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument("--prompt-file", default=str(DEFAULT_PROMPT_FILE))
    parser.add_argument(
        "--detector",
        action="append",
        dest="detectors",
        choices=sorted(SUPPORTED_DETECTORS),
        help="Repeat to benchmark specific detectors. Defaults to all supported backends.",
    )
    parser.add_argument("--iou-threshold", type=float, default=0.5)
    parser.add_argument("--box-threshold", type=float, default=0.35)
    parser.add_argument("--text-threshold", type=float, default=0.25)
    parser.add_argument("--batch-size", type=int, default=0)
    parser.add_argument("--inference-max-width", type=int, default=1920)
    parser.add_argument("--inference-max-height", type=int, default=960)
    parser.add_argument("--preload-workers", type=int, default=0)
    parser.add_argument("--precision", default="auto")
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()
    summary = run_spatial_iou_validation(
        manifest_csv=args.manifest_csv,
        manual_boxes_csv=args.manual_boxes_csv,
        frame_root=args.frame_root,
        output_root=args.output_root,
        prompt_file=args.prompt_file,
        detectors=args.detectors,
        iou_threshold=args.iou_threshold,
        box_threshold=args.box_threshold,
        text_threshold=args.text_threshold,
        batch_size=args.batch_size,
        inference_max_width=args.inference_max_width,
        inference_max_height=args.inference_max_height,
        preload_workers=args.preload_workers,
        precision=args.precision,
    )
    print("[verify_spatial_iou] Spatial IoU validation complete.")
    print(f"[verify_spatial_iou] Output directory: {summary['output_dir']}")
    print(f"[verify_spatial_iou] Detector summary: {summary['summary_by_detector_path']}")


if __name__ == "__main__":
    main()
