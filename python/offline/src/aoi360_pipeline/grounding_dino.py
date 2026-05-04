from __future__ import annotations
"""Run Grounding DINO over extracted frames and normalize the detections output."""

import argparse
import inspect
import re
from collections.abc import Callable
from pathlib import Path

import pandas as pd


DEFAULT_MODEL_ID = "IDEA-Research/grounding-dino-tiny"
DETECTION_COLUMNS = [
    "frame_index",
    "frame_file",
    "detection_index",
    "label",
    "confidence",
    "x_min",
    "y_min",
    "x_max",
    "y_max",
    "source",
    "model_id",
    "prompt",
]
ProgressCallback = Callable[[int, int, str], None]
LogCallback = Callable[[str], None]


def get_frame_index(frame_path: Path) -> int:
    match = re.search(r"frame_(\d+)", frame_path.stem)
    if not match:
        raise ValueError(f"Could not extract frame index from: {frame_path.name}")
    return int(match.group(1))


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


def detect_frames(
    frames_dir: str | Path,
    output_csv: str | Path,
    text_prompt: str,
    box_threshold: float = 0.35,
    text_threshold: float = 0.25,
    model_id: str = DEFAULT_MODEL_ID,
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

    device = "cuda" if torch.cuda.is_available() else "cpu"
    _emit_log(log_callback, f"[detect_grounding_dino] Using device: {device}")
    _emit_log(log_callback, f"[detect_grounding_dino] Model: {model_id}")

    processor = AutoProcessor.from_pretrained(model_id)
    model = AutoModelForZeroShotObjectDetection.from_pretrained(model_id).to(device)
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

    for processed_index, frame_path in enumerate(iterator, start=1):
        with Image.open(frame_path) as image_handle:
            image = image_handle.convert("RGB")
            frame_index = get_frame_index(frame_path)

            inputs = processor(images=image, text=text_prompt, return_tensors="pt").to(device)
            with torch.no_grad():
                outputs = model(**inputs)

            results = _post_process_grounding_dino_results(
                processor=processor,
                outputs=outputs,
                input_ids=inputs.input_ids,
                box_threshold=box_threshold,
                text_threshold=text_threshold,
                target_sizes=[(image.height, image.width)],
            )[0]

            boxes = results["boxes"].cpu().tolist()
            scores = results["scores"].cpu().tolist()
            labels = [str(label) for label in results["labels"]]

            for detection_index, (box, score, label) in enumerate(zip(boxes, scores, labels)):
                x_min, y_min, x_max, y_max = box
                rows.append(
                    {
                        "frame_index": frame_index,
                        "frame_file": frame_path.name,
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

        _emit_progress(
            progress_callback,
            processed_index,
            total_frames,
            f"Processed {frame_path.name} with {len(boxes)} detections.",
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
    )


if __name__ == "__main__":
    main()
