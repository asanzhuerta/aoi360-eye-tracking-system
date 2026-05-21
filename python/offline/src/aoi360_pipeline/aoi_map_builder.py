from __future__ import annotations

import argparse
import colorsys
import json
import re
from pathlib import Path

import pandas as pd
from PIL import Image, ImageChops, ImageDraw


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


def build_distinct_hex_color(index: int) -> str:
    if index < 1:
        raise ValueError("AOI color index must be >= 1")

    hue = (index * 0.61803398875) % 1.0
    red, green, blue = colorsys.hsv_to_rgb(hue, 0.75, 1.0)
    return "#{:02X}{:02X}{:02X}".format(int(red * 255), int(green * 255), int(blue * 255))


def parse_label_filters(values: list[str] | None) -> set[str]:
    if not values:
        return set()
    return {value.strip().lower() for value in values if value and value.strip()}


def normalize_text_fragment(value: str) -> str:
    normalized_value = re.sub(r"\s+", " ", str(value).replace("_", " ").strip().lower())
    return normalized_value


def parse_prompt_vocabulary(prompt: str) -> list[str]:
    prompt_segments = re.split(r"[.;\n\r]+", str(prompt))
    vocabulary: list[str] = []
    for segment in prompt_segments:
        normalized_segment = normalize_text_fragment(segment)
        if normalized_segment:
            vocabulary.append(normalized_segment)
    return vocabulary


def tokenize_label(value: str) -> set[str]:
    return {token for token in normalize_text_fragment(value).split(" ") if token}


def canonicalize_label_to_prompt(label: str, prompt: str) -> str:
    normalized_label = normalize_text_fragment(label)
    prompt_vocabulary = parse_prompt_vocabulary(prompt)
    if not normalized_label or not prompt_vocabulary:
        return normalized_label

    if normalized_label in prompt_vocabulary:
        return normalized_label

    label_tokens = tokenize_label(normalized_label)
    if not label_tokens:
        return normalized_label

    best_candidate = normalized_label
    best_score: tuple[int, float, int, int, int] | None = None

    for prompt_index, candidate in enumerate(prompt_vocabulary):
        candidate_tokens = tokenize_label(candidate)
        token_overlap = len(label_tokens.intersection(candidate_tokens))
        if token_overlap <= 0:
            continue

        overlap_ratio = token_overlap / max(len(label_tokens), len(candidate_tokens))
        contains_score = 1 if candidate in normalized_label or normalized_label in candidate else 0
        score = (
            contains_score,
            overlap_ratio,
            token_overlap,
            len(candidate_tokens),
            -prompt_index,
        )
        if best_score is None or score > best_score:
            best_candidate = candidate
            best_score = score

    return best_candidate


def _bbox_iou_from_series(box_a: pd.Series, box_b: pd.Series) -> float:
    inter_x_min = max(float(box_a["x_min"]), float(box_b["x_min"]))
    inter_y_min = max(float(box_a["y_min"]), float(box_b["y_min"]))
    inter_x_max = min(float(box_a["x_max"]), float(box_b["x_max"]))
    inter_y_max = min(float(box_a["y_max"]), float(box_b["y_max"]))

    inter_width = max(0.0, inter_x_max - inter_x_min)
    inter_height = max(0.0, inter_y_max - inter_y_min)
    intersection = inter_width * inter_height

    area_a = max(0.0, float(box_a["x_max"]) - float(box_a["x_min"])) * max(
        0.0, float(box_a["y_max"]) - float(box_a["y_min"])
    )
    area_b = max(0.0, float(box_b["x_max"]) - float(box_b["x_min"])) * max(
        0.0, float(box_b["y_max"]) - float(box_b["y_min"])
    )
    union = area_a + area_b - intersection

    if union <= 0.0:
        return 0.0

    return intersection / union


def apply_per_frame_label_nms(detections: pd.DataFrame, iou_threshold: float) -> pd.DataFrame:
    if detections.empty:
        return detections

    if not 0.0 <= iou_threshold <= 1.0:
        raise ValueError("frame_nms_iou_threshold must be between 0.0 and 1.0")

    kept_row_indexes: list[int] = []
    grouped = detections.groupby(["frame_index", "frame_file", "label"], sort=False)
    for _group_key, frame_group in grouped:
        ordered_group = frame_group.sort_values(["confidence", "detection_index"], ascending=[False, True])
        kept_rows: list[pd.Series] = []
        for row_index, row in ordered_group.iterrows():
            should_keep = True
            for kept_row in kept_rows:
                if _bbox_iou_from_series(row, kept_row) >= iou_threshold:
                    should_keep = False
                    break
            if should_keep:
                kept_rows.append(row)
                kept_row_indexes.append(int(row_index))

    if not kept_row_indexes:
        return detections.iloc[0:0].copy()

    return detections.loc[sorted(kept_row_indexes)].copy()


def build_aoi_entries_from_detections(
    detections: pd.DataFrame,
    width: int,
    height: int,
    box_padding: int = 0,
    source_width: int | None = None,
    source_height: int | None = None,
) -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []
    source_width = int(source_width or width)
    source_height = int(source_height or height)
    scale_x = width / max(1, source_width)
    scale_y = height / max(1, source_height)
    ordered_detections = detections.copy()
    ordered_detections["_bbox_area"] = (
        (ordered_detections["x_max"].astype(float) - ordered_detections["x_min"].astype(float)).clip(lower=0.0) *
        (ordered_detections["y_max"].astype(float) - ordered_detections["y_min"].astype(float)).clip(lower=0.0)
    )
    ordered_detections = ordered_detections.sort_values(
        ["_bbox_area", "confidence", "detection_index"],
        ascending=[False, True, True],
    )

    for local_aoi_id, row in enumerate(ordered_detections.itertuples(index=False), start=1):
        row_label = getattr(row, "label", getattr(row, "aoi_category", "aoi"))
        row_prompt = getattr(row, "aoi_prompt", getattr(row, "prompt", row_label))
        assigned_aoi_id = int(getattr(row, "aoi_id", local_aoi_id))
        color_hex = str(getattr(row, "aoi_color", build_distinct_hex_color(assigned_aoi_id)))
        name = str(getattr(row, "aoi_name", f"{str(row_label)}_{assigned_aoi_id:02d}"))
        category = str(getattr(row, "aoi_category", str(row_label)))
        prompt = str(row_prompt)

        red = int(color_hex[1:3], 16)
        green = int(color_hex[3:5], 16)
        blue = int(color_hex[5:7], 16)

        x_min = max(0, int(round((float(row.x_min) - box_padding) * scale_x)))
        y_min = max(0, int(round((float(row.y_min) - box_padding) * scale_y)))
        x_max = min(width - 1, int(round((float(row.x_max) + box_padding) * scale_x)))
        y_max = min(height - 1, int(round((float(row.y_max) + box_padding) * scale_y)))

        entries.append(
            {
                "id": assigned_aoi_id,
                "name": name,
                "prompt": prompt,
                "category": category,
                "parentId": 0,
                "color": color_hex,
                "confidence": float(row.confidence),
                "bbox": [x_min, y_min, x_max, y_max],
                "sourceDetectionIndex": int(row.detection_index),
                "fillRgb": (red, green, blue),
            }
        )

    return entries


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
        raise ValueError(
            "Detections CSV is missing required columns: " + ", ".join(missing_columns)
        )

    if normalize_labels_to_prompt_vocab:
        detections = detections.copy()
        detections["label"] = [
            canonicalize_label_to_prompt(label=row_label, prompt=row_prompt)
            for row_label, row_prompt in zip(detections["label"], detections["prompt"])
        ]

    label_filters = parse_label_filters(include_labels)
    if label_filters:
        detections = detections[
            detections["label"].astype(str).map(normalize_text_fragment).isin(label_filters)
        ]

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


def render_aoi_map_from_detections(
    detections: pd.DataFrame,
    frames_dir: str | Path,
    output_map_path: str | Path,
    output_metadata_path: str | Path | None,
    video_name: str,
    fps: int = 30,
    box_padding: int = 0,
    write_metadata_document: bool = True,
    output_width: int | None = None,
    output_height: int | None = None,
    yaw_offset_degrees: float = 0.0,
) -> dict[str, object]:
    frames_dir = Path(frames_dir)
    output_map_path = Path(output_map_path)
    if output_metadata_path is not None:
        output_metadata_path = Path(output_metadata_path)

    if not frames_dir.exists():
        raise FileNotFoundError(f"Frames directory not found: {frames_dir}")

    if box_padding < 0:
        raise ValueError("box_padding must be >= 0")

    if fps < 0:
        raise ValueError("fps must be >= 0")

    selected_frame_file = str(detections.iloc[0]["frame_file"])
    selected_frame_index = int(detections.iloc[0]["frame_index"])
    selected_frame_path = frames_dir / selected_frame_file
    if not selected_frame_path.exists():
        raise FileNotFoundError(f"Frame image referenced by detections was not found: {selected_frame_path}")

    with Image.open(selected_frame_path) as frame_image:
        source_width, source_height = frame_image.size

    width = int(output_width or source_width)
    height = int(output_height or source_height)

    if width <= 0 or height <= 0:
        raise ValueError("output_width and output_height must be > 0 when provided")

    aoi_map = Image.new("RGB", (width, height), (0, 0, 0))
    drawer = ImageDraw.Draw(aoi_map)

    aois = build_aoi_entries_from_detections(
        detections=detections,
        width=width,
        height=height,
        box_padding=box_padding,
        source_width=source_width,
        source_height=source_height,
    )

    for aoi in aois:
        x_min, y_min, x_max, y_max = aoi["bbox"]

        # Phase 1 deliberately paints box AOIs as a bootstrap path. Once segmentation
        # lands, this fill step can be replaced by exact masks without changing the
        # Unity-side metadata contract.
        drawer.rectangle([x_min, y_min, x_max, y_max], fill=aoi["fillRgb"])

    if abs(yaw_offset_degrees) > 0.0001:
        horizontal_pixel_offset = int(round((yaw_offset_degrees / 360.0) * width)) % width
        if horizontal_pixel_offset != 0:
            aoi_map = ImageChops.offset(aoi_map, horizontal_pixel_offset, 0)

    rgb24_bytes = aoi_map.tobytes()

    output_map_path.parent.mkdir(parents=True, exist_ok=True)
    aoi_map.save(output_map_path)

    if write_metadata_document:
        if output_metadata_path is None:
            raise ValueError("output_metadata_path is required when write_metadata_document=True")

        output_metadata_path = Path(output_metadata_path)
        output_metadata_path.parent.mkdir(parents=True, exist_ok=True)
        metadata = {
            "video": video_name,
            "fps": int(fps),
            "idMapResolution": [width, height],
            "sourceFrameResolution": [source_width, source_height],
            "bakedYawOffsetDegrees": float(yaw_offset_degrees),
            "frameIndex": selected_frame_index,
            "frameFile": selected_frame_file,
            "aois": [
                {
                    "id": aoi["id"],
                    "name": aoi["name"],
                    "prompt": aoi["prompt"],
                    "category": aoi["category"],
                    "parentId": aoi["parentId"],
                    "color": aoi["color"],
                    "sourceDetectionIndex": aoi["sourceDetectionIndex"],
                    "confidence": aoi["confidence"],
                    "bbox": aoi["bbox"],
                }
                for aoi in aois
            ],
        }
        output_metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    return {
        "frame_file": selected_frame_file,
        "frame_index": selected_frame_index,
        "aoi_count": len(aois),
        "output_map_path": str(output_map_path),
        "output_metadata_path": str(output_metadata_path) if output_metadata_path is not None else "",
        "image_width": width,
        "image_height": height,
        "source_image_width": source_width,
        "source_image_height": source_height,
        "baked_yaw_offset_degrees": float(yaw_offset_degrees),
        "rgb24_bytes": rgb24_bytes,
        "aois": [
            {
                "id": aoi["id"],
                "name": aoi["name"],
                "prompt": aoi["prompt"],
                "category": aoi["category"],
                "parentId": aoi["parentId"],
                "color": aoi["color"],
                "sourceDetectionIndex": aoi["sourceDetectionIndex"],
                "confidence": aoi["confidence"],
                "bbox": aoi["bbox"],
            }
            for aoi in aois
        ],
    }


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
    detections = load_and_filter_detections(
        detections_csv=detections_csv,
        include_labels=include_labels,
        min_confidence=min_confidence,
    )
    selected_detections = select_frame_detections(
        detections=detections,
        frame_index=frame_index,
        frame_file=frame_file,
    )
    return render_aoi_map_from_detections(
        detections=selected_detections,
        frames_dir=frames_dir,
        output_map_path=output_map_path,
        output_metadata_path=output_metadata_path,
        video_name=video_name,
        fps=fps,
        box_padding=box_padding,
        output_width=output_width,
        output_height=output_height,
        yaw_offset_degrees=yaw_offset_degrees,
    )


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
    parser.add_argument(
        "--fps",
        type=int,
        default=30,
        help="FPS metadata to write into the AOI metadata JSON.",
    )
    parser.add_argument(
        "--frame-index",
        type=int,
        default=None,
        help="Specific frame index to convert into an AOI map.",
    )
    parser.add_argument(
        "--frame-file",
        default=None,
        help="Specific frame filename to convert into an AOI map.",
    )
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
    parser = build_parser()
    args = parser.parse_args()
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
