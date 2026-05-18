from __future__ import annotations

"""Benchmark the detector stage over extracted 360-video frames.

The goal of this module is to make detector timing comparisons reproducible.
It measures only the detection stage, not frame extraction or AOI rendering,
so the results remain focused on the two open-vocabulary backends.
"""

import argparse
import json
import shutil
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from time import perf_counter

import pandas as pd

from aoi360_pipeline.detectors import (
    SUPPORTED_DETECTORS,
    detect_frames_with_backend,
    detector_display_name,
    normalize_detector_name,
    resolve_default_model_id,
)
from aoi360_pipeline.rebuild_runtime_assets import find_repo_root
from aoi360_pipeline.runtime_environment import TorchRuntimeSummary, inspect_torch_runtime


DEFAULT_TEXT_PROMPT = "person. face. bottle. screen. product."
DEFAULT_OUTPUT_ROOT = Path("data") / "exports" / "benchmarks"


@dataclass(frozen=True)
class BenchmarkDataset:
    video_id: str
    original_frames_dir: Path
    prepared_frames_dir: Path
    frame_count: int
    temp_dir_to_cleanup: Path | None = None


def discover_frames_directories(
    *,
    repo_root: str | Path | None = None,
    frames_dirs: list[str] | None = None,
) -> list[Path]:
    """Resolve the frame directories to benchmark."""

    if frames_dirs:
        resolved_directories = [Path(value).resolve() for value in frames_dirs]
    else:
        root = find_repo_root(repo_root)
        frames_root = root / "data" / "frames"
        if not frames_root.exists():
            raise FileNotFoundError(f"Frames root not found: {frames_root}")
        resolved_directories = sorted(path for path in frames_root.iterdir() if path.is_dir())

    if not resolved_directories:
        raise RuntimeError("No frame directories were found to benchmark.")

    return resolved_directories


def select_frame_paths(
    frames_dir: str | Path,
    *,
    sample_every_n_frames: int = 1,
    limit_frames: int | None = None,
) -> list[Path]:
    """Pick a deterministic subset of extracted frames for benchmarking."""

    frames_dir = Path(frames_dir)
    frame_paths = sorted([*frames_dir.glob("*.jpg"), *frames_dir.glob("*.jpeg"), *frames_dir.glob("*.png")])
    if not frame_paths:
        raise RuntimeError(f"No extracted frames were found in: {frames_dir}")

    stride = max(1, int(sample_every_n_frames))
    selected_paths = frame_paths[::stride]

    if limit_frames is not None and limit_frames > 0 and len(selected_paths) > limit_frames:
        if limit_frames == 1:
            selected_paths = [selected_paths[0]]
        else:
            max_index = len(selected_paths) - 1
            sampled_indices = [
                round(position * max_index / (limit_frames - 1))
                for position in range(limit_frames)
            ]
            deduplicated_indices: list[int] = []
            seen_indices: set[int] = set()
            for index in sampled_indices:
                if index in seen_indices:
                    continue
                seen_indices.add(index)
                deduplicated_indices.append(index)

            selected_paths = [selected_paths[index] for index in deduplicated_indices]

    if not selected_paths:
        raise RuntimeError(
            f"The selected subset is empty for '{frames_dir}'. Check --sample-every-n-frames and --limit-frames."
        )

    return selected_paths


def prepare_benchmark_dataset(
    frames_dir: str | Path,
    *,
    sample_every_n_frames: int = 1,
    limit_frames: int | None = None,
) -> BenchmarkDataset:
    """Materialize a benchmark dataset, copying only when a subset is requested."""

    original_frames_dir = Path(frames_dir).resolve()
    selected_paths = select_frame_paths(
        original_frames_dir,
        sample_every_n_frames=sample_every_n_frames,
        limit_frames=limit_frames,
    )

    all_frame_paths = sorted([*original_frames_dir.glob("*.jpg"), *original_frames_dir.glob("*.jpeg"), *original_frames_dir.glob("*.png")])
    needs_subset_directory = len(selected_paths) != len(all_frame_paths)

    if not needs_subset_directory:
        return BenchmarkDataset(
            video_id=original_frames_dir.name,
            original_frames_dir=original_frames_dir,
            prepared_frames_dir=original_frames_dir,
            frame_count=len(selected_paths),
            temp_dir_to_cleanup=None,
        )

    temp_dir = Path(tempfile.mkdtemp(prefix=f"aoi360_benchmark_{original_frames_dir.name}_"))
    for frame_path in selected_paths:
        shutil.copy2(frame_path, temp_dir / frame_path.name)

    return BenchmarkDataset(
        video_id=original_frames_dir.name,
        original_frames_dir=original_frames_dir,
        prepared_frames_dir=temp_dir,
        frame_count=len(selected_paths),
        temp_dir_to_cleanup=temp_dir,
    )


def cleanup_benchmark_dataset(dataset: BenchmarkDataset) -> None:
    """Remove any temporary subset directory created for the benchmark."""

    if dataset.temp_dir_to_cleanup is not None and dataset.temp_dir_to_cleanup.exists():
        shutil.rmtree(dataset.temp_dir_to_cleanup, ignore_errors=True)


def _build_runtime_columns(runtime_summary: TorchRuntimeSummary) -> dict[str, object]:
    runtime_columns = asdict(runtime_summary)
    runtime_columns["runtime_label"] = runtime_summary.short_label
    return runtime_columns


def _announce_benchmark_step(message: str) -> None:
    print()
    separator = "=" * 96
    print(f"[benchmark_detectors] {separator}")
    print(f"[benchmark_detectors] {message}")
    print(f"[benchmark_detectors] {separator}")
    print()


def run_detector_benchmark(
    *,
    frames_dirs: list[str] | None = None,
    detectors: list[str] | None = None,
    output_dir: str | Path | None = None,
    text_prompt: str = DEFAULT_TEXT_PROMPT,
    repeats: int = 1,
    warmup_runs: int = 0,
    sample_every_n_frames: int = 1,
    limit_frames: int | None = None,
    box_threshold: float = 0.35,
    text_threshold: float = 0.25,
    batch_size: int = 0,
    inference_max_width: int | None = 1920,
    inference_max_height: int | None = 960,
    preload_workers: int = 0,
    precision: str = "auto",
    grounding_dino_model_id: str | None = None,
    owlv2_model_id: str | None = None,
    yolo_world_model_id: str | None = None,
) -> dict[str, Path]:
    """Run detector timing experiments and save raw + aggregated reports."""

    if repeats <= 0:
        raise ValueError("repeats must be greater than zero")
    if warmup_runs < 0:
        raise ValueError("warmup_runs must be zero or greater")

    repo_root = find_repo_root()
    resolved_output_dir = (Path(output_dir) if output_dir is not None else repo_root / DEFAULT_OUTPUT_ROOT).resolve()
    resolved_output_dir.mkdir(parents=True, exist_ok=True)

    timestamp_label = pd.Timestamp.now().strftime("%Y%m%d_%H%M%S")
    run_output_dir = resolved_output_dir / timestamp_label
    run_output_dir.mkdir(parents=True, exist_ok=True)

    detector_keys = [normalize_detector_name(detector) for detector in (detectors or list(SUPPORTED_DETECTORS))]
    runtime_summary = inspect_torch_runtime()
    runtime_columns = _build_runtime_columns(runtime_summary)

    prepared_datasets = [
        prepare_benchmark_dataset(
            frames_dir,
            sample_every_n_frames=sample_every_n_frames,
            limit_frames=limit_frames,
        )
        for frames_dir in discover_frames_directories(repo_root=repo_root, frames_dirs=frames_dirs)
    ]

    raw_records: list[dict[str, object]] = []
    model_id_overrides = {
        "grounding_dino": grounding_dino_model_id,
        "owlv2": owlv2_model_id,
        "yolo_world": yolo_world_model_id,
    }

    try:
        for dataset in prepared_datasets:
            for detector_key in detector_keys:
                detector_name = detector_display_name(detector_key)
                model_id = model_id_overrides.get(detector_key) or resolve_default_model_id(detector_key)

                for warmup_index in range(warmup_runs):
                    warmup_output_path = run_output_dir / f"warmup_{dataset.video_id}_{detector_key}_{warmup_index + 1}.csv"
                    _announce_benchmark_step(
                        "Starting warm-up "
                        f"{warmup_index + 1}/{warmup_runs} for video='{dataset.video_id}', "
                        f"detector='{detector_name}', model='{model_id}', frames={dataset.frame_count}."
                    )
                    try:
                        detect_frames_with_backend(
                            detector=detector_key,
                            frames_dir=dataset.prepared_frames_dir,
                            output_csv=warmup_output_path,
                            text_prompt=text_prompt,
                            box_threshold=box_threshold,
                            text_threshold=text_threshold,
                            model_id=model_id,
                            batch_size=batch_size,
                            inference_max_width=inference_max_width,
                            inference_max_height=inference_max_height,
                            preload_workers=preload_workers,
                            precision=precision,
                        )
                    finally:
                        if warmup_output_path.exists():
                            warmup_output_path.unlink()

                for repeat_index in range(repeats):
                    run_output_path = run_output_dir / f"run_{dataset.video_id}_{detector_key}_{repeat_index + 1}.csv"
                    _announce_benchmark_step(
                        "Starting measured run "
                        f"{repeat_index + 1}/{repeats} for video='{dataset.video_id}', "
                        f"detector='{detector_name}', model='{model_id}', frames={dataset.frame_count}."
                    )
                    start_time = perf_counter()
                    succeeded = False
                    error_message = ""
                    detections_count = 0

                    try:
                        detections = detect_frames_with_backend(
                            detector=detector_key,
                            frames_dir=dataset.prepared_frames_dir,
                            output_csv=run_output_path,
                            text_prompt=text_prompt,
                            box_threshold=box_threshold,
                            text_threshold=text_threshold,
                            model_id=model_id,
                            batch_size=batch_size,
                            inference_max_width=inference_max_width,
                            inference_max_height=inference_max_height,
                            preload_workers=preload_workers,
                            precision=precision,
                        )
                        detections_count = int(len(detections))
                        succeeded = True
                    except Exception as exception:  # pragma: no cover - depends on local ML stack
                        error_message = str(exception)
                    finally:
                        duration_seconds = perf_counter() - start_time
                        if run_output_path.exists():
                            run_output_path.unlink()

                    raw_records.append(
                        {
                            "video_id": dataset.video_id,
                            "original_frames_dir": str(dataset.original_frames_dir),
                            "prepared_frames_dir": str(dataset.prepared_frames_dir),
                            "frame_count": dataset.frame_count,
                            "detector": detector_key,
                            "detector_name": detector_name,
                            "model_id": model_id,
                            "repeat_index": repeat_index + 1,
                            "duration_seconds": duration_seconds,
                            "frames_per_second": (dataset.frame_count / duration_seconds) if duration_seconds > 0 else 0.0,
                            "milliseconds_per_frame": (duration_seconds * 1000.0 / dataset.frame_count),
                            "detections_count": detections_count,
                            "detections_per_frame": (detections_count / dataset.frame_count),
                            "success": succeeded,
                            "error_message": error_message,
                            "text_prompt": text_prompt,
                            "box_threshold": box_threshold,
                            "text_threshold": text_threshold,
                            "batch_size": batch_size,
                            "inference_max_width": inference_max_width,
                            "inference_max_height": inference_max_height,
                            "preload_workers": preload_workers,
                            "precision": precision,
                            **runtime_columns,
                        }
                    )
    finally:
        for dataset in prepared_datasets:
            cleanup_benchmark_dataset(dataset)

    raw_results = pd.DataFrame(raw_records)
    raw_results_path = run_output_dir / "detector_benchmark_raw_runs.csv"
    raw_results.to_csv(raw_results_path, index=False)

    successful_runs = raw_results[raw_results["success"] == True].copy()
    if successful_runs.empty:
        summary_results = pd.DataFrame(
            columns=[
                "video_id",
                "detector",
                "detector_name",
                "model_id",
                "run_count",
                "frame_count",
                "duration_seconds_mean",
                "duration_seconds_median",
                "duration_seconds_min",
                "duration_seconds_max",
                "duration_seconds_std",
                "frames_per_second_mean",
                "milliseconds_per_frame_mean",
                "detections_count_mean",
                "detections_per_frame_mean",
            ]
        )
    else:
        summary_results = (
            successful_runs
            .groupby(["video_id", "detector", "detector_name", "model_id", "frame_count"], as_index=False)
            .agg(
                run_count=("repeat_index", "count"),
                duration_seconds_mean=("duration_seconds", "mean"),
                duration_seconds_median=("duration_seconds", "median"),
                duration_seconds_min=("duration_seconds", "min"),
                duration_seconds_max=("duration_seconds", "max"),
                duration_seconds_std=("duration_seconds", "std"),
                frames_per_second_mean=("frames_per_second", "mean"),
                milliseconds_per_frame_mean=("milliseconds_per_frame", "mean"),
                detections_count_mean=("detections_count", "mean"),
                detections_per_frame_mean=("detections_per_frame", "mean"),
            )
        )

    summary_results_path = run_output_dir / "detector_benchmark_summary.csv"
    summary_results.to_csv(summary_results_path, index=False)

    metadata = {
        "output_dir": str(run_output_dir),
        "runtime": runtime_columns,
        "parameters": {
            "frames_dirs": frames_dirs,
            "detectors": detector_keys,
            "text_prompt": text_prompt,
            "repeats": repeats,
            "warmup_runs": warmup_runs,
            "sample_every_n_frames": sample_every_n_frames,
            "limit_frames": limit_frames,
            "box_threshold": box_threshold,
            "text_threshold": text_threshold,
            "batch_size": batch_size,
            "inference_max_width": inference_max_width,
            "inference_max_height": inference_max_height,
            "preload_workers": preload_workers,
            "precision": precision,
            "grounding_dino_model_id": grounding_dino_model_id,
            "owlv2_model_id": owlv2_model_id,
            "yolo_world_model_id": yolo_world_model_id,
        },
    }
    metadata_path = run_output_dir / "detector_benchmark_metadata.json"
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    return {
        "output_dir": run_output_dir,
        "raw_results_path": raw_results_path,
        "summary_results_path": summary_results_path,
        "metadata_path": metadata_path,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Benchmark supported open-vocabulary detectors over extracted 360-video frames.",
    )
    parser.add_argument(
        "--frames-dir",
        dest="frames_dirs",
        action="append",
        help=(
            "Frame directory to benchmark. Repeat the option to compare multiple 360 videos. "
            "If omitted, every subdirectory under data/frames is used."
        ),
    )
    parser.add_argument(
        "--detector",
        dest="detectors",
        action="append",
        choices=sorted(SUPPORTED_DETECTORS),
        help="Detector backend to benchmark. Repeat to include multiple detectors. Defaults to every supported detector.",
    )
    parser.add_argument("--output-dir", help="Directory where benchmark reports are written.")
    parser.add_argument("--text-prompt", default=DEFAULT_TEXT_PROMPT)
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument(
        "--warmup-runs",
        type=int,
        default=0,
        help="Number of warm-up runs per detector/video pair before timings are recorded.",
    )
    parser.add_argument(
        "--sample-every-n-frames",
        type=int,
        default=1,
        help="Use only every Nth extracted frame to shorten the benchmark while keeping a deterministic sample.",
    )
    parser.add_argument(
        "--limit-frames",
        type=int,
        default=None,
        help="Optional hard cap on the number of extracted frames used per video.",
    )
    parser.add_argument("--box-threshold", type=float, default=0.35)
    parser.add_argument("--text-threshold", type=float, default=0.25)
    parser.add_argument("--batch-size", type=int, default=0)
    parser.add_argument("--inference-max-width", type=int, default=1920)
    parser.add_argument("--inference-max-height", type=int, default=960)
    parser.add_argument("--preload-workers", type=int, default=0)
    parser.add_argument("--precision", choices=["auto", "fp16", "fp32"], default="auto")
    parser.add_argument(
        "--grounding-dino-model-id",
        default=None,
        help="Optional override for the Grounding DINO pretrained model id.",
    )
    parser.add_argument(
        "--owlv2-model-id",
        default=None,
        help="Optional override for the OWLv2 pretrained model id.",
    )
    parser.add_argument(
        "--yolo-world-model-id",
        default=None,
        help="Optional override for the YOLO-World pretrained model id.",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    result_paths = run_detector_benchmark(
        frames_dirs=args.frames_dirs,
        detectors=args.detectors,
        output_dir=args.output_dir,
        text_prompt=args.text_prompt,
        repeats=args.repeats,
        warmup_runs=args.warmup_runs,
        sample_every_n_frames=args.sample_every_n_frames,
        limit_frames=args.limit_frames,
        box_threshold=args.box_threshold,
        text_threshold=args.text_threshold,
        batch_size=args.batch_size,
        inference_max_width=args.inference_max_width,
        inference_max_height=args.inference_max_height,
        preload_workers=args.preload_workers,
        precision=args.precision,
        grounding_dino_model_id=args.grounding_dino_model_id,
        owlv2_model_id=args.owlv2_model_id,
        yolo_world_model_id=args.yolo_world_model_id,
    )

    print(f"[benchmark_detectors] Raw runs: {result_paths['raw_results_path']}")
    print(f"[benchmark_detectors] Summary: {result_paths['summary_results_path']}")
    print(f"[benchmark_detectors] Metadata: {result_paths['metadata_path']}")


if __name__ == "__main__":
    main()
