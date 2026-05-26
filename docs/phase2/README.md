# Phase 2 Documentation

Phase 2 is the Unity/OpenXR runtime layer of the AOI360 system. It is the stage
that runs the VR experiment, resolves AOI hits in real time, and exports the
fixation-level CSV files later consumed by Phase 3.

## Current runtime scope

The current runtime supports:

- 360 video playback in VR
- OpenXR eye gaze acquisition with HTC VIVE fallback
- spherical gaze mapping to azimuth, elevation, and equirectangular UV
- exact-color AOI lookup against precomputed AOI maps
- optional AOI overlay rendering on an inner validation sphere
- fixation visualization and fixation-level CSV export
- repository-local Windows builds that preserve repo-backed data discovery

## Frozen pilot state

The participant-facing runtime was frozen around a three-stimulus pilot corpus:

- `test1Camera360`
- `test2Camera360`
- `test3Lions360`

The build used for pilot collection is repository-local:

- `build/windows/AOI360Runtime/AOI360Runtime.exe`

## Minimum local setup

1. Open the Unity project under `unity/AOI360Runtime/`.
2. Use the current project baseline:
   - Unity `6000.3.11f1`
   - URP enabled
   - `com.unity.xr.openxr` `1.16.1`
   - `com.unity.xr.management` `4.5.4`
   - HTC VIVE OpenXR package `2.5.0`
3. Make sure the repository data layout exists:
   - `data/input_videos/`
   - `data/processed/id_maps/<video_name>/`
   - `data/processed/metadata/<video_name>_aoi_sequence_manifest.json`

The editor workflow prioritizes repository-backed data. `StreamingAssets`
remains the packaging path for standalone builds, but it is no longer the main
authoring path during development.

## Recommended editor flow

1. Open `Initial_Scene`.
2. Enter Play mode.
3. Select one processed stimulus from the runtime UI.
4. Let the countdown finish while video and AOI data prepare.
5. Run the headset test and end the experiment with the configured controller binding.
6. Check the exported CSV under `data/exports/csv/`.

If the runtime cannot resolve the repository root, the CSV exporter falls back
to `Application.persistentDataPath/Exports/csv`. That fallback is mainly for
packaged builds or unusual folder layouts.

## Recommended Windows build flow

If you want a `Windows x64` build that runs through `SteamVR`, the intended path
is:

1. Open the Unity project under `unity/AOI360Runtime/`.
2. Keep `OpenXR` as the XR backend for `Standalone`.
3. Make sure `SteamVR` is the active OpenXR runtime on the PC that will execute the build.
4. If the headset uses HTC eye tracking on PC, start its eye-tracking runtime first.
5. Use `Tools > AOI > Build Windows x64 Player`.
6. Let Unity generate the player under `build/windows/AOI360Runtime/AOI360Runtime.exe`.
7. Launch that repository-local build without moving it outside the repo.

This preserves access to:

- `data/input_videos/`
- `data/processed/`
- `data/exports/csv/`

If the `.exe` is moved outside the repository, the runtime can lose that
repository-backed behavior. In that case, define `AOI360_REPOSITORY_ROOT`
before launching the player or pass `--aoi360-repo-root=<absolute_repo_path>`.

## Day-to-day maintenance flow

For the operational flow when the content changes but the Unity runtime itself
does not, use:

- `windows-build-refresh-runbook.md`

That runbook documents the full chain:

1. drop the new video into `data/input_videos/`
2. rebuild the processed AOI assets with the offline Python pipeline
3. rebuild the repository-local Windows player
4. run the VR session through `SteamVR`
5. hand the exported CSVs to Phase 3 analytics

## Expected runtime sequence

The current documented participant flow is:

1. choose a processed stimulus in `Initial_Scene`
2. load `Phase2_360Playback_VR_sampleRIG`
3. show the countdown while video, AOI metadata, AOI maps, and eye-gaze runtime prepare
4. start the video only after the countdown has completed
5. export the experiment CSV when the operator ends the session

## Documents

- `runtime-unity.md` -> current Unity runtime behavior
- `aoi-data-contract.md` -> AOI map and metadata contract for Unity and Python
- `csv-schema.md` -> exported fixation CSV fields, units, and interpretation notes
- `validation-checklist.md` -> practical checks for testing on device
- `windows-build-refresh-runbook.md` -> operational checklist for adding new videos, rebuilding the Windows player, and handing the CSVs to Phase 3
