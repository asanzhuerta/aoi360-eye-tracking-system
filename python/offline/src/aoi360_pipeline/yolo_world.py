from __future__ import annotations

"""Run YOLO-World over extracted frames and normalize the detections output."""

import argparse
import os
import re
from collections.abc import Callable
from pathlib import Path

import pandas as pd

from aoi360_pipeline.detection_contract import DETECTION_COLUMNS, get_frame_index
from aoi360_pipeline.runtime_environment import inspect_torch_runtime

DEFAULT_MODEL_ID = "yolov8s-worldv2.pt"
ProgressCallback = Callable[[int, int, str], None]
LogCallback = Callable[[str], None]


def _get_ultralytics_cache_root() -> Path:
    """Keep YOLO-World caches inside the repo instead of polluting the root."""

    return Path(__file__).resolve().parents[4] / ".cache" / "ultralytics"


def _lazy_import_yolo_world_stack():
    # Delay optional detector imports so the rest of the package stays usable
    # even when this backend has not been installed yet.
    config_root = _get_ultralytics_cache_root()
    config_root.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("YOLO_CONFIG_DIR", str(config_root))

    try:
        import torch
        from tqdm import tqdm
        from ultralytics import YOLOWorld
    except ImportError as exc:  # pragma: no cover - depends on local environment
        raise RuntimeError(
            "YOLO-World dependencies are missing. Install the offline pipeline dependencies first."
        ) from exc

    return torch, tqdm, YOLOWorld


def _resolve_model_reference(model_id: str) -> str:
    # Ultralytics downloads pretrained weights into the current working
    # directory when given only a bare filename. Route those files into the
    # repo-local cache so experiments do not dirty the workspace root.
    model_path = Path(model_id)
    if model_path.is_absolute() or model_path.exists() or model_path.parent != Path("."):
        return str(model_path)

    cached_model_path = _get_ultralytics_cache_root() / "weights" / model_path.name
    cached_model_path.parent.mkdir(parents=True, exist_ok=True)
    return str(cached_model_path)


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


def _parse_open_vocabulary_classes(text_prompt: str) -> list[str]:
    # Grounding DINO works well with dot-separated prompts. YOLO-World expects
    # a list of class strings, so normalize the existing prompt contract here.
    prompt_tokens = re.split(r"[,\n]+|\.(?:\s|$)", text_prompt)
    normalized_tokens: list[str] = []
    seen_tokens: set[str] = set()

    for token in prompt_tokens:
        normalized_token = token.strip()
        if not normalized_token:
            continue
        lowered_token = normalized_token.lower()
        if lowered_token in seen_tokens:
            continue
        seen_tokens.add(lowered_token)
        normalized_tokens.append(normalized_token)

    if not normalized_tokens:
        raise ValueError("text_prompt must contain at least one non-empty class prompt for YOLO-World.")

    return normalized_tokens


def _resolve_prediction_size(
    inference_max_width: int | None,
    inference_max_height: int | None,
) -> tuple[int, int] | int:
    has_width = bool(inference_max_width and inference_max_width > 0)
    has_height = bool(inference_max_height and inference_max_height > 0)

    if has_width and has_height:
        return (int(inference_max_height), int(inference_max_width))
    if has_width:
        return int(inference_max_width)
    if has_height:
        return int(inference_max_height)
    return 960


def _collect_detection_rows(
    *,
    model,
    frame_paths: list[Path],
    total_frames: int,
    effective_batch_size: int,
    prediction_size: tuple[int, int] | int,
    box_threshold: float,
    device_argument,
    use_half_precision: bool,
    model_id: str,
    text_prompt: str,
    progress_callback: ProgressCallback | None,
    tqdm_module,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    batch_starts = range(0, total_frames, effective_batch_size)
    if progress_callback is None:
        batch_starts = tqdm_module(batch_starts, desc="Running YOLO-World")
    processed_index = 0

    for batch_start in batch_starts:
        batch_paths = frame_paths[batch_start: batch_start + effective_batch_size]
        batch_sources = [str(frame_path) for frame_path in batch_paths]
        batch_results = model.predict(
            source=batch_sources,
            conf=box_threshold,
            imgsz=prediction_size,
            device=device_argument,
            half=use_half_precision,
            verbose=False,
            stream=False,
            batch=len(batch_sources),
        )

        for frame_path, result in zip(batch_paths, batch_results):
            boxes = result.boxes
            detection_count = 0

            if boxes is not None and len(boxes) > 0:
                xyxy_boxes = boxes.xyxy.cpu().tolist()
                confidence_scores = boxes.conf.cpu().tolist()
                class_indices = boxes.cls.int().cpu().tolist()

                for detection_index, (box, score, class_index) in enumerate(
                    zip(xyxy_boxes, confidence_scores, class_indices)
                ):
                    x_min, y_min, x_max, y_max = box
                    label = str(result.names[int(class_index)])
                    rows.append(
                        {
                            "frame_index": get_frame_index(frame_path),
                            "frame_file": frame_path.name,
                            "detection_index": detection_index,
                            "label": label,
                            "confidence": float(score),
                            "x_min": float(x_min),
                            "y_min": float(y_min),
                            "x_max": float(x_max),
                            "y_max": float(y_max),
                            "source": "yolo_world",
                            "model_id": model_id,
                            "prompt": text_prompt,
                        }
                    )
                    detection_count += 1

            processed_index += 1
            _emit_progress(
                progress_callback,
                processed_index,
                total_frames,
                f"Processed {frame_path.name} with {detection_count} detections.",
            )

    return rows


def detect_frames(
    frames_dir: str | Path,
    output_csv: str | Path,
    text_prompt: str,
    box_threshold: float = 0.35,
    text_threshold: float = 0.25,
    model_id: str = DEFAULT_MODEL_ID,
    batch_size: int = 0,
    inference_max_width: int | None = None,
    inference_max_height: int | None = None,
    preload_workers: int = 0,
    precision: str = "auto",
    progress_callback: ProgressCallback | None = None,
    log_callback: LogCallback | None = None,
) -> pd.DataFrame:
    # Keep the public signature aligned with the Grounding DINO backend so the
    # rebuild pipeline and GUI can swap detectors without branching logic.
    torch, tqdm, YOLOWorld = _lazy_import_yolo_world_stack()

    frames_dir = Path(frames_dir)
    output_csv = Path(output_csv)

    if not frames_dir.exists():
        raise FileNotFoundError(f"Frames directory not found: {frames_dir}")

    if not 0.0 <= box_threshold <= 1.0:
        raise ValueError("box_threshold must be between 0.0 and 1.0")

    if not 0.0 <= text_threshold <= 1.0:
        raise ValueError("text_threshold must be between 0.0 and 1.0")

    output_csv.parent.mkdir(parents=True, exist_ok=True)

    runtime_summary = inspect_torch_runtime(torch)
    class_prompts = _parse_open_vocabulary_classes(text_prompt)
    effective_batch_size = batch_size if batch_size > 0 else runtime_summary.recommended_batch_size
    resolved_precision = runtime_summary.recommended_precision if precision == "auto" else precision.lower()
    if resolved_precision not in {"fp16", "fp32"}:
        raise ValueError("precision must be one of: auto, fp16, fp32")
    if not runtime_summary.cuda_available:
        resolved_precision = "fp32"

    prediction_size = _resolve_prediction_size(
        inference_max_width=inference_max_width,
        inference_max_height=inference_max_height,
    )
    device_argument = 0 if runtime_summary.cuda_available else "cpu"
    resolved_model_reference = _resolve_model_reference(model_id)

    _emit_log(log_callback, f"[detect_yolo_world] Runtime: {runtime_summary.short_label}")
    _emit_log(log_callback, f"[detect_yolo_world] Using device: {runtime_summary.default_device}")
    _emit_log(log_callback, f"[detect_yolo_world] Model: {model_id}")
    _emit_log(log_callback, f"[detect_yolo_world] Cached model path: {resolved_model_reference}")
    _emit_log(log_callback, f"[detect_yolo_world] Batch size: {effective_batch_size}")
    _emit_log(log_callback, f"[detect_yolo_world] Precision: {resolved_precision}")
    _emit_log(log_callback, f"[detect_yolo_world] Prompt classes: {', '.join(class_prompts)}")
    if text_threshold != 0.25:
        _emit_log(
            log_callback,
            "[detect_yolo_world] Note: text_threshold is not used by YOLO-World and is ignored in this backend.",
        )

    frame_paths = sorted([*frames_dir.glob("*.jpg"), *frames_dir.glob("*.jpeg"), *frames_dir.glob("*.png")])
    if not frame_paths:
        raise RuntimeError(f"No images found in: {frames_dir}")

    total_frames = len(frame_paths)
    _emit_progress(progress_callback, 0, total_frames, "Loading YOLO-World and preparing detections.")
    def _build_model():
        built_model = YOLOWorld(resolved_model_reference)
        built_model.set_classes(class_prompts)
        return built_model

    rows: list[dict[str, object]]
    try:
        rows = _collect_detection_rows(
            model=_build_model(),
            frame_paths=frame_paths,
            total_frames=total_frames,
            effective_batch_size=effective_batch_size,
            prediction_size=prediction_size,
            box_threshold=box_threshold,
            device_argument=device_argument,
            use_half_precision=runtime_summary.cuda_available and resolved_precision == "fp16",
            model_id=model_id,
            text_prompt=text_prompt,
            progress_callback=progress_callback,
            tqdm_module=tqdm,
        )
    except Exception as exception:
        should_retry_with_safe_cuda = (
            runtime_summary.cuda_available and
            device_argument != "cpu" and
            (effective_batch_size > 1 or resolved_precision == "fp16")
        )
        if not should_retry_with_safe_cuda:
            raise

        _emit_log(
            log_callback,
            (
                "[detect_yolo_world] CUDA inference failed with the automatic settings. "
                "Retrying with a safer configuration: batch_size=1, precision=fp32."
            ),
        )
        _emit_log(log_callback, f"[detect_yolo_world] Original error: {type(exception).__name__}: {exception}")

        if hasattr(torch.cuda, "empty_cache"):
            torch.cuda.empty_cache()

        _emit_progress(progress_callback, 0, total_frames, "Retrying YOLO-World with safer CUDA settings.")
        rows = _collect_detection_rows(
            model=_build_model(),
            frame_paths=frame_paths,
            total_frames=total_frames,
            effective_batch_size=1,
            prediction_size=prediction_size,
            box_threshold=box_threshold,
            device_argument=device_argument,
            use_half_precision=False,
            model_id=model_id,
            text_prompt=text_prompt,
            progress_callback=progress_callback,
            tqdm_module=tqdm,
        )

    detections = pd.DataFrame(rows, columns=DETECTION_COLUMNS)
    detections.to_csv(output_csv, index=False)

    _emit_log(log_callback, f"[detect_yolo_world] Frames processed: {len(frame_paths)}")
    _emit_log(log_callback, f"[detect_yolo_world] Detections exported: {len(detections)}")
    _emit_log(log_callback, f"[detect_yolo_world] CSV written to: {output_csv}")
    return detections


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run YOLO-World over extracted 360 frames and export bounding boxes to CSV."
    )
    parser.add_argument(
        "--frames-dir",
        default="data/frames/video_360",
        help="Directory containing the extracted frames.",
    )
    parser.add_argument(
        "--output-csv",
        default="data/interim/detections/video_360_yolo_world_boxes.csv",
        help="CSV path where detections will be written.",
    )
    parser.add_argument(
        "--text-prompt",
        default="person. face. bottle. screen. product.",
        help="YOLO-World class prompt list. Dot-separated prompts are converted into detector classes automatically.",
    )
    parser.add_argument("--box-threshold", type=float, default=0.35)
    parser.add_argument("--text-threshold", type=float, default=0.25)
    parser.add_argument("--model-id", default=DEFAULT_MODEL_ID)
    parser.add_argument(
        "--batch-size",
        type=int,
        default=0,
        help="How many frames to run per inference batch. Use 0 to choose an automatic default.",
    )
    parser.add_argument(
        "--inference-max-width",
        type=int,
        default=None,
        help="Optional maximum inference width. YOLO-World resizes internally and reports boxes in original-image coordinates.",
    )
    parser.add_argument(
        "--inference-max-height",
        type=int,
        default=None,
        help="Optional maximum inference height. YOLO-World resizes internally and reports boxes in original-image coordinates.",
    )
    parser.add_argument(
        "--preload-workers",
        type=int,
        default=0,
        help="Retained for parity with other backends. YOLO-World manages loading internally, so this value is not used.",
    )
    parser.add_argument(
        "--precision",
        default="auto",
        choices=["auto", "fp16", "fp32"],
        help="Inference precision. 'auto' uses fp16 on CUDA and fp32 on CPU.",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    detect_frames(
        frames_dir=args.frames_dir,
        output_csv=args.output_csv,
        text_prompt=args.text_prompt,
        box_threshold=args.box_threshold,
        text_threshold=args.text_threshold,
        model_id=args.model_id,
        batch_size=args.batch_size,
        inference_max_width=args.inference_max_width,
        inference_max_height=args.inference_max_height,
        preload_workers=args.preload_workers,
        precision=args.precision,
    )


if __name__ == "__main__":
    main()
