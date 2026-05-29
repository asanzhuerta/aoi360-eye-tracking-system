# Test-Frame IoU Validation Scaffold

This folder hosts the manual ground-truth subset used to compare detector boxes
against hand-drawn bounding boxes on a small subset of the frozen three-stimulus
test corpus.

## Contents

- `frame_subset/`
  - 15 copied test frames ready for manual labeling (kept as a local working copy)
- `frame_subset_manifest.csv`
  - seeded manifest describing the selected frames and scene groups
- `manual_boxes.csv`
  - flat CSV to fill with manual bounding boxes

## Expected manual CSV schema

`manual_boxes.csv` must keep the following columns:

- `video_id`
- `frame_file`
- `label`
- `x_min`
- `y_min`
- `x_max`
- `y_max`
- `annotation_notes`

Use one row per hand-drawn object box. Repeated labels inside the same frame are
allowed; simply add one row per visible instance.

## Labeling guidance

- Use the copied images under `frame_subset/<video_id>/`.
- Keep the semantic labels aligned with `data/promts/3videosPromt.json`.
- Label only objects that are actually visible in the frame.
- Coordinates must be pixel coordinates in the original copied image.
- If a frame contains no visible object for a prompt label, do not add a row for it.

## Current subset

The current seeded subset uses five frames from each frozen test stimulus:

- `test1Camera360`
- `test2Camera360`
- `test3Lions360`

The copied JPG subset under `frame_subset/` is intentionally ignored by Git to
avoid repository bloat and duplicate media. The tracked artefacts are the
manifest, this README, and `manual_boxes.csv`. If the IoU validation is bundled
into a frozen archival release, include both the copied 15-frame subset and the
timestamped `data/exports/benchmarks/spatial_iou/` summaries as release assets.

## Local OpenCV annotator

Annotate the 15 copied frames locally with:

```powershell
python\offline\.venv\Scripts\python.exe python\offline\scripts\annotate_manual_boxes_opencv.py
```

The tool writes directly into `manual_boxes.csv`.

Controls:

- `Left mouse drag`
  - draw a new bounding box with the current label
- sidebar buttons
  - click to move between frames, change label, save, clear, or quit
- `n` / `p`
  - next / previous frame
- `]` / `[`
  - next / previous label
- `1` to `9`
  - jump directly to a label index shown in the overlay
- `d`
  - delete the last box of the current frame
- `c`
  - clear all boxes in the current frame
- `s`
  - save `manual_boxes.csv`
- `q` or `Esc`
  - save and quit

The overlay shows the current frame, available labels for that stimulus, and the
selection note seeded in the manifest.

## Running the validation

Once `manual_boxes.csv` is filled, run:

```powershell
python\offline\.venv\Scripts\python.exe python\offline\scripts\verify_spatial_iou.py
```

The script will:

1. rerun the three detectors over this 15-frame subset,
2. compare detector boxes against the manual boxes,
3. export per-box and aggregated IoU summaries under
   `data/exports/benchmarks/spatial_iou/<timestamp>/`.
