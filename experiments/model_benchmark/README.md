# Model Benchmark Experiment

This folder documents the empirical timing experiment for comparing the two open-vocabulary detector backends used by the AOI360 preprocessing pipeline:

- `Grounding DINO`
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

## Reference command

```bash
python python/offline/scripts/benchmark_detectors.py --frames-dir data/frames/video_360 --frames-dir data/frames/Leones_National_Geographic_360 --detector grounding_dino --detector yolo_world --repeats 2 --warmup-runs 1 --limit-frames 30
```

## Outputs

Each benchmark run writes a timestamped folder under `data/exports/benchmarks/` with:

- `detector_benchmark_raw_runs.csv`
- `detector_benchmark_summary.csv`
- `detector_benchmark_metadata.json`

## Interpretation

Use the summary table to answer practical questions such as:

- Which detector is faster on the same 360 stimulus?
- How much does runtime vary across videos?
- Is the detector fast enough for your preprocessing batch size and hardware?
- Does a faster model also reduce detections too aggressively for your AOI authoring needs?

The benchmark measures the detector stage only. If you later want a full preprocessing benchmark, treat it as a second experiment so model time and pipeline overhead stay separable.
