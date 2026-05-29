from __future__ import annotations

"""Small OpenCV annotator that writes manual AOI boxes directly to CSV."""

import argparse
from dataclasses import dataclass
from pathlib import Path

import cv2
import pandas as pd

from aoi360_pipeline.rebuild_runtime_assets import find_repo_root

DEFAULT_MANIFEST_CSV = Path("data") / "manual_gt" / "benchmark_iou" / "frame_subset_manifest.csv"
DEFAULT_OUTPUT_CSV = Path("data") / "manual_gt" / "benchmark_iou" / "manual_boxes.csv"
WINDOW_NAME = "AOI360 Manual Boxes"

MARGIN = 12
SIDEBAR_WIDTH = 250
BUTTON_HEIGHT = 34
BUTTON_GAP = 8
TOP_PANEL_BASE_HEIGHT = 88


@dataclass
class FrameRecord:
    video_id: str
    frame_file: str
    frame_path: Path
    target_labels: list[str]
    selection_notes: str


@dataclass
class Button:
    key: str
    label: str
    rect: tuple[int, int, int, int]
    is_active: bool = False


class OpenCVManualAnnotator:
    def __init__(
        self,
        *,
        manifest_csv: Path,
        output_csv: Path,
        max_width: int,
        max_height: int,
    ) -> None:
        self.manifest_csv = manifest_csv
        self.output_csv = output_csv
        self.max_width = max_width
        self.max_height = max_height
        self.repo_root = find_repo_root(None)

        self.frames = self._load_manifest()
        self.annotations = self._load_existing_annotations()

        self.current_index = 0
        self.current_label_index = 0
        self.current_frame: FrameRecord | None = None

        self.current_image_original = None
        self.current_image_display = None
        self.current_scale = 1.0

        self.image_offset_x = MARGIN
        self.image_offset_y = MARGIN
        self.image_display_width = 0
        self.image_display_height = 0
        self.top_panel_height = TOP_PANEL_BASE_HEIGHT
        self.buttons: list[Button] = []
        self.button_lookup: dict[str, Button] = {}

        self.drag_start: tuple[int, int] | None = None
        self.drag_current: tuple[int, int] | None = None
        self.is_drawing = False

    def _load_manifest(self) -> list[FrameRecord]:
        manifest = pd.read_csv(self.manifest_csv).copy()
        required = ["video_id", "frame_file", "subset_frame_path"]
        missing = [column for column in required if column not in manifest.columns]
        if missing:
            raise ValueError(f"Manifest is missing required columns: {', '.join(missing)}")

        if "target_labels" not in manifest.columns:
            manifest["target_labels"] = ""
        if "selection_notes" not in manifest.columns:
            manifest["selection_notes"] = ""

        frames: list[FrameRecord] = []
        for row in manifest.itertuples(index=False):
            target_labels = [label.strip() for label in str(row.target_labels).split("|") if label.strip()]
            frame_path = Path(str(row.subset_frame_path))
            if not frame_path.is_absolute():
                frame_path = (self.repo_root / frame_path).resolve()
            frames.append(
                FrameRecord(
                    video_id=str(row.video_id).strip(),
                    frame_file=str(row.frame_file).strip(),
                    frame_path=frame_path,
                    target_labels=target_labels,
                    selection_notes=str(row.selection_notes).strip(),
                )
            )

        if not frames:
            raise ValueError("The frame subset manifest is empty.")
        return frames

    def _load_existing_annotations(self) -> pd.DataFrame:
        columns = ["video_id", "frame_file", "label", "x_min", "y_min", "x_max", "y_max", "annotation_notes"]
        if not self.output_csv.exists():
            return pd.DataFrame(columns=columns)
        annotations = pd.read_csv(self.output_csv).copy()
        for column in columns:
            if column not in annotations.columns:
                annotations[column] = ""
        return annotations.loc[:, columns]

    def _save_annotations(self) -> None:
        self.output_csv.parent.mkdir(parents=True, exist_ok=True)
        self.annotations.to_csv(self.output_csv, index=False)

    def _frame_annotations(self, frame: FrameRecord) -> pd.DataFrame:
        return self.annotations[
            (self.annotations["video_id"] == frame.video_id) & (self.annotations["frame_file"] == frame.frame_file)
        ].copy()

    def _replace_frame_annotations(self, frame: FrameRecord, frame_annotations: pd.DataFrame) -> None:
        keep_mask = ~(
            (self.annotations["video_id"] == frame.video_id) & (self.annotations["frame_file"] == frame.frame_file)
        )
        self.annotations = pd.concat([self.annotations.loc[keep_mask], frame_annotations], ignore_index=True)
        self.annotations = (
            self.annotations.sort_values(["video_id", "frame_file", "label", "x_min", "y_min"])
            .reset_index(drop=True)
        )

    def _load_frame(self) -> None:
        self.current_frame = self.frames[self.current_index]
        image = cv2.imread(str(self.current_frame.frame_path))
        if image is None:
            raise FileNotFoundError(f"Could not open frame image: {self.current_frame.frame_path}")

        original_height, original_width = image.shape[:2]
        scale = min(1.0, self.max_width / float(original_width), self.max_height / float(original_height))
        if scale < 1.0:
            display_width = max(1, int(round(original_width * scale)))
            display_height = max(1, int(round(original_height * scale)))
            display = cv2.resize(image, (display_width, display_height), interpolation=cv2.INTER_AREA)
        else:
            display = image.copy()

        self.current_image_original = image
        self.current_image_display = display
        self.current_scale = scale
        self.image_display_width = display.shape[1]
        self.image_display_height = display.shape[0]
        self.current_label_index = min(self.current_label_index, max(len(self.current_frame.target_labels) - 1, 0))
        self.drag_start = None
        self.drag_current = None
        self.is_drawing = False
        self._rebuild_layout()

    def _rebuild_layout(self) -> None:
        assert self.current_frame is not None
        info_lines = self._info_lines()
        self.top_panel_height = TOP_PANEL_BASE_HEIGHT + max(0, len(info_lines) - 3) * 24
        self.image_offset_x = MARGIN
        self.image_offset_y = self.top_panel_height + MARGIN
        self._build_buttons()

    def _info_lines(self) -> list[str]:
        assert self.current_frame is not None
        frame_annotations = self._frame_annotations(self.current_frame)
        return [
            f"Frame {self.current_index + 1}/{len(self.frames)}  |  {self.current_frame.video_id}/{self.current_frame.frame_file}",
            f"Current label: {self._current_label() or '(no label)'}  |  Boxes in frame: {len(frame_annotations)}",
            f"Labels: {', '.join(self.current_frame.target_labels) if self.current_frame.target_labels else '(none)'}",
            "Keyboard: n/p frame | ]/[ label | 1-9 label | d delete last | c clear frame | s save | q quit",
            f"Notes: {self.current_frame.selection_notes}" if self.current_frame.selection_notes else "",
        ]

    def _build_buttons(self) -> None:
        assert self.current_frame is not None
        self.buttons = []
        self.button_lookup = {}

        sidebar_x = self.image_offset_x + self.image_display_width + MARGIN
        y = self.image_offset_y

        def add_button(key: str, label: str, *, is_active: bool = False) -> None:
            nonlocal y
            rect = (sidebar_x, y, SIDEBAR_WIDTH, BUTTON_HEIGHT)
            button = Button(key=key, label=label, rect=rect, is_active=is_active)
            self.buttons.append(button)
            self.button_lookup[key] = button
            y += BUTTON_HEIGHT + BUTTON_GAP

        add_button("prev_frame", "Prev Frame (p)")
        add_button("next_frame", "Next Frame (n)")
        add_button("save", "Save (s)")
        add_button("delete_last", "Delete Last (d)")
        add_button("clear_frame", "Clear Frame (c)")
        add_button("quit", "Save & Quit (q)")

        y += 8
        add_button("prev_label", "Prev Label ([)")
        add_button("next_label", "Next Label (])")

        y += 8
        for label_index, label in enumerate(self.current_frame.target_labels, start=1):
            add_button(
                f"label_{label_index - 1}",
                f"{label_index}. {label}",
                is_active=(label_index - 1 == self.current_label_index),
            )

    def _current_label(self) -> str:
        if not self.current_frame or not self.current_frame.target_labels:
            return ""
        return self.current_frame.target_labels[self.current_label_index]

    def _draw_button(self, canvas, button: Button) -> None:
        x, y, width, height = button.rect
        fill = (78, 126, 230) if button.is_active else (52, 52, 52)
        border = (255, 255, 255) if button.is_active else (110, 110, 110)
        cv2.rectangle(canvas, (x, y), (x + width, y + height), fill, thickness=-1)
        cv2.rectangle(canvas, (x, y), (x + width, y + height), border, thickness=1)
        cv2.putText(
            canvas,
            button.label,
            (x + 10, y + 22),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.56,
            (245, 245, 245),
            1,
            cv2.LINE_AA,
        )

    def _draw_overlay(self) -> None:
        assert self.current_frame is not None
        assert self.current_image_display is not None

        canvas_width = self.image_display_width + SIDEBAR_WIDTH + 3 * MARGIN
        canvas_height = self.image_display_height + self.top_panel_height + 2 * MARGIN
        canvas = cv2.copyMakeBorder(
            self.current_image_display.copy(),
            self.top_panel_height,
            MARGIN,
            MARGIN,
            SIDEBAR_WIDTH + 2 * MARGIN,
            cv2.BORDER_CONSTANT,
            value=(18, 18, 18),
        )
        canvas = canvas[:canvas_height, :canvas_width]
        canvas[:, :] = (18, 18, 18)
        canvas[
            self.image_offset_y : self.image_offset_y + self.image_display_height,
            self.image_offset_x : self.image_offset_x + self.image_display_width,
        ] = self.current_image_display

        scale = self.current_scale
        frame_annotations = self._frame_annotations(self.current_frame)
        for idx, row in enumerate(frame_annotations.itertuples(index=False), start=1):
            x_min = self.image_offset_x + int(round(float(row.x_min) * scale))
            y_min = self.image_offset_y + int(round(float(row.y_min) * scale))
            x_max = self.image_offset_x + int(round(float(row.x_max) * scale))
            y_max = self.image_offset_y + int(round(float(row.y_max) * scale))
            cv2.rectangle(canvas, (x_min, y_min), (x_max, y_max), (0, 220, 0), 2)
            cv2.putText(
                canvas,
                f"{idx}:{row.label}",
                (x_min, max(self.image_offset_y + 18, y_min - 6)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                (0, 220, 0),
                2,
                cv2.LINE_AA,
            )

        if self.is_drawing and self.drag_start and self.drag_current:
            x1 = self.image_offset_x + self.drag_start[0]
            y1 = self.image_offset_y + self.drag_start[1]
            x2 = self.image_offset_x + self.drag_current[0]
            y2 = self.image_offset_y + self.drag_current[1]
            cv2.rectangle(canvas, (x1, y1), (x2, y2), (0, 180, 255), 2)

        info_lines = [line for line in self._info_lines() if line]
        for line_index, text in enumerate(info_lines):
            cv2.putText(
                canvas,
                text,
                (MARGIN, 26 + line_index * 22),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.58,
                (245, 245, 245),
                1,
                cv2.LINE_AA,
            )

        for button in self.buttons:
            self._draw_button(canvas, button)

        cv2.imshow(WINDOW_NAME, canvas)

    def _add_box_from_drag(self) -> None:
        assert self.current_frame is not None
        assert self.drag_start is not None
        assert self.drag_current is not None
        label = self._current_label()
        if not label:
            return

        x1, y1 = self.drag_start
        x2, y2 = self.drag_current
        if abs(x2 - x1) < 4 or abs(y2 - y1) < 4:
            return

        x_min_display, x_max_display = sorted([x1, x2])
        y_min_display, y_max_display = sorted([y1, y2])

        x_min = int(round(x_min_display / self.current_scale))
        y_min = int(round(y_min_display / self.current_scale))
        x_max = int(round(x_max_display / self.current_scale))
        y_max = int(round(y_max_display / self.current_scale))

        frame_annotations = self._frame_annotations(self.current_frame)
        new_row = pd.DataFrame(
            [
                {
                    "video_id": self.current_frame.video_id,
                    "frame_file": self.current_frame.frame_file,
                    "label": label,
                    "x_min": x_min,
                    "y_min": y_min,
                    "x_max": x_max,
                    "y_max": y_max,
                    "annotation_notes": "Annotated with local OpenCV tool",
                }
            ]
        )
        frame_annotations = pd.concat([frame_annotations, new_row], ignore_index=True)
        self._replace_frame_annotations(self.current_frame, frame_annotations)

    def _delete_last_box(self) -> None:
        assert self.current_frame is not None
        frame_annotations = self._frame_annotations(self.current_frame)
        if frame_annotations.empty:
            return
        frame_annotations = frame_annotations.iloc[:-1].copy()
        self._replace_frame_annotations(self.current_frame, frame_annotations)

    def _clear_frame_boxes(self) -> None:
        assert self.current_frame is not None
        empty = pd.DataFrame(columns=self.annotations.columns)
        self._replace_frame_annotations(self.current_frame, empty)

    def _to_image_coords(self, x: int, y: int) -> tuple[int, int] | None:
        local_x = x - self.image_offset_x
        local_y = y - self.image_offset_y
        if local_x < 0 or local_y < 0 or local_x >= self.image_display_width or local_y >= self.image_display_height:
            return None
        return local_x, local_y

    def _button_at(self, x: int, y: int) -> Button | None:
        for button in self.buttons:
            bx, by, bw, bh = button.rect
            if bx <= x <= bx + bw and by <= y <= by + bh:
                return button
        return None

    def _handle_button(self, key: str) -> bool:
        if key == "prev_frame":
            self._previous_frame()
        elif key == "next_frame":
            self._next_frame()
        elif key == "save":
            self._save_annotations()
        elif key == "delete_last":
            self._delete_last_box()
        elif key == "clear_frame":
            self._clear_frame_boxes()
        elif key == "quit":
            self._save_annotations()
            return True
        elif key == "prev_label":
            self._previous_label()
        elif key == "next_label":
            self._next_label()
        elif key.startswith("label_"):
            self.current_label_index = int(key.split("_", 1)[1])
            self._build_buttons()
        return False

    def _on_mouse(self, event: int, x: int, y: int, _flags: int, _userdata: object) -> None:
        button = self._button_at(x, y)
        if button and event == cv2.EVENT_LBUTTONDOWN:
            should_quit = self._handle_button(button.key)
            if should_quit:
                self._quit_requested = True
            return

        image_point = self._to_image_coords(x, y)
        if event == cv2.EVENT_LBUTTONDOWN and image_point is not None:
            self.drag_start = image_point
            self.drag_current = image_point
            self.is_drawing = True
        elif event == cv2.EVENT_MOUSEMOVE and self.is_drawing and image_point is not None:
            self.drag_current = image_point
        elif event == cv2.EVENT_LBUTTONUP and self.is_drawing:
            if image_point is not None:
                self.drag_current = image_point
                self._add_box_from_drag()
            self.is_drawing = False
            self.drag_start = None
            self.drag_current = None

    def _next_frame(self) -> None:
        if self.current_index < len(self.frames) - 1:
            self.current_index += 1
            self._load_frame()

    def _previous_frame(self) -> None:
        if self.current_index > 0:
            self.current_index -= 1
            self._load_frame()

    def _next_label(self) -> None:
        if self.current_frame and self.current_frame.target_labels:
            self.current_label_index = (self.current_label_index + 1) % len(self.current_frame.target_labels)
            self._build_buttons()

    def _previous_label(self) -> None:
        if self.current_frame and self.current_frame.target_labels:
            self.current_label_index = (self.current_label_index - 1) % len(self.current_frame.target_labels)
            self._build_buttons()

    def _select_label_by_digit(self, digit: int) -> None:
        if self.current_frame and 1 <= digit <= len(self.current_frame.target_labels):
            self.current_label_index = digit - 1
            self._build_buttons()

    def run(self) -> None:
        self._load_frame()
        self._quit_requested = False
        cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)
        cv2.setMouseCallback(WINDOW_NAME, self._on_mouse)

        while True:
            self._draw_overlay()
            if self._quit_requested:
                break

            key = cv2.waitKeyEx(25)
            if key == -1:
                continue

            if key in (ord("q"), 27):
                self._save_annotations()
                break
            if key == ord("s"):
                self._save_annotations()
            elif key == ord("n"):
                self._next_frame()
            elif key == ord("p"):
                self._previous_frame()
            elif key == ord("]"):
                self._next_label()
            elif key == ord("["):
                self._previous_label()
            elif key in (ord("d"), 8, 127):
                self._delete_last_box()
            elif key == ord("c"):
                self._clear_frame_boxes()
            elif ord("1") <= key <= ord("9"):
                self._select_label_by_digit(key - ord("0"))

        cv2.destroyAllWindows()


def _resolve_repo_path(repo_root: Path, candidate: str | Path) -> Path:
    path = Path(candidate)
    if path.is_absolute():
        return path
    return (repo_root / path).resolve()


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Annotate test-frame IoU manual boxes locally with OpenCV."
    )
    parser.add_argument("--manifest-csv", default=str(DEFAULT_MANIFEST_CSV))
    parser.add_argument("--output-csv", default=str(DEFAULT_OUTPUT_CSV))
    parser.add_argument("--max-width", type=int, default=1400)
    parser.add_argument("--max-height", type=int, default=820)
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()
    repo_root = find_repo_root(None)
    annotator = OpenCVManualAnnotator(
        manifest_csv=_resolve_repo_path(repo_root, args.manifest_csv),
        output_csv=_resolve_repo_path(repo_root, args.output_csv),
        max_width=args.max_width,
        max_height=args.max_height,
    )
    annotator.run()


if __name__ == "__main__":
    main()
