# AOI360 Eye Tracking System

Research system for 360 video attention analysis with:
- offline AOI generation in Python
- detector benchmarking in Python
- experimental runtime in Unity
- post-hoc analytics in Python

## Current project status

The repository is now organized around three practical phases:

- `Phase 1` -> offline AOI preprocessing in Python
- `Phase 2` -> Unity runtime playback, gaze capture, AOI lookup, and CSV export
- `Phase 3` -> post-processing and analytics over the Unity runtime exports

## Architecture

### 1. Offline pipeline
Python pipeline for:
- frame extraction
- 360 projection handling
- AOI detection from prompts
- segmentation and tracking
- AOI ID map export
- metadata export

### 2. Runtime
Unity runtime for:
- 360 video playback
- OpenXR eye gaze capture
- HTC VIVE OpenXR eye tracker fallback
- spherical gaze mapping
- AOI lookup on equirectangular ID maps
- AOI overlay rendering on the 360 sphere
- fixation visualization and trail rendering
- fixation-based CSV logging into `data/exports/csv/` when the repo root is available

### 3. Analytics
Python post-hoc analysis for:
- fixation detection
- TFF
- FD
- TFD
- FC
- FB
- validation comparisons between manual and automatic AOIs

## Where the install/run manuals live

The install and execution manuals are now split by phase:

- `Phase 1` manual: `python/offline/README.md`
  - installation: `Phase 1 manual: installation`
  - execution: `Phase 1 manual: execution`
- `Phase 2` manual: `docs/phase2/README.md`
  - installation: `Phase 2 manual: installation`
  - execution: `Phase 2 manual: execution`
- `Phase 3` manual: `python/analytics/README.md`
  - installation: `Phase 3 manual: installation`
  - execution: `Phase 3 manual: execution`

If you want the direct desktop launcher for the preprocessing GUI, use:

- `Launch_AOI360_Preprocess_GUI.bat`

## Current recommended workflow

The current practical workflow across the repository is:

1. add or update one source video under `data/input_videos/`
2. rebuild its AOI assets with the offline Python pipeline in `python/offline/`
3. rebuild the repository-local `Windows x64` player from Unity with `Tools > AOI > Build Windows x64 Player`
4. run the VR session from `build/windows/AOI360Runtime/AOI360Runtime.exe`
5. collect runtime CSV exports from `data/exports/csv/`

Use these entry points depending on what you need:

- preprocessing and AOI asset generation -> `python/offline/README.md`
- Unity runtime and Windows build flow -> `docs/phase2/README.md`
- refresh runbook for new videos -> `docs/phase2/windows-build-refresh-runbook.md`
- post-processing and analytics -> `python/analytics/README.md`

## Phase 2 goal

Build a stable end-to-end prototype with:
- one 360 video in Unity
- manual AOI maps rendered as an overlay on the 360 scene
- real eye tracking through OpenXR and HTC VIVE
- spherical gaze mapping and AOI lookup
- fixation commits every 250 ms
- fixation trail visualization in VR
- fixation-based CSV export
- a documented AOI data contract for future Grounding DINO integration

## Current Phase 2 status

The active Unity scene is `Phase2_360Playback_VR_sampleRIG`.

Phase 2 currently includes:
- 360 video playback on the skybox
- AOI overlay rendering from a runtime-generated transparent sphere
- AOI lookup through exact-color metadata maps exported by the offline pipeline
- fixation detection and commit cadence at `250 ms`
- visible fixation hit marker plus a capped trail of previous fixations
- CSV export of fixation events, AOI hits, and pupil diameters when HTC eye tracker data is available
- runtime debug UI showing AOI state, tracking source, and pupil data
- per-frame AOI sequence loading from `StreamingAssets`, reset-safe loop handling, and projection alignment through runtime calibration plus optional baked offline yaw offsets
- runtime performance tuning for standalone VR through lighter AOI maps, cached AOI pixel lookup, a binary AOI runtime pack, and frame-drop-friendly video playback
- fallback from problematic `.mkv` sources to `.mp4` / `.mov` / `.webm` when matching alternatives exist
- projection normalization for non-2:1 source videos so wide clips such as `3840x2160` can still be tested on the 360 sphere
- repository-first stimulus discovery from `data/input_videos` and `data/processed`, with `StreamingAssets` kept as the packaging path for later builds
- controller material repair in runtime so Focus 3 controller prefabs no longer render as magenta under the current URP setup
- CSV export routed to `data/exports/csv/` when the runtime can resolve the repository root
- repository-local Windows builds through `Tools > AOI > Build Windows x64 Player`, keeping the `.exe` under `build/windows/` so the runtime preserves the same repo-backed CSV export flow

## AOI map contract

The runtime now supports a color-driven AOI contract intended for the offline Python pipeline:

- AOI texture: exact-color ID map
- Metadata file: `StreamingAssets/AOIMaps/<map_name>_metadata.json`
- Metadata fields:
  - `id`
  - `name`
  - `prompt`
  - `category`
  - `parentId`
  - `color`

Example:

```json
{
  "video": "sample360.mp4",
  "fps": 30,
  "idMapResolution": [1920, 960],
  "aois": [
    {
      "id": 17,
      "name": "product_box_left",
      "prompt": "product box",
      "category": "product/box",
      "parentId": 0,
      "color": "#00FF00"
    }
  ]
}
```

This lets Unity resolve AOIs by exact pixel color while preserving semantic metadata that can later be produced by Grounding DINO, segmentation, and tracking.

## Repository layout

- `unity/AOI360Runtime` -> Unity project
- `python/offline` -> AOI generation pipeline
- `python/analytics` -> metric analysis
- `data` -> input and output data
- `docs` -> architecture, ADRs, notes, and phase documentation
- `experiments` -> phase-specific experiments

## Documentation

See the Phase 2 documentation for implementation details:
- `docs/phase2/README.md`
- `docs/phase2/runtime-unity.md`
- `docs/phase2/aoi-data-contract.md`
- `docs/phase2/csv-schema.md`
- `docs/phase2/validation-checklist.md`
- `docs/phase2/windows-build-refresh-runbook.md`

## Offline Python quick start

The current offline branch supports a simple AOI authoring loop:

1. extract sparse frames from `data/input_videos/video_360.mp4`
2. run an open-vocabulary detector over those frames
3. export a Unity-compatible AOI map PNG plus metadata JSON
4. optionally export a full per-frame AOI sequence plus manifest for Unity runtime loading
5. rebuild the full runtime-ready asset set in one command or from the preprocessing GUI

The offline pipeline now also supports:

- detector selection between Grounding DINO and YOLO-World while keeping the same downstream AOI/Unity contract
- reproducible timing benchmarks for Grounding DINO vs YOLO-World over extracted 360-video frames
- per-video prompt overrides for detector benchmarking through `data/promts/5videosPromt.json`
- CUDA-aware preprocessing when a compatible NVIDIA GPU is available
- automatic preprocessing defaults tuned to the detected runtime (`cpu` or `cuda`)
- stable AOI identities across sparse keyframes, so the same tracked AOI keeps the same color and id over time
- a more compact desktop preprocessing GUI that fits typical laptop screens better
- automatic prompt autofill in the GUI when the selected video matches an entry in `data/promts/5videosPromt.json`
- a default baked yaw offset of `0` degrees, with any extra alignment handled explicitly instead of hidden in the export defaults

Reference commands and options live in:

- `python/offline/README.md`
- `experiments/model_benchmark/README.md`

## Post-processing quick start

The analytics package now includes a first post-processing pass for the fixation-based CSV exports produced by Unity.

It can:

- load one or more runtime CSVs
- normalize and validate the export schema
- estimate the effective fixation cadence per session
- summarize session quality and valid-tracking coverage
- compute AOI-level dwell time, first-fixation timing, and visit counts
- aggregate session quality by participant and by video
- estimate AOI-to-AOI transition counts from the ordered fixation timeline
- enrich AOI ids with names/categories from the exported manifests when available

Reference commands and outputs live in:

- `python/analytics/README.md`
- `docs/unity/manual-test-plan.md`
