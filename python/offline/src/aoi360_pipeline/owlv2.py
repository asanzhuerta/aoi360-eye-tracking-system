from __future__ import annotations

"""Run OWLv2 over extracted frames and normalize the detections output."""

import argparse
import re
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from threading import RLock

import pandas as pd

from aoi360_pipeline.cache_roots import (
    configure_huggingface_cache_environment,
    iter_huggingface_cache_roots,
    resolve_huggingface_snapshot_path,
)
from aoi360_pipeline.detection_contract import DETECTION_COLUMNS, get_frame_index
from aoi360_pipeline.runtime_environment import inspect_torch_runtime

DEFAULT_MODEL_ID = "google/owlv2-base-patch16-ensemble"
ProgressCallback = Callable[[int, int, str], None]
LogCallback = Callable[[str], None]
_PROCESSOR_CACHE: dict[tuple[str], object] = {}
_MODEL_CACHE: dict[tuple[str, str, str], object] = {}
_CACHE_LOCK = RLock()


@dataclass(frozen=True)
class PreparedFrame:
    frame_path: Path
    frame_index: int
    image: object
    target_size: tuple[int, int]


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


def _load_pretrained_asset(pretrained_factory, model_id: str, *, log_callback: LogCallback | None = None, **kwargs):
    primary_cache_root = configure_huggingface_cache_environment()
    local_failures: list[str] = []
    for cache_root in iter_huggingface_cache_roots():
        snapshot_path = resolve_huggingface_snapshot_path(model_id, cache_root)
        if snapshot_path is not None:
            snapshot_kwargs = dict(kwargs)
            snapshot_kwargs["local_files_only"] = True
            try:
                asset = pretrained_factory.from_pretrained(str(snapshot_path), **snapshot_kwargs)
                _emit_log(log_callback, f"[detect_owlv2] Loaded assets from cached snapshot: {snapshot_path}")
                return asset
            except Exception as local_exception:
                local_failures.append(f"{snapshot_path} -> {local_exception}")

        local_kwargs = dict(kwargs)
        local_kwargs["cache_dir"] = str(cache_root)
        local_kwargs["local_files_only"] = True
        try:
            asset = pretrained_factory.from_pretrained(model_id, **local_kwargs)
            _emit_log(log_callback, f"[detect_owlv2] Loaded assets from local cache root: {cache_root}")
            return asset
        except Exception as local_exception:
            local_failures.append(f"{cache_root} -> {local_exception}")

    _emit_log(
        log_callback,
        (
            "[detect_owlv2] Local cache lookup failed; falling back to remote resolution. "
            f"Tried: {' | '.join(local_failures)}"
        ),
    )

    try:
        return pretrained_factory.from_pretrained(model_id, cache_dir=str(primary_cache_root), **kwargs)
    except Exception as remote_exception:
        raise RuntimeError(
            "OWLv2 could not be loaded from the local cache or from the remote Hugging Face repository. "
            "If the model was already downloaded before, check that the cache is still available."
        ) from remote_exception


def _get_cached_processor(
    *,
    processor_factory,
    model_id: str,
    log_callback: LogCallback | None,
):
    cache_key = (model_id,)
    with _CACHE_LOCK:
        cached_processor = _PROCESSOR_CACHE.get(cache_key)

    if cached_processor is not None:
        _emit_log(log_callback, f"[detect_owlv2] Reusing cached processor for: {model_id}")
        return cached_processor

    built_processor = _load_pretrained_asset(processor_factory, model_id, log_callback=log_callback)
    with _CACHE_LOCK:
        cached_processor = _PROCESSOR_CACHE.setdefault(cache_key, built_processor)
    return cached_processor


def _get_cached_model(
    *,
    model_factory,
    model_id: str,
    device: str,
    precision: str,
    model_kwargs: dict[str, object],
    log_callback: LogCallback | None,
):
    cache_key = (model_id, device, precision)
    with _CACHE_LOCK:
        cached_model = _MODEL_CACHE.get(cache_key)

    if cached_model is not None:
        cached_model.eval()
        _emit_log(log_callback, f"[detect_owlv2] Reusing cached model for: {model_id} [{device}, {precision}]")
        return cached_model

    built_model = _load_pretrained_asset(
        model_factory,
        model_id,
        log_callback=log_callback,
        **model_kwargs,
    ).to(device)
    built_model.eval()

    with _CACHE_LOCK:
        cached_model = _MODEL_CACHE.setdefault(cache_key, built_model)

    cached_model.eval()
    return cached_model


def _resolve_resampling_filter(image_module):
    try:
        return image_module.Resampling.BICUBIC
    except AttributeError:  # pragma: no cover - Pillow compatibility shim
        return image_module.BICUBIC


def _resize_for_inference(image, image_module, max_width: int | None, max_height: int | None):
    width, height = image.size
    scale = 1.0

    if max_width is not None and max_width > 0 and width > max_width:
        scale = min(scale, max_width / width)
    if max_height is not None and max_height > 0 and height > max_height:
        scale = min(scale, max_height / height)

    if scale >= 1.0:
        return image

    resized_width = max(1, int(round(width * scale)))
    resized_height = max(1, int(round(height * scale)))
    return image.resize((resized_width, resized_height), _resolve_resampling_filter(image_module))


def _prepare_frame(
    frame_path: Path,
    image_module,
    inference_max_width: int | None,
    inference_max_height: int | None,
) -> PreparedFrame:
    with image_module.open(frame_path) as image_handle:
        image = image_handle.convert("RGB")
        target_size = (image.height, image.width)
        inference_image = _resize_for_inference(
            image=image,
            image_module=image_module,
            max_width=inference_max_width,
            max_height=inference_max_height,
        )

    return PreparedFrame(
        frame_path=frame_path,
        frame_index=get_frame_index(frame_path),
        image=inference_image,
        target_size=target_size,
    )


def _parse_open_vocabulary_labels(text_prompt: str) -> tuple[list[str], dict[str, str]]:
    prompt_tokens = re.split(r"[,\n]+|\.(?:\s|$)", text_prompt)
    query_labels: list[str] = []
    label_map: dict[str, str] = {}
    seen_tokens: set[str] = set()

    for token in prompt_tokens:
        normalized_token = token.strip()
        if not normalized_token:
            continue

        lowered_token = normalized_token.lower()
        if lowered_token in seen_tokens:
            continue

        seen_tokens.add(lowered_token)
        query_label = normalized_token
        if not lowered_token.startswith(("a ", "an ", "the ")):
            query_label = f"a photo of a {normalized_token}"

        query_labels.append(query_label)
        label_map[query_label] = normalized_token

    if not query_labels:
        raise ValueError("text_prompt must contain at least one non-empty class prompt for OWLv2.")

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
    _emit_log(log_callback, f"[detect_owlv2] Prefetching assets into local cache: {cache_root}")

    model_kwargs = {}
    if device == "cuda" and resolved_precision == "fp16":
        model_kwargs["torch_dtype"] = torch.float16

    _get_cached_processor(
        processor_factory=Owlv2Processor,
        model_id=model_id,
        log_callback=log_callback,
    )
    _get_cached_model(
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

    _emit_log(log_callback, f"[detect_owlv2] Runtime: {runtime_summary.short_label}")
    _emit_log(log_callback, f"[detect_owlv2] Using device: {device}")
    _emit_log(log_callback, f"[detect_owlv2] Model: {model_id}")
    _emit_log(log_callback, f"[detect_owlv2] Local Hugging Face cache: {cache_root}")
    _emit_log(log_callback, f"[detect_owlv2] Batch size: {effective_batch_size}")
    _emit_log(log_callback, f"[detect_owlv2] Precision: {resolved_precision}")
    _emit_log(log_callback, f"[detect_owlv2] Prompt classes: {', '.join(query_labels)}")
    if text_threshold != 0.25:
        _emit_log(
            log_callback,
            "[detect_owlv2] Note: text_threshold is not used by OWLv2 and is ignored in this backend.",
        )

    model_kwargs = {}
    if device == "cuda" and resolved_precision == "fp16":
        model_kwargs["torch_dtype"] = torch.float16

    processor = _get_cached_processor(
        processor_factory=Owlv2Processor,
        model_id=model_id,
        log_callback=log_callback,
    )
    model = _get_cached_model(
        model_factory=Owlv2ForObjectDetection,
        model_id=model_id,
        device=device,
        precision=resolved_precision,
        model_kwargs=model_kwargs,
        log_callback=log_callback,
    )

    frame_paths = sorted([*frames_dir.glob("*.jpg"), *frames_dir.glob("*.jpeg"), *frames_dir.glob("*.png")])
    if not frame_paths:
        raise RuntimeError(f"No images found in: {frames_dir}")

    rows: list[dict[str, object]] = []
    total_frames = len(frame_paths)
    _emit_progress(progress_callback, 0, total_frames, "Loading OWLv2 and preparing detections.")

    image_loader = lambda path: _prepare_frame(
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
            _emit_progress(
                progress_callback,
                processed_index,
                total_frames,
                f"Processed {prepared_frame.frame_path.name} with {len(boxes)} detections.",
            )

    detections = pd.DataFrame(rows, columns=DETECTION_COLUMNS)
    detections.to_csv(output_csv, index=False)

    _emit_log(log_callback, f"[detect_owlv2] Frames processed: {len(frame_paths)}")
    _emit_log(log_callback, f"[detect_owlv2] Detections exported: {len(detections)}")
    _emit_log(log_callback, f"[detect_owlv2] CSV written to: {output_csv}")
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
