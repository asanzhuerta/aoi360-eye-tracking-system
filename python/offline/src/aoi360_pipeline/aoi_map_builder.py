"""Render exact-colour AOI ID maps from detector boxes.

Each AOI is painted as a filled rectangle with a unique RGB colour, so the
Unity runtime can resolve a gaze UV coordinate to an AOI id by exact colour
lookup. Larger boxes are painted first, so smaller (nested) AOIs stay visible.
"""

from __future__ import annotations

import argparse
import colorsys
import json
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
from PIL import Image, ImageChops, ImageDraw

from aoi360_pipeline.geometry import bbox_area, bbox_iou
from aoi360_pipeline.prompts import (  # noqa: F401  (re-exported for compatibility)
    canonicalize_label_to_prompt,
    normalize_text_fragment,
    parse_label_filters,
    parse_prompt_vocabulary,
    tokenize_label,
)

REQUIRED_DETECTION_COLUMNS = {
    "frame_index",
    "frame_file",
    "detection_index",
    "label",
    "confidence",
    "x_min",
    "y_min",
    "x_max",
    "y_max",
    "prompt",
}

# Golden-ratio hue stepping keeps consecutive ids visually distinct.
_GOLDEN_RATIO_CONJUGATE = 0.61803398875


def build_distinct_hex_color(index: int) -> str:
    if index < 1:
        raise ValueError("AOI color index must be >= 1")

    hue = (index * _GOLDEN_RATIO_CONJUGATE) % 1.0
    red, green, blue = colorsys.hsv_to_rgb(hue, 0.75, 1.0)
    return "#{:02X}{:02X}{:02X}".format(int(red * 255), int(green * 255), int(blue * 255))


def hex_to_rgb(color_hex: str) -> tuple[int, int, int]:
    return int(color_hex[1:3], 16), int(color_hex[3:5], 16), int(color_hex[5:7], 16)


@dataclass(frozen=True)
class AoiBox:
    """One detection to paint, in source-frame pixel coordinates."""

    detection_index: int
    label: str
    prompt: str
    confidence: float
    x_min: float
    y_min: float
    x_max: float
    y_max: float
    # Persistent identity assigned by the sequence tracker. When it is None the
    # id is the box's position in paint order, and the colour/name derive from it.
    aoi_id: int | None = None
    name: str | None = None
    color: str | None = None

    @property
    def bbox(self) -> tuple[float, float, float, float]:
        return (self.x_min, self.y_min, self.x_max, self.y_max)


@dataclass(frozen=True)
class AoiEntry:
    """An AOI as painted into a map, in map pixel coordinates."""

    id: int
    name: str
    prompt: str
    category: str
    color: str
    confidence: float
    bbox: list[int]
    source_detection_index: int

    def to_metadata(self) -> dict[str, object]:
        return {
            "id": self.id,
            "name": self.name,
            "prompt": self.prompt,
            "category": self.category,
            "parentId": 0,
            "color": self.color,
            "sourceDetectionIndex": self.source_detection_index,
            "confidence": self.confidence,
            "bbox": self.bbox,
        }


def boxes_from_dataframe(detections: pd.DataFrame) -> list[AoiBox]:
    return [
        AoiBox(
            detection_index=int(row.detection_index),
            label=str(row.label),
            prompt=str(row.prompt),
            confidence=float(row.confidence),
            x_min=float(row.x_min),
            y_min=float(row.y_min),
            x_max=float(row.x_max),
            y_max=float(row.y_max),
        )
        for row in detections.itertuples(index=False)
    ]


def apply_per_frame_label_nms(detections: pd.DataFrame, iou_threshold: float) -> pd.DataFrame:
    """Greedy NMS within each (frame, label) group, highest confidence first."""
    if detections.empty:
        return detections

    if not 0.0 <= iou_threshold <= 1.0:
        raise ValueError("frame_nms_iou_threshold must be between 0.0 and 1.0")

    boxes = detections[["x_min", "y_min", "x_max", "y_max"]].to_numpy(dtype=float)
    position_of = {label: position for position, label in enumerate(detections.index)}

    kept_row_indexes: list[int] = []
    grouped = detections.groupby(["frame_index", "frame_file", "label"], sort=False)
    for _group_key, frame_group in grouped:
        ordered_group = frame_group.sort_values(["confidence", "detection_index"], ascending=[False, True])
        kept_boxes: list[tuple[float, float, float, float]] = []
        for row_index in ordered_group.index:
            box = tuple(boxes[position_of[row_index]])
            if all(bbox_iou(box, kept) < iou_threshold for kept in kept_boxes):
                kept_boxes.append(box)
                kept_row_indexes.append(int(row_index))

    if not kept_row_indexes:
        return detections.iloc[0:0].copy()

    return detections.loc[sorted(kept_row_indexes)].copy()


def build_aoi_entries(
    boxes: Iterable[AoiBox],
    width: int,
    height: int,
    box_padding: int = 0,
    source_width: int | None = None,
    source_height: int | None = None,
) -> list[AoiEntry]:
    """Scale and pad boxes into map space, ordered largest first (paint order)."""
    source_width = int(source_width or width)
    source_height = int(source_height or height)
    scale_x = width / max(1, source_width)
    scale_y = height / max(1, source_height)

    ordered = sorted(boxes, key=lambda box: (-bbox_area(box.bbox), box.confidence, box.detection_index))

    entries: list[AoiEntry] = []
    for paint_position, box in enumerate(ordered, start=1):
        aoi_id = box.aoi_id if box.aoi_id is not None else paint_position
        entries.append(
            AoiEntry(
                id=int(aoi_id),
                name=box.name or f"{box.label}_{aoi_id:02d}",
                prompt=box.prompt,
                category=box.label,
                color=box.color or build_distinct_hex_color(aoi_id),
                confidence=box.confidence,
                bbox=[
                    max(0, int(round((box.x_min - box_padding) * scale_x))),
                    max(0, int(round((box.y_min - box_padding) * scale_y))),
                    min(width - 1, int(round((box.x_max + box_padding) * scale_x))),
                    min(height - 1, int(round((box.y_max + box_padding) * scale_y))),
                ],
                source_detection_index=box.detection_index,
            )
        )
    return entries


def paint_aoi_map(entries: list[AoiEntry], width: int, height: int, yaw_offset_degrees: float = 0.0) -> Image.Image:
    """Paint entries in order onto a black RGB canvas and apply the yaw roll."""
    if width <= 0 or height <= 0:
        raise ValueError("output_width and output_height must be > 0 when provided")

    aoi_map = Image.new("RGB", (width, height), (0, 0, 0))
    drawer = ImageDraw.Draw(aoi_map)
    for entry in entries:
        # Boxes are a bootstrap representation; segmentation masks can replace
        # this fill step without changing the Unity-side metadata contract.
        drawer.rectangle(entry.bbox, fill=hex_to_rgb(entry.color))

    if abs(yaw_offset_degrees) > 0.0001:
        horizontal_pixel_offset = int(round((yaw_offset_degrees / 360.0) * width)) % width
        if horizontal_pixel_offset != 0:
            aoi_map = ImageChops.offset(aoi_map, horizontal_pixel_offset, 0)

    return aoi_map


def write_json(path: Path, document: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2), encoding="utf-8")


def read_frame_size(frames_dir: Path, frame_file: str) -> tuple[int, int]:
    frame_path = frames_dir / frame_file
    if not frame_path.exists():
        raise FileNotFoundError(f"Frame image referenced by detections was not found: {frame_path}")
    with Image.open(frame_path) as frame_image:
        return frame_image.size


def load_and_filter_detections(
    detections_csv: str | Path,
    include_labels: list[str] | None = None,
    min_confidence: float = 0.35,
    frame_nms_iou_threshold: float | None = None,
    normalize_labels_to_prompt_vocab: bool = False,
) -> pd.DataFrame:
    detections_csv = Path(detections_csv)
    if not detections_csv.exists():
        raise FileNotFoundError(f"Detections CSV not found: {detections_csv}")

    detections = pd.read_csv(detections_csv)
    if detections.empty:
        raise RuntimeError(f"Detections CSV is empty: {detections_csv}")

    missing_columns = sorted(REQUIRED_DETECTION_COLUMNS.difference(detections.columns))
    if missing_columns:
        raise ValueError("Detections CSV is missing required columns: " + ", ".join(missing_columns))

    if normalize_labels_to_prompt_vocab:
        detections = detections.copy()
        detections["label"] = [
            canonicalize_label_to_prompt(label=row_label, prompt=row_prompt)
            for row_label, row_prompt in zip(detections["label"], detections["prompt"])
        ]

    label_filters = parse_label_filters(include_labels)
    if label_filters:
        detections = detections[detections["label"].astype(str).map(normalize_text_fragment).isin(label_filters)]

    detections = detections[detections["confidence"] >= float(min_confidence)].copy()
    if detections.empty:
        raise RuntimeError("No detections survived the current filters.")

    if frame_nms_iou_threshold is not None:
        detections = apply_per_frame_label_nms(detections, frame_nms_iou_threshold)
        if detections.empty:
            raise RuntimeError("No detections survived the per-frame label NMS pass.")

    return detections


def select_frame_detections(
    detections: pd.DataFrame,
    frame_index: int | None = None,
    frame_file: str | None = None,
) -> pd.DataFrame:
    """Pick one frame's detections; defaults to the earliest detected frame."""
    if frame_file and frame_index is not None:
        raise ValueError("Use either frame_file or frame_index, not both.")

    if frame_file:
        selected = detections[detections["frame_file"] == frame_file].copy()
    elif frame_index is not None:
        selected = detections[detections["frame_index"] == int(frame_index)].copy()
    else:
        chosen_frame_index = int(detections.sort_values(["frame_index", "detection_index"]).iloc[0]["frame_index"])
        selected = detections[detections["frame_index"] == chosen_frame_index].copy()

    if selected.empty:
        raise RuntimeError("No detections remain for the selected frame.")

    return selected.sort_values(["confidence", "detection_index"], ascending=[False, True]).reset_index(drop=True)


def build_aoi_map(
    detections_csv: str | Path,
    frames_dir: str | Path,
    output_map_path: str | Path,
    output_metadata_path: str | Path,
    video_name: str,
    fps: int = 30,
    frame_index: int | None = None,
    frame_file: str | None = None,
    include_labels: list[str] | None = None,
    min_confidence: float = 0.35,
    box_padding: int = 0,
    output_width: int | None = None,
    output_height: int | None = None,
    yaw_offset_degrees: float = 0.0,
) -> dict[str, object]:
    """Export a single AOI map PNG and its metadata JSON for one frame."""
    frames_dir = Path(frames_dir)
    output_map_path = Path(output_map_path)
    output_metadata_path = Path(output_metadata_path)
    if not frames_dir.exists():
        raise FileNotFoundError(f"Frames directory not found: {frames_dir}")
    if box_padding < 0:
        raise ValueError("box_padding must be >= 0")
    if fps < 0:
        raise ValueError("fps must be >= 0")

    detections = load_and_filter_detections(
        detections_csv=detections_csv,
        include_labels=include_labels,
        min_confidence=min_confidence,
    )
    selected = select_frame_detections(detections=detections, frame_index=frame_index, frame_file=frame_file)
    selected_frame_file = str(selected.iloc[0]["frame_file"])
    selected_frame_index = int(selected.iloc[0]["frame_index"])

    source_width, source_height = read_frame_size(frames_dir, selected_frame_file)
    width = int(output_width or source_width)
    height = int(output_height or source_height)

    entries = build_aoi_entries(
        boxes_from_dataframe(selected),
        width=width,
        height=height,
        box_padding=box_padding,
        source_width=source_width,
        source_height=source_height,
    )
    aoi_map = paint_aoi_map(entries, width, height, yaw_offset_degrees)
    output_map_path.parent.mkdir(parents=True, exist_ok=True)
    aoi_map.save(output_map_path)

    aoi_metadata = [entry.to_metadata() for entry in entries]
    write_json(
        output_metadata_path,
        {
            "video": video_name,
            "fps": int(fps),
            "idMapResolution": [width, height],
            "sourceFrameResolution": [source_width, source_height],
            "bakedYawOffsetDegrees": float(yaw_offset_degrees),
            "frameIndex": selected_frame_index,
            "frameFile": selected_frame_file,
            "aois": aoi_metadata,
        },
    )

    return {
        "frame_file": selected_frame_file,
        "frame_index": selected_frame_index,
        "aoi_count": len(entries),
        "output_map_path": str(output_map_path),
        "output_metadata_path": str(output_metadata_path),
        "image_width": width,
        "image_height": height,
        "source_image_width": source_width,
        "source_image_height": source_height,
        "baked_yaw_offset_degrees": float(yaw_offset_degrees),
        "aois": aoi_metadata,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a Unity-compatible AOI map and metadata JSON from a detections CSV."
    )
    parser.add_argument(
        "--detections-csv",
        default="data/interim/detections/video_360_grounding_dino_boxes.csv",
        help="Detections CSV produced by the open-vocabulary detector step.",
    )
    parser.add_argument(
        "--frames-dir",
        default="data/frames/video_360",
        help="Directory that contains the extracted frame images.",
    )
    parser.add_argument(
        "--output-map-path",
        default="data/processed/id_maps/video_360_aoi_map.png",
        help="Path where the AOI map PNG will be written.",
    )
    parser.add_argument(
        "--output-metadata-path",
        default="data/processed/metadata/video_360_aoi_map_metadata.json",
        help="Path where the AOI metadata JSON will be written.",
    )
    parser.add_argument(
        "--video-name",
        default="video_360.mp4",
        help="Video filename to write into the metadata JSON.",
    )
    parser.add_argument("--fps", type=int, default=30, help="FPS metadata to write into the AOI metadata JSON.")
    parser.add_argument("--frame-index", type=int, default=None, help="Specific frame index to convert.")
    parser.add_argument("--frame-file", default=None, help="Specific frame filename to convert.")
    parser.add_argument(
        "--include-label",
        action="append",
        dest="include_labels",
        help="Optional label filter. Repeat to keep multiple labels.",
    )
    parser.add_argument("--min-confidence", type=float, default=0.35)
    parser.add_argument("--box-padding", type=int, default=0)
    parser.add_argument("--output-width", type=int, default=None)
    parser.add_argument("--output-height", type=int, default=None)
    parser.add_argument("--yaw-offset-degrees", type=float, default=0.0)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    summary = build_aoi_map(
        detections_csv=args.detections_csv,
        frames_dir=args.frames_dir,
        output_map_path=args.output_map_path,
        output_metadata_path=args.output_metadata_path,
        video_name=args.video_name,
        fps=args.fps,
        frame_index=args.frame_index,
        frame_file=args.frame_file,
        include_labels=args.include_labels,
        min_confidence=args.min_confidence,
        box_padding=args.box_padding,
        output_width=args.output_width,
        output_height=args.output_height,
        yaw_offset_degrees=args.yaw_offset_degrees,
    )

    print(f"Frame used: {summary['frame_file']} (index={summary['frame_index']})")
    print(f"AOIs written: {summary['aoi_count']}")
    print(f"AOI map: {summary['output_map_path']}")
    print(f"Metadata: {summary['output_metadata_path']}")


if __name__ == "__main__":
    main()
