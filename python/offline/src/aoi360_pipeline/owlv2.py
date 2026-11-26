from __future__ import annotations

"""Run OWLv2 over extracted frames and normalize the detections output."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd

from aoi360_pipeline.cache_roots import (
    configure_huggingface_cache_environment,
)
from aoi360_pipeline.callbacks import (
    LogCallback,
    ProgressCallback,
    emit_log,
    emit_progress,
)
from aoi360_pipeline.detection_contract import (
    DETECTION_COLUMNS,
    list_frame_paths,
)
from aoi360_pipeline.hf_backend import (
    PretrainedAssetCache,
    prepare_frame,
)
from aoi360_pipeline.prompts import split_class_prompt
from aoi360_pipeline.runtime_environment import inspect_torch_runtime

DEFAULT_MODEL_ID = "google/owlv2-base-patch16-ensemble"
_ASSETS = PretrainedAssetCache(display_name="OWLv2", log_prefix="[detect_owlv2]")


def _lazy_import_owlv2_stack():
    configure_huggingface_cache_environment()
    try:
        import torch
        from PIL import Image
        from tqdm import tqdm
        from transformers import Owlv2ForObjectDetection, Owlv2Processor
    except ImportError as exc:  # pragma: no cover - depends on local environment
        raise RuntimeError(
            "OWLv2 dependencies are missing. Install the offline pipeline dependencies first."
        ) from exc

    return torch, Image, tqdm, Owlv2ForObjectDetection, Owlv2Processor


def _parse_open_vocabulary_labels(text_prompt: str) -> tuple[list[str], dict[str, str]]:
    """OWLv2 scores captions better than bare class names: "person" -> "a photo of a person"."""
    query_labels: list[str] = []
    label_map: dict[str, str] = {}
    for class_name in split_class_prompt(text_prompt, "OWLv2"):
        query_label = class_name
        if not class_name.lower().startswith(("a ", "an ", "the ")):
            query_label = f"a photo of a {class_name}"
        query_labels.append(query_label)
        label_map[query_label] = class_name
    return query_labels, label_map


def prefetch_model_assets(
    model_id: str = DEFAULT_MODEL_ID,
    *,
    precision: str = "auto",
    log_callback: LogCallback | None = None,
) -> dict[str, str]:
    torch, _, _, Owlv2ForObjectDetection, Owlv2Processor = _lazy_import_owlv2_stack()
    runtime_summary = inspect_torch_runtime(torch)
    device = runtime_summary.default_device
    resolved_precision = runtime_summary.recommended_precision if precision == "auto" else precision.lower()
    if resolved_precision not in {"fp16", "fp32"}:
        raise ValueError("precision must be one of: auto, fp16, fp32")
    if device != "cuda":
        resolved_precision = "fp32"

    cache_root = configure_huggingface_cache_environment()
    emit_log(log_callback, f"[detect_owlv2] Prefetching assets into local cache: {cache_root}")

    model_kwargs = {}
    if device == "cuda" and resolved_precision == "fp16":
        model_kwargs["torch_dtype"] = torch.float16

    _ASSETS.get_processor(
        processor_factory=Owlv2Processor,
        model_id=model_id,
        log_callback=log_callback,
    )
    _ASSETS.get_model(
        model_factory=Owlv2ForObjectDetection,
        model_id=model_id,
        device=device,
        precision=resolved_precision,
        model_kwargs=model_kwargs,
        log_callback=log_callback,
    )

    return {
        "model_id": model_id,
        "cache_root": str(cache_root),
        "device": device,
        "precision": resolved_precision,
    }


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
    torch, Image, tqdm, Owlv2ForObjectDetection, Owlv2Processor = _lazy_import_owlv2_stack()

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
    cache_root = configure_huggingface_cache_environment()
    device = runtime_summary.default_device
    effective_batch_size = batch_size if batch_size > 0 else runtime_summary.recommended_batch_size
    effective_preload_workers = (
        preload_workers if preload_workers > 0 else min(runtime_summary.recommended_preload_workers, effective_batch_size)
    )
    resolved_precision = runtime_summary.recommended_precision if precision == "auto" else precision.lower()
    if resolved_precision not in {"fp16", "fp32"}:
        raise ValueError("precision must be one of: auto, fp16, fp32")
    if device != "cuda":
        resolved_precision = "fp32"

    query_labels, label_map = _parse_open_vocabulary_labels(text_prompt)

    emit_log(log_callback, f"[detect_owlv2] Runtime: {runtime_summary.short_label}")
    emit_log(log_callback, f"[detect_owlv2] Using device: {device}")
    emit_log(log_callback, f"[detect_owlv2] Model: {model_id}")
    emit_log(log_callback, f"[detect_owlv2] Local Hugging Face cache: {cache_root}")
    emit_log(log_callback, f"[detect_owlv2] Batch size: {effective_batch_size}")
    emit_log(log_callback, f"[detect_owlv2] Precision: {resolved_precision}")
    emit_log(log_callback, f"[detect_owlv2] Prompt classes: {', '.join(query_labels)}")
    if text_threshold != 0.25:
        emit_log(
            log_callback,
            "[detect_owlv2] Note: text_threshold is not used by OWLv2 and is ignored in this backend.",
        )

    model_kwargs = {}
    if device == "cuda" and resolved_precision == "fp16":
        model_kwargs["torch_dtype"] = torch.float16

    processor = _ASSETS.get_processor(
        processor_factory=Owlv2Processor,
        model_id=model_id,
        log_callback=log_callback,
    )
    model = _ASSETS.get_model(
        model_factory=Owlv2ForObjectDetection,
        model_id=model_id,
        device=device,
        precision=resolved_precision,
        model_kwargs=model_kwargs,
        log_callback=log_callback,
    )

    frame_paths = list_frame_paths(frames_dir)
    if not frame_paths:
        raise RuntimeError(f"No images found in: {frames_dir}")

    rows: list[dict[str, object]] = []
    total_frames = len(frame_paths)
    emit_progress(progress_callback, 0, total_frames, "Loading OWLv2 and preparing detections.")

    image_loader = lambda path: prepare_frame(
        frame_path=path,
        image_module=Image,
        inference_max_width=inference_max_width,
        inference_max_height=inference_max_height,
    )

    processed_index = 0
    batch_starts = range(0, len(frame_paths), effective_batch_size)
    if progress_callback is None:
        batch_starts = tqdm(batch_starts, desc="Running OWLv2")

    for batch_start in batch_starts:
        batch_paths = frame_paths[batch_start: batch_start + effective_batch_size]
        if effective_preload_workers > 1 and len(batch_paths) > 1:
            with ThreadPoolExecutor(max_workers=min(effective_preload_workers, len(batch_paths))) as executor:
                prepared_batch = list(executor.map(image_loader, batch_paths))
        else:
            prepared_batch = [image_loader(frame_path) for frame_path in batch_paths]

        input_images = [prepared_frame.image for prepared_frame in prepared_batch]
        target_sizes = [prepared_frame.target_size for prepared_frame in prepared_batch]
        batch_text_labels = [query_labels] * len(prepared_batch)
        inputs = processor(text=batch_text_labels, images=input_images, return_tensors="pt").to(device)

        with torch.inference_mode():
            if device == "cuda" and resolved_precision == "fp16":
                with torch.autocast(device_type="cuda", dtype=torch.float16):
                    outputs = model(**inputs)
            else:
                outputs = model(**inputs)

        results_batch = processor.post_process_grounded_object_detection(
            outputs=outputs,
            target_sizes=target_sizes,
            threshold=box_threshold,
            text_labels=batch_text_labels,
        )

        for prepared_frame, results in zip(prepared_batch, results_batch):
            boxes = results["boxes"].cpu().tolist()
            scores = results["scores"].cpu().tolist()
            raw_labels = [str(label) for label in results["text_labels"]]

            for detection_index, (box, score, raw_label) in enumerate(zip(boxes, scores, raw_labels)):
                x_min, y_min, x_max, y_max = box
                label = label_map.get(raw_label, raw_label)
                rows.append(
                    {
                        "frame_index": prepared_frame.frame_index,
                        "frame_file": prepared_frame.frame_path.name,
                        "detection_index": detection_index,
                        "label": label,
                        "confidence": float(score),
                        "x_min": float(x_min),
                        "y_min": float(y_min),
                        "x_max": float(x_max),
                        "y_max": float(y_max),
                        "source": "owlv2",
                        "model_id": model_id,
                        "prompt": text_prompt,
                    }
                )

            processed_index += 1
            emit_progress(
                progress_callback,
                processed_index,
                total_frames,
                f"Processed {prepared_frame.frame_path.name} with {len(boxes)} detections.",
            )

    detections = pd.DataFrame(rows, columns=DETECTION_COLUMNS)
    detections.to_csv(output_csv, index=False)

    emit_log(log_callback, f"[detect_owlv2] Frames processed: {len(frame_paths)}")
    emit_log(log_callback, f"[detect_owlv2] Detections exported: {len(detections)}")
    emit_log(log_callback, f"[detect_owlv2] CSV written to: {output_csv}")
    return detections


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run OWLv2 over extracted 360 frames and export bounding boxes to CSV."
    )
    parser.add_argument(
        "--frames-dir",
        default="data/frames/video_360",
        help="Directory containing the extracted frames.",
    )
    parser.add_argument(
        "--output-csv",
        default="data/interim/detections/video_360_owlv2_boxes.csv",
        help="CSV path where detections will be written.",
    )
    parser.add_argument(
        "--text-prompt",
        default="person. face. bottle. screen. product.",
        help="OWLv2 prompt list. Dot-separated prompts are normalized into text labels automatically.",
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
        help="Optional maximum width for inference images before boxes are rescaled back to the original frame.",
    )
    parser.add_argument(
        "--inference-max-height",
        type=int,
        default=None,
        help="Optional maximum height for inference images before boxes are rescaled back to the original frame.",
    )
    parser.add_argument(
        "--preload-workers",
        type=int,
        default=0,
        help="Threaded frame-loading worker count. Use 0 to choose an automatic default.",
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
