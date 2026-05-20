# Phase 2 Documentation

Phase 2 is the stable Unity runtime stage of the AOI360 system.

Its purpose is to validate the runtime experiment loop before the offline AOI generation pipeline is connected:

- play one 360 video in VR
- read real eye tracking data
- map gaze onto the equirectangular stimulus
- resolve AOI hits from a precomputed AOI map
- visualize fixations in the headset
- export fixation-based CSV data

## Scope

Phase 2 does not yet generate AOIs automatically inside Unity. AOI maps are still produced offline, but the runtime contract is already structured so the Python pipeline can drop in generated maps and metadata without rewriting the Unity side.

## Key outputs

- runtime AOI hit detection
- AOI overlay visualization
- fixation commits every `250 ms`
- fixation trail history capped at `10` markers
- CSV export with AOI hit information
- pupil diameters when HTC eye tracker data is available

## Phase 2 manual: installation

Minimum local setup:

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

The editor workflow currently prioritizes repository-backed data. `StreamingAssets` remains the packaging path for later builds, but it is no longer the main day-to-day authoring path.

## Phase 2 manual: execution

Recommended runtime flow in the Editor:

1. Open `Initial_Scene`.
2. Enter Play mode.
3. Select one processed stimulus from the runtime UI.
4. Let the countdown finish while video and AOI data prepare.
5. Run the headset test and end the experiment with the configured controller binding.
6. Check the exported CSV under `data/exports/csv/`.

If the runtime cannot resolve the repository root, the CSV exporter falls back to `Application.persistentDataPath/Exports`. That fallback is mainly for packaged builds or unusual folder layouts.

## Phase 2 manual: Windows build for SteamVR runtime

If we now want to work with a `Windows x64` build that runs through `SteamVR`, the recommended path is:

1. Open the Unity project under `unity/AOI360Runtime/`.
2. Keep `OpenXR` as the XR backend for `Standalone`.
3. Make sure `SteamVR` is the active OpenXR runtime on the PC that will execute the build.
4. If the target headset uses HTC eye tracking on PC, start its eye-tracking runtime first.
5. Use `Tools > AOI > Build Windows x64 Player`.
6. Let Unity generate the player under `build/windows/AOI360Runtime/AOI360Runtime.exe`.
7. Launch that repository-local build without moving it outside the repo.

This keeps the build inside the repository tree, so the runtime can still resolve:

- `data/input_videos/`
- `data/processed/`
- `data/exports/csv/`

With that layout, the same repository-backed workflow used in the Editor is preserved and the CSV export continues to land in `data/exports/csv/`.

If the `.exe` is moved outside the repository, the runtime can lose that repository-backed behavior. In that case, define `AOI360_REPOSITORY_ROOT` before launching the player or pass `--aoi360-repo-root=<absolute_repo_path>`.

Important runtime note:

- this project already targets `Standalone + OpenXR`
- the runtime input bindings are based on `XRController` / `OpenXRController`
- eye gaze is read first from the HTC-specific eye-tracker path when available and then falls back to the generic OpenXR eye-gaze path

So the intended PC path is `Windows build -> OpenXR -> SteamVR runtime`, not `Windows build -> legacy SteamVR Unity plugin`.

## Phase 2 manual: refresh the Windows build with new videos

For the day-to-day operational flow, use:

- `windows-build-refresh-runbook.md`

That runbook documents the full chain:

1. drop the new video into `data/input_videos/`
2. rebuild the processed AOI assets with the offline Python pipeline
3. rebuild the repository-local Windows player
4. run the VR session through `SteamVR`
5. hand the exported CSVs to Phase 3 analytics

This is now the recommended maintenance path when the content changes but the Unity runtime itself does not.

## Expected headset flow

The current documented Phase 2 flow is:

1. choose a processed stimulus in `Initial_Scene`
2. load `Phase2_360Playback_VR_sampleRIG`
3. show a `5 -> 0` countdown while video, AOI metadata, AOI maps, and eye-gaze runtime finish preparing
4. start the video only after the countdown has completed
5. export the experiment CSV when the operator ends the session with the right controller `A` button

## Build note

The repository-backed discovery path is still the reference workflow used during development. For PC builds, the new recommended approach is to generate the player inside `build/windows/` so the executable remains under the same repo tree and can keep using repository-backed stimuli plus repository-local CSV export.

## Documents

- `runtime-unity.md` -> current Unity runtime behavior
- `aoi-data-contract.md` -> AOI map and metadata contract for Unity and Python
- `csv-schema.md` -> exported fixation CSV fields, units, and interpretation notes
- `validation-checklist.md` -> practical checks for testing on device
- `windows-build-refresh-runbook.md` -> operational checklist for adding new videos, rebuilding the Windows player, and handing the CSVs to Phase 3
