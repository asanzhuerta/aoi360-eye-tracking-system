from __future__ import annotations
"""Run Grounding DINO over extracted frames and normalize the detections output."""

import argparse
import inspect
from concurrent.futures import ThreadPoolExecutor
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from aoi360_pipeline.detection_contract import DETECTION_COLUMNS, get_frame_index
from aoi360_pipeline.runtime_environment import inspect_torch_runtime


DEFAULT_MODEL_ID = "IDEA-Research/grounding-dino-tiny"
ProgressCallback = Callable[[int, int, str], None]
LogCallback = Callable[[str], None]


@dataclass(frozen=True)
class PreparedFrame:
    """Carry one frame through the batched inference pipeline."""

    frame_path: Path
    frame_index: int
    image: object
    target_size: tuple[int, int]

def _lazy_import_transformers_stack():
    # Delay the heavy ML imports until the command actually runs so simple
    # metadata operations and --help stay cheap and environment-friendly.
    try:
        import torch
        from PIL import Image
        from tqdm import tqdm
        from transformers import AutoModelForZeroShotObjectDetection, AutoProcessor
    except ImportError as exc:  # pragma: no cover - depends on local environment
        raise RuntimeError(
            "Grounding DINO dependencies are missing. Install the offline pipeline dependencies first."
        ) from exc

    return torch, Image, tqdm, AutoModelForZeroShotObjectDetection, AutoProcessor


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


def _post_process_grounding_dino_results(
    processor,
    outputs,
    input_ids,
    box_threshold: float,
    text_threshold: float,
    target_sizes,
):
    # Hugging Face has changed this processor signature across versions. The
    # adapter keeps the rest of the pipeline independent from that drift.
    post_process = processor.post_process_grounded_object_detection
    parameters = inspect.signature(post_process).parameters

    kwargs = {
        "outputs": outputs,
        "input_ids": input_ids,
        "target_sizes": target_sizes,
    }

    # Transformers has shipped this API under two compatible names across versions:
    # `threshold` in some releases and `box_threshold` in others. Support both so the
    # project does not depend on a single pinned signature to run.
    if "box_threshold" in parameters:
        kwargs["box_threshold"] = box_threshold
    elif "threshold" in parameters:
        kwargs["threshold"] = box_threshold
    else:
        raise RuntimeError(
            "Unsupported Grounding DINO processor API: expected either "
            "`box_threshold` or `threshold` in post_process_grounded_object_detection()."
        )

    if "text_threshold" in parameters:
        kwargs["text_threshold"] = text_threshold

    return post_process(**kwargs)


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
    # This stage only owns model inference and CSV normalization. Later stages
    # decide which detections become persistent AOIs for Unity.
    torch, Image, tqdm, AutoModelForZeroShotObjectDetection, AutoProcessor = _lazy_import_transformers_stack()

    frames_dir = Path(frames_dir)
    output_csv = Path(output_csv)

    if not frames_dir.exists():
        raise FileNotFoundError(f"Frames directory not found: {frames_dir}")

    if not text_prompt or not text_prompt.strip():
        raise ValueError("text_prompt must not be empty")

    if not 0.0 <= box_threshold <= 1.0:
        raise ValueError("box_threshold must be between 0.0 and 1.0")

    if not 0.0 <= text_threshold <= 1.0:
        raise ValueError("text_threshold must be between 0.0 and 1.0")

    output_csv.parent.mkdir(parents=True, exist_ok=True)

    runtime_summary = inspect_torch_runtime(torch)
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

    _emit_log(log_callback, f"[detect_grounding_dino] Runtime: {runtime_summary.short_label}")
    _emit_log(log_callback, f"[detect_grounding_dino] Using device: {device}")
    _emit_log(log_callback, f"[detect_grounding_dino] Model: {model_id}")
    _emit_log(log_callback, f"[detect_grounding_dino] Batch size: {effective_batch_size}")
    _emit_log(log_callback, f"[detect_grounding_dino] Precision: {resolved_precision}")
    if inference_max_width or inference_max_height:
        _emit_log(
            log_callback,
            (
                "[detect_grounding_dino] Downscaling frames for inference to at most "
                f"{inference_max_width or 'full'}x{inference_max_height or 'full'}."
            ),
        )

    if device == "cuda":
        torch.backends.cudnn.benchmark = True
        try:
            torch.set_float32_matmul_precision("high")
        except Exception:
            pass

    model_kwargs = {}
    if device == "cuda" and resolved_precision == "fp16":
        model_kwargs["dtype"] = torch.float16

    processor = AutoProcessor.from_pretrained(model_id)
    model = AutoModelForZeroShotObjectDetection.from_pretrained(model_id, **model_kwargs).to(device)
    model.eval()

    frame_paths = sorted([*frames_dir.glob("*.jpg"), *frames_dir.glob("*.jpeg"), *frames_dir.glob("*.png")])
    if not frame_paths:
        raise RuntimeError(f"No images found in: {frames_dir}")

    rows: list[dict[str, object]] = []

    iterator = frame_paths
    if progress_callback is None:
        iterator = tqdm(frame_paths, desc="Running Grounding DINO")

    total_frames = len(frame_paths)
    _emit_progress(progress_callback, 0, total_frames, "Loading Grounding DINO and preparing detections.")

    del iterator  # The tqdm wrapper is replaced by explicit batched progress below.
    image_loader = lambda path: _prepare_frame(
        frame_path=path,
        image_module=Image,
        inference_max_width=inference_max_width,
        inference_max_height=inference_max_height,
    )

    processed_index = 0
    batch_starts = range(0, len(frame_paths), effective_batch_size)
    if progress_callback is None:
        batch_starts = tqdm(batch_starts, desc="Running Grounding DINO")

    for batch_start in batch_starts:
        batch_paths = frame_paths[batch_start: batch_start + effective_batch_size]
        if effective_preload_workers > 1 and len(batch_paths) > 1:
            with ThreadPoolExecutor(max_workers=min(effective_preload_workers, len(batch_paths))) as executor:
                prepared_batch = list(executor.map(image_loader, batch_paths))
        else:
            prepared_batch = [image_loader(frame_path) for frame_path in batch_paths]

        input_images = [prepared_frame.image for prepared_frame in prepared_batch]
        target_sizes = [prepared_frame.target_size for prepared_frame in prepared_batch]
        input_prompts = [text_prompt] * len(prepared_batch)
        inputs = processor(images=input_images, text=input_prompts, return_tensors="pt").to(device)
        with torch.inference_mode():
            if device == "cuda" and resolved_precision == "fp16":
                with torch.autocast(device_type="cuda", dtype=torch.float16):
                    outputs = model(**inputs)
            else:
                outputs = model(**inputs)

        batch_results = _post_process_grounding_dino_results(
            processor=processor,
            outputs=outputs,
            input_ids=inputs.input_ids,
            box_threshold=box_threshold,
            text_threshold=text_threshold,
            target_sizes=target_sizes,
        )

        for prepared_frame, results in zip(prepared_batch, batch_results):
            boxes = results["boxes"].cpu().tolist()
            scores = results["scores"].cpu().tolist()
            labels = [str(label) for label in results["labels"]]

            for detection_index, (box, score, label) in enumerate(zip(boxes, scores, labels)):
                x_min, y_min, x_max, y_max = box
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
                        "source": "grounding_dino",
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

    _emit_log(log_callback, f"[detect_grounding_dino] Frames processed: {len(frame_paths)}")
    _emit_log(log_callback, f"[detect_grounding_dino] Detections exported: {len(detections)}")
    _emit_log(log_callback, f"[detect_grounding_dino] CSV written to: {output_csv}")
    return detections


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run Grounding DINO over extracted 360 frames and export bounding boxes to CSV."
    )
    parser.add_argument(
        "--frames-dir",
        default="data/frames/video_360",
        help="Directory containing the extracted frames.",
    )
    parser.add_argument(
        "--output-csv",
        default="data/interim/detections/video_360_grounding_dino_boxes.csv",
        help="CSV path where detections will be written.",
    )
    parser.add_argument(
        "--text-prompt",
        default="person. face. bottle. screen. product.",
        help="Grounding DINO text prompt. Dot-separated prompts work well for the model.",
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
