"""Detector registry for the offline open-vocabulary stage.

The rest of the AOI pipeline does not need to know which detector produced the
intermediate CSV, as long as the CSV keeps the shared schema
(``detection_contract.DETECTION_COLUMNS``). Backend modules are imported lazily
so that choosing one detector does not load the others' dependencies.
"""

from __future__ import annotations

import importlib
from types import ModuleType

import pandas as pd

from aoi360_pipeline.callbacks import LogCallback, ProgressCallback

DEFAULT_DETECTOR = "yolo_world"

SUPPORTED_DETECTORS: dict[str, str] = {
    "grounding_dino": "Grounding DINO",
    "owlv2": "OWLv2",
    "yolo_world": "YOLO-World",
}


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
    return f"{video_stem}_{normalize_detector_name(detector)}_boxes.csv"


def load_backend(detector: str) -> ModuleType:
    """Import the backend module (named after the detector key)."""
    return importlib.import_module(f"aoi360_pipeline.{normalize_detector_name(detector)}")


def resolve_default_model_id(detector: str) -> str:
    """Return the backend-specific pretrained model identifier."""
    return load_backend(detector).DEFAULT_MODEL_ID


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
    backend = load_backend(detector)
    return backend.detect_frames(
        frames_dir=frames_dir,
        output_csv=output_csv,
        text_prompt=text_prompt,
        box_threshold=box_threshold,
        text_threshold=text_threshold,
        model_id=model_id or backend.DEFAULT_MODEL_ID,
        batch_size=batch_size,
        inference_max_width=inference_max_width,
        inference_max_height=inference_max_height,
        preload_workers=preload_workers,
        precision=precision,
        progress_callback=progress_callback,
        log_callback=log_callback,
    )
