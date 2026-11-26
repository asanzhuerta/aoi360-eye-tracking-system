"""Extract sparse frames from a source video for downstream AOI authoring."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from aoi360_pipeline.callbacks import (
    LogCallback,
    ProgressCallback,
    emit_log,
    emit_progress,
)

try:
    import cv2
except ImportError as exc:  # pragma: no cover - depends on local environment
    cv2 = None
    _CV2_IMPORT_ERROR = exc
else:
    _CV2_IMPORT_ERROR = None


SUPPORTED_IMAGE_EXTENSIONS = {"jpg", "jpeg", "png"}
# Image encoding releases the GIL, so a few writer threads overlap it with decoding.
_WRITER_THREADS = 4


def extract_frames(
    video_path: str | Path,
    output_dir: str | Path,
    every_n_frames: int = 1,
    image_extension: str = "jpg",
    progress_callback: ProgressCallback | None = None,
    log_callback: LogCallback | None = None,
) -> dict[str, int | str]:
    # Sparse extraction keeps the offline dataset manageable while preserving a
    # predictable mapping back to the original absolute video frame indices.
    if cv2 is None:
        raise RuntimeError(
            "OpenCV is required for frame extraction. Install the offline pipeline dependencies first."
        ) from _CV2_IMPORT_ERROR

    video_path = Path(video_path)
    output_dir = Path(output_dir)
    extension = image_extension.lower().lstrip(".")

    if not video_path.exists():
        raise FileNotFoundError(f"Video not found: {video_path}")

    if every_n_frames < 1:
        raise ValueError("every_n_frames must be >= 1")

    if extension not in SUPPORTED_IMAGE_EXTENSIONS:
        raise ValueError(
            f"Unsupported image extension '{image_extension}'. "
            f"Use one of: {', '.join(sorted(SUPPORTED_IMAGE_EXTENSIONS))}."
        )

    output_dir.mkdir(parents=True, exist_ok=True)

    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise RuntimeError(f"Could not open video: {video_path}")

    total_frames = max(0, int(capture.get(cv2.CAP_PROP_FRAME_COUNT)))
    frame_index = 0
    saved_count = 0

    emit_log(
        log_callback,
        f"[extract_frames] Reading '{video_path.name}' and saving one frame every {every_n_frames} frames.",
    )

    pending_writes = []
    with ThreadPoolExecutor(max_workers=_WRITER_THREADS) as writer:
        while True:
            # grab() advances without converting the frame; only kept frames
            # are retrieved, which yields the same pixels as read().
            if not capture.grab():
                break

            if frame_index % every_n_frames == 0:
                success, frame = capture.retrieve()
                if not success:
                    break
                output_path = output_dir / f"frame_{frame_index:06d}.{extension}"
                pending_writes.append(writer.submit(cv2.imwrite, str(output_path), frame))
                saved_count += 1

            frame_index += 1
            should_report = progress_callback is not None and (
                frame_index == 1 or frame_index % 30 == 0 or (total_frames > 0 and frame_index >= total_frames)
            )
            if should_report:
                emit_progress(
                    progress_callback,
                    min(frame_index, total_frames) if total_frames > 0 else frame_index,
                    total_frames if total_frames > 0 else max(frame_index, 1),
                    f"Extracted {saved_count} sparse frames so far.",
                )

    capture.release()
    for write in pending_writes:
        if not write.result():
            raise RuntimeError(f"Could not write extracted frames into: {output_dir}")

    emit_progress(
        progress_callback,
        total_frames if total_frames > 0 else frame_index,
        total_frames if total_frames > 0 else max(frame_index, 1),
        f"Frame extraction finished with {saved_count} saved frames.",
    )
    emit_log(
        log_callback,
        f"[extract_frames] Completed: {frame_index} frames read, {saved_count} saved into '{output_dir}'.",
    )

    return {
        "video_path": str(video_path),
        "output_dir": str(output_dir),
        "frames_read": frame_index,
        "frames_saved": saved_count,
        "every_n_frames": every_n_frames,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Extract sparse frames from a 360 video for manual review or AOI detection."
    )
    parser.add_argument(
        "--video-path",
        default="data/input_videos/video_360.mp4",
        help="Path to the source 360 video.",
    )
    parser.add_argument(
        "--output-dir",
        default="data/frames/video_360",
        help="Directory where extracted frames will be written.",
    )
    parser.add_argument(
        "--every-n-frames",
        type=int,
        default=10,
        help="Save one frame every N video frames.",
    )
    parser.add_argument(
        "--image-extension",
        default="jpg",
        help="Output image extension. Supported: jpg, jpeg, png.",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    summary = extract_frames(
        video_path=args.video_path,
        output_dir=args.output_dir,
        every_n_frames=args.every_n_frames,
        image_extension=args.image_extension,
    )

    print(f"Frames read: {summary['frames_read']}")
    print(f"Frames saved: {summary['frames_saved']}")
    print(f"Output directory: {summary['output_dir']}")


if __name__ == "__main__":
    main()
