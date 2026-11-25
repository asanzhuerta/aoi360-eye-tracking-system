"""Axis-aligned box helpers. Boxes are (x_min, y_min, x_max, y_max) tuples."""

from __future__ import annotations

import math

Box = tuple[float, float, float, float]


def bbox_area(box: Box) -> float:
    x_min, y_min, x_max, y_max = box
    return max(0.0, x_max - x_min) * max(0.0, y_max - y_min)


def bbox_iou(box_a: Box, box_b: Box) -> float:
    """IoU with degenerate boxes clamped to zero area."""
    ax_min, ay_min, ax_max, ay_max = box_a
    bx_min, by_min, bx_max, by_max = box_b

    inter_width = max(0.0, min(ax_max, bx_max) - max(ax_min, bx_min))
    inter_height = max(0.0, min(ay_max, by_max) - max(ay_min, by_min))
    intersection = inter_width * inter_height

    union = bbox_area(box_a) + bbox_area(box_b) - intersection
    if union <= 0.0:
        return 0.0
    return intersection / union


def bbox_center_distance(box_a: Box, box_b: Box) -> float:
    ax_min, ay_min, ax_max, ay_max = box_a
    bx_min, by_min, bx_max, by_max = box_b
    return math.hypot(
        (ax_min + ax_max) * 0.5 - (bx_min + bx_max) * 0.5,
        (ay_min + ay_max) * 0.5 - (by_min + by_max) * 0.5,
    )


def bbox_area_similarity(box_a: Box, box_b: Box) -> float:
    """Ratio of the smaller to the larger area, 0 when either is empty."""
    area_a = bbox_area(box_a)
    area_b = bbox_area(box_b)
    if area_a <= 0.0 or area_b <= 0.0:
        return 0.0
    return min(area_a, area_b) / max(area_a, area_b)
