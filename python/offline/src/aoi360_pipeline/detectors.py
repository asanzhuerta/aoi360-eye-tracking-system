from __future__ import annotations

"""Detector registry for the offline open-vocabulary stage.

The rest of the AOI pipeline should not need to care which detector produced
the intermediate CSV, as long as the CSV keeps the shared schema that later
stages already consume.
"""

from collections.abc import Callable

import pandas as pd

DEFAULT_DETECTOR = "yolo_world"

SUPPORTED_DETECTORS: dict[str, str] = {
    "grounding_dino": "Grounding DINO",
    "owlv2": "OWLv2",
    "yolo_world": "YOLO-World",
}

ProgressCallback = Callable[[int, int, str], None]
LogCallback = Callable[[str], None]


def normalize_detector_name(detector: str) -> str:
    """Map user-facing detector names to stable internal keys."""

    normalized = detector.strip().lower().replace("-", "_").replace(" ", "_")
    if normalized not in SUPPORTED_DETECTORS:
        valid_values = ", ".join(sorted(SUPPORTED_DETECTORS))
        raise ValueError(f"Unsupported detector '{detector}'. Expected one of: {valid_values}")
    return normalized


def detector_display_name(detector: str) -> str:
    """Return the operator-facing label for a configured detector."""

    return SUPPORTED_DETECTORS[normalize_detector_name(detector)]


def default_detections_csv_name(video_stem: str, detector: str) -> str:
    """Keep detector outputs separate when multiple experiments coexist."""

    detector_key = normalize_detector_name(detector)
    return f"{video_stem}_{detector_key}_boxes.csv"


def resolve_default_model_id(detector: str) -> str:
    """Return the backend-specific pretrained model identifier."""

    detector_key = normalize_detector_name(detector)
    if detector_key == "grounding_dino":
        from aoi360_pipeline.grounding_dino import DEFAULT_MODEL_ID as grounding_dino_model_id

        return grounding_dino_model_id
    if detector_key == "yolo_world":
        from aoi360_pipeline.yolo_world import DEFAULT_MODEL_ID as yolo_world_model_id

        return yolo_world_model_id
    if detector_key == "owlv2":
        from aoi360_pipeline.owlv2 import DEFAULT_MODEL_ID as owlv2_model_id

        return owlv2_model_id

    raise AssertionError(f"Unexpected detector key: {detector_key}")


def detect_frames_with_backend(
    *,
    detector: str,
    frames_dir,
    output_csv,
    text_prompt: str,
    box_threshold: float = 0.35,
    text_threshold: float = 0.25,
    model_id: str | None = None,
    batch_size: int = 0,
    inference_max_width: int | None = None,
    inference_max_height: int | None = None,
    preload_workers: int = 0,
    precision: str = "auto",
    progress_callback: ProgressCallback | None = None,
    log_callback: LogCallback | None = None,
) -> pd.DataFrame:
    """Dispatch detection to the configured backend while preserving one schema."""

    detector_key = normalize_detector_name(detector)
    resolved_model_id = model_id or resolve_default_model_id(detector_key)

    if detector_key == "grounding_dino":
        from aoi360_pipeline.grounding_dino import detect_frames as detect_grounding_dino_frames

        return detect_grounding_dino_frames(
            frames_dir=frames_dir,
            output_csv=output_csv,
            text_prompt=text_prompt,
            box_threshold=box_threshold,
            text_threshold=text_threshold,
            model_id=resolved_model_id,
            batch_size=batch_size,
            inference_max_width=inference_max_width,
            inference_max_height=inference_max_height,
            preload_workers=preload_workers,
            precision=precision,
            progress_callback=progress_callback,
            log_callback=log_callback,
        )

    if detector_key == "yolo_world":
        from aoi360_pipeline.yolo_world import detect_frames as detect_yolo_world_frames

        return detect_yolo_world_frames(
            frames_dir=frames_dir,
            output_csv=output_csv,
            text_prompt=text_prompt,
            box_threshold=box_threshold,
            text_threshold=text_threshold,
            model_id=resolved_model_id,
            batch_size=batch_size,
            inference_max_width=inference_max_width,
            inference_max_height=inference_max_height,
            preload_workers=preload_workers,
            precision=precision,
            progress_callback=progress_callback,
            log_callback=log_callback,
        )

    if detector_key == "owlv2":
        from aoi360_pipeline.owlv2 import detect_frames as detect_owlv2_frames

        return detect_owlv2_frames(
            frames_dir=frames_dir,
            output_csv=output_csv,
            text_prompt=text_prompt,
            box_threshold=box_threshold,
            text_threshold=text_threshold,
            model_id=resolved_model_id,
            batch_size=batch_size,
            inference_max_width=inference_max_width,
            inference_max_height=inference_max_height,
            preload_workers=preload_workers,
            precision=precision,
            progress_callback=progress_callback,
            log_callback=log_callback,
        )

    raise AssertionError(f"Unexpected detector key: {detector_key}")
