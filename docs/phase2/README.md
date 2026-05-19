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

## Expected headset flow

The current documented Phase 2 flow is:

1. choose a processed stimulus in `Initial_Scene`
2. load `Phase2_360Playback_VR_sampleRIG`
3. show a `5 -> 0` countdown while video, AOI metadata, AOI maps, and eye-gaze runtime finish preparing
4. start the video only after the countdown has completed
5. export the experiment CSV when the operator ends the session with the right controller `A` button

## Build note

The current Unity implementation can be built, but it will only behave the same as the editor workflow if the build also receives the required video and AOI assets through the mirrored `StreamingAssets` layout. The repository-backed discovery path is the reference workflow used during development.

## Documents

- `runtime-unity.md` -> current Unity runtime behavior
- `aoi-data-contract.md` -> AOI map and metadata contract for Unity and Python
- `csv-schema.md` -> exported fixation CSV fields, units, and interpretation notes
- `validation-checklist.md` -> practical checks for testing on device
