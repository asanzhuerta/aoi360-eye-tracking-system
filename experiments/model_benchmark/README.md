# Model Benchmark Experiment

This folder documents the empirical detector benchmark used by the AOI360 preprocessing pipeline.

- `Grounding DINO`
- `OWLv2`
- `YOLO-World`

## Goal

Measure detector runtime on the same extracted 360-video frame sets so the comparison is:

- reproducible
- isolated from frame extraction and AOI-map export
- comparable across multiple stimuli and hardware runs

## Protocol

1. Pre-extract frames for each target 360 video with the normal preprocessing pipeline.
2. Run `benchmark_detectors.py` over the same frame directories for both detectors.
3. Use the same prompt, image-size limits, precision mode, and batch-size policy for both backends.
4. Record:
   - total duration
   - frames per second
   - milliseconds per frame
   - detection count
5. Repeat each configuration at least twice after one warm-up run when you want more stable timings.
6. Optionally add a small manual ground-truth subset and run the IoU validation scaffold to compare detector boxes against hand-drawn boxes on key benchmark frames.

## Reference command

```bash
python python/offline/scripts/benchmark_detectors.py --frames-dir data/frames/video_360 --frames-dir data/frames/Leones_National_Geographic_360 --detector grounding_dino --detector yolo_world --repeats 2 --warmup-runs 1 --limit-frames 30
```

## Outputs

Each benchmark run writes a timestamped folder under `data/exports/benchmarks/` with:

- `detector_benchmark_raw_runs.csv`
- `detector_benchmark_summary.csv`
- `detector_benchmark_metadata.json`

The manual spatial validation scaffold lives under:

- `data/manual_gt/benchmark_iou/`
- `python/offline/scripts/annotate_manual_boxes_opencv.py`
- `python/offline/scripts/verify_spatial_iou.py`

The current seeded IoU subset is based on 15 manually reviewable frames from the
frozen three-stimulus test corpus (`test1Camera360`, `test2Camera360`,
`test3Lions360`) rather than on the older five-video sample benchmark.

The copied 15-frame JPG subset used for manual labeling is kept as a local
working copy and is intentionally ignored by Git. The tracked benchmark-IoU
artefacts are the manifest, the hand-drawn box CSV, and the OpenCV annotator /
validation scripts. When freezing a release that cites these results, bundle the
frame subset and the generated `data/exports/benchmarks/spatial_iou/` outputs as
release assets or supplementary material.

Once `manual_boxes.csv` is filled, the IoU validation exports:

- `spatial_iou_rows.csv`
- `spatial_iou_summary_by_detector.csv`
- `spatial_iou_summary_by_scene_group.csv`
- `spatial_iou_summary_by_video.csv`
- `spatial_iou_metadata.json`

## Interpretation

Use the summary table to answer practical questions such as:

- Which detector is faster on the same 360 stimulus?
- How much does runtime vary across videos?
- Is the detector fast enough for your preprocessing batch size and hardware?
- Does a faster model also reduce detections too aggressively for your AOI authoring needs?

The benchmark measures the detector stage only. If you later want a full preprocessing benchmark, treat it as a second experiment so model time and pipeline overhead stay separable.
