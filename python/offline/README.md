# aoi360_pipeline

Offline Python pipeline for the AOI360 project.

## Current scope

The current branch covers the first usable offline loop:

1. extract sparse frames from a 360 video
2. run an open-vocabulary detector over those frames
3. convert reviewed detections into a Unity-compatible AOI map and metadata JSON

This is not yet the final automated pipeline with segmentation, temporal propagation, seam handling, and tracking. It is the practical first version for testing AOI authoring against the Unity runtime.

The pipeline now also includes:

- a master rebuild script that regenerates the runtime assets from scratch
- a compact Tkinter GUI that lets an operator select a video, launch preprocessing, and monitor progress and logs live
- detector selection between `grounding_dino` and `yolo_world` while preserving the same detections CSV schema for the AOI builders
- a detector benchmark entry point so both models can be compared empirically on the same extracted 360-video frames
- CUDA-aware runtime inspection so the preprocessing stage can report whether it is running on `cpu` or `cuda`
- runtime-oriented exports with:
  - sparse AOI keyframes every `30` video frames by default
  - lighter AOI maps at `1024x512`
  - a baked yaw offset default of `0` degrees
  - a binary `RGB24` runtime pack so Unity can avoid decoding PNG keyframes during playback
- stable AOI identities across sparse keyframes, so one tracked AOI keeps the same color and id over the exported sequence

## Phase 1 manual: installation

Recommended:

```bash
pip install -e python/offline
```

If you have a compatible NVIDIA GPU and want the detector stage to use CUDA, reinstall PyTorch in the project environment with the official CUDA wheels. For the current setup we used the `cu126` index from the official PyTorch install guide:

```bash
python/offline/.venv/Scripts/python.exe -m pip install --upgrade --force-reinstall torch torchvision --index-url https://download.pytorch.org/whl/cu126
```

Alternative:

```bash
pip install -r python/offline/requirements.txt
```

Note:

- The first YOLO-World run downloads the pretrained weights and the CLIP text encoder cache.
- After that warm-up, repeated runs reuse the cached artifacts.

## Phase 1 manual: execution

Recommended entry points:

- CLI rebuild: `python python/offline/scripts/rebuild_runtime_assets.py --video-path data/input_videos/video_360.mp4 --clean`
- GUI launcher: `Launch_AOI360_Preprocess_GUI.bat`

The GUI launcher opens the same preprocessing pipeline documented below, but with a desktop window and live logs.

## Scripts

### 1. Extract frames

```bash
python python/offline/scripts/extract_frames.py --video-path data/input_videos/video_360.mp4 --output-dir data/frames/video_360 --every-n-frames 10
```

### 2. Run Grounding DINO

```bash
python python/offline/scripts/detect_grounding_dino.py --frames-dir data/frames/video_360 --output-csv data/interim/detections/video_360_grounding_dino_boxes.csv --text-prompt "person. face. bottle. screen. product."
```

### 3. Run YOLO-World

```bash
python python/offline/scripts/detect_yolo_world.py --frames-dir data/frames/video_360 --output-csv data/interim/detections/video_360_yolo_world_boxes.csv --text-prompt "person. face. bottle. screen. product."
```

### 4. Build one AOI map for Unity

```bash
python python/offline/scripts/build_aoi_map.py --detections-csv data/interim/detections/video_360_yolo_world_boxes.csv --frames-dir data/frames/video_360 --output-map-path data/processed/id_maps/video_360_aoi_map.png --output-metadata-path data/processed/metadata/video_360_aoi_map_metadata.json --video-name video_360.mp4 --fps 30 --frame-index 0
```

### 5. Build AOI maps for every detected frame

```bash
python python/offline/scripts/build_aoi_sequence.py --detections-csv data/interim/detections/video_360_yolo_world_boxes.csv --frames-dir data/frames/video_360 --output-maps-dir data/processed/id_maps/video_360 --output-metadata-dir data/processed/metadata/video_360 --manifest-path data/processed/metadata/video_360_aoi_sequence_manifest.json --video-name video_360.mp4 --fps 30
```

### 6. Rebuild the complete runtime asset set from scratch

This command derives the output layout from the selected video name, cleans previous generated assets, exports sparse AOI keyframes every `30` source frames, writes runtime-friendly `1024x512` AOI maps, and uses device-aware detector defaults. On this branch the default detector is `yolo_world`, but you can still switch back to `grounding_dino`.

```bash
python python/offline/scripts/rebuild_runtime_assets.py --video-path data/input_videos/video_360.mp4 --clean
```

### 7. Launch the preprocessing GUI

```bash
python python/offline/scripts/preprocess_gui.py
```

The GUI lets you:

- select the input 360 video
- choose the detector backend and pretrained model id
- tweak prompt, confidence, frame stride, output resolution, batch settings, and yaw offset
- launch the full preprocessing pipeline from one button
- follow stage progress and useful logs in real time
- see whether the pipeline is running on `cpu` or `cuda`
- see the resolved output folders before running anything
- auto-fill the prompt when the selected video stem matches an entry in `data/promts/5videosPromt.json`

If you want a root-level launcher instead of calling Python manually, use:

```bash
Launch_AOI360_Preprocess_GUI.bat
```

### 8. Benchmark Grounding DINO vs YOLO-World

This benchmark measures only the detector stage over already extracted frames, so the comparison stays focused on the AI models instead of mixing in video decoding or AOI export costs.

```bash
python python/offline/scripts/benchmark_detectors.py --frames-dir data/frames/video_360 --detector grounding_dino --detector yolo_world --repeats 2 --warmup-runs 1 --limit-frames 30
```

When `--limit-frames` is used, the benchmark now distributes that sample across the full extracted sequence instead of taking only the first N frames.

Outputs:

- raw per-run timings in `data/exports/benchmarks/<timestamp>/detector_benchmark_raw_runs.csv`
- aggregated detector summary in `data/exports/benchmarks/<timestamp>/detector_benchmark_summary.csv`
- benchmark metadata and runtime details in `data/exports/benchmarks/<timestamp>/detector_benchmark_metadata.json`

## Outputs

- Extracted frames: `data/frames/<video_name>/`
- Detection CSV: `data/interim/detections/`
- AOI maps: `data/processed/id_maps/`
- AOI keyframes: `data/processed/metadata/`
- AOI sequence manifest: `data/processed/metadata/<video_name>_aoi_sequence_manifest.json`
- AOI runtime pack: `data/processed/metadata/<video_name>_aoi_sequence_rgb24.bin`
- Detector benchmark reports: `data/exports/benchmarks/<timestamp>/`

The rebuild script and GUI now auto-derive these paths from the selected video stem, so a file such as `my_scene.mp4` will produce:

- `data/frames/my_scene/`
- `data/interim/detections/my_scene_yolo_world_boxes.csv`
- `data/processed/id_maps/my_scene/`
- `data/processed/metadata/my_scene/`
- `data/processed/metadata/my_scene_aoi_sequence_manifest.json`

## Unity handoff

### Current Unity runtime

The current Unity Phase 2 runtime is ready for:

1. copy the PNG into `unity/AOI360Runtime/Assets/Textures/AOIMaps`
2. copy the metadata JSON into `unity/AOI360Runtime/Assets/StreamingAssets/AOIMaps`
3. set the AOI map import settings as a data texture:
   - Read/Write Enabled = On
   - Generate Mip Maps = Off
   - Filter Mode = Point
   - Compression = None
   - sRGB = Off when possible

### Future per-frame Unity runtime

For per-frame AOI maps, the recommended handoff structure is:

- PNG sequence staged under `Assets/StreamingAssets/AOIMaps/<video_name>/maps/`
- lightweight keyframe JSON sequence staged under `Assets/StreamingAssets/AOIMaps/<video_name>/keyframes/`
- one sequence manifest JSON under `Assets/StreamingAssets/AOIMaps/<video_name>/`
- one binary runtime pack under `Assets/StreamingAssets/AOIMaps/<video_name>/`

In this format:

- AOI colors and semantic definitions are stored once in the manifest
- each keyframe JSON only stores which AOI ids are present in that frame plus their boxes/confidence
- each per-frame PNG uses the persistent color assigned to that AOI id across time
- the runtime pack stores each AOI keyframe as raw `RGB24` bytes for fast Unity uploads into a reused texture

Example PowerShell copy commands:

```powershell
New-Item -ItemType Directory -Force -Path unity\AOI360Runtime\Assets\StreamingAssets\AOIMaps\video_360\maps | Out-Null
New-Item -ItemType Directory -Force -Path unity\AOI360Runtime\Assets\StreamingAssets\AOIMaps\video_360\keyframes | Out-Null
Copy-Item data\processed\id_maps\video_360\*.png unity\AOI360Runtime\Assets\StreamingAssets\AOIMaps\video_360\maps\
Copy-Item data\processed\metadata\video_360\*.json unity\AOI360Runtime\Assets\StreamingAssets\AOIMaps\video_360\keyframes\
Copy-Item data\processed\metadata\video_360_aoi_sequence_manifest.json unity\AOI360Runtime\Assets\StreamingAssets\AOIMaps\video_360\
Copy-Item data\processed\metadata\video_360_aoi_sequence_rgb24.bin unity\AOI360Runtime\Assets\StreamingAssets\AOIMaps\video_360\
```

That per-frame layout is now consumed by the current Unity runtime loader keyed by `VideoPlayer.frame`, and the binary runtime pack is the preferred fast path for Phase 2 playback tests on standalone VR hardware.

## Prompt presets

The repository now keeps a simple per-video prompt mapping file in:

- `data/promts/5videosPromt.json`

This mapping is used in two places:

- the benchmark script through `--video-prompt` / `--video-prompt-file`
- the preprocessing GUI, which auto-loads the matching prompt when the selected video stem is present in that JSON
