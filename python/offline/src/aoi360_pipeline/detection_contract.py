from __future__ import annotations

"""Shared detection schema used by all offline detector backends."""

import re
from pathlib import Path

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


def get_frame_index(frame_path: Path) -> int:
    """Parse the frame index from the normalized extraction file name."""

    match = re.search(r"frame_(\d+)", frame_path.stem)
    if not match:
        raise ValueError(f"Could not extract frame index from: {frame_path.name}")
    return int(match.group(1))
