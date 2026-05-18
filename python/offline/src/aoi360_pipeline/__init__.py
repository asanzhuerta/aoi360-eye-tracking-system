"""
Utilities for the offline AOI360 pipeline.

The package intentionally keeps the first phase simple:
- extract sparse frames from a 360 video
- run an open-vocabulary detector over those frames
- convert accepted detections into a Unity-compatible AOI map + metadata JSON
"""

__all__ = [
    "aoi_map_builder",
    "aoi_map_sequence_builder",
    "cache_roots",
    "detection_contract",
    "detectors",
    "frame_extraction",
    "grounding_dino",
    "owlv2",
    "yolo_world",
]
