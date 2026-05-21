# Windows Build Refresh Runbook

This runbook documents the practical flow to update the current `Windows x64` build when a new 360 video is added to the repository.

The goal is to keep Unity as a packaging step only:

1. prepare the new stimulus in the offline Python pipeline
2. rebuild the repository-local Windows player
3. run the VR session
4. hand the exported CSVs to Phase 3 analytics

## When to use this runbook

Use this flow when:

- a new source video has been added
- AOI maps must be regenerated for an existing video
- the Windows build must be refreshed so the runtime can see the updated repository data

## Source of truth

The day-to-day source of truth is the repository data layout:

- `data/input_videos/`
- `data/processed/id_maps/`
- `data/processed/metadata/`
- `data/exports/csv/`

The runtime now discovers processed stimuli from the repository itself. That means the normal authoring loop no longer depends on manually copying AOI assets into Unity `StreamingAssets` for each new video.

## Step 1: Add the new video

Copy the new 360 video into:

- `data/input_videos/`

Example:

```text
data/input_videos/new_stimulus.mp4
```

If the new video needs its own prompt preset for the preprocessing GUI or detector benchmark flow, update one of the prompt preset mappings under:

- `data/promts/`

## Step 2: Rebuild the processed AOI assets

Recommended CLI path:

```bash
python python/offline/scripts/rebuild_runtime_assets.py --video-path data/input_videos/new_stimulus.mp4 --clean
```

Alternative GUI path:

```bash
Launch_AOI360_Preprocess_GUI.bat
```

After the run finishes, verify that these outputs exist:

- `data/frames/new_stimulus/`
- `data/interim/detections/new_stimulus_yolo_world_boxes.csv` or the detector-specific equivalent
- `data/processed/id_maps/new_stimulus/`
- `data/processed/metadata/new_stimulus/`
- `data/processed/metadata/new_stimulus_aoi_sequence_manifest.json`
- `data/processed/metadata/new_stimulus_aoi_sequence_rgb24.bin`

If these outputs are missing, do not rebuild the player yet. Fix the offline preprocessing step first.

## Step 3: Open Unity only to rebuild the player

Open:

- `unity/AOI360Runtime/`

Then run:

1. `Tools > AOI > Build Windows x64 Player`
2. wait for Unity to finish the build

Expected output:

- `build/windows/AOI360Runtime/AOI360Runtime.exe`

Important:

- keep the executable inside the repository
- do not move the build outside `build/windows/`

Keeping the player under the repo tree lets the runtime keep reading:

- `data/input_videos/`
- `data/processed/`
- `data/exports/csv/`

If you want the build to show only a selected subset of processed videos in `Initial_Scene`, edit:

- `data/experiment/runtime_config.json`

This allowlist filters the visible stimuli without deleting any source videos or generated AOI assets.

If the build is moved elsewhere, define `AOI360_REPOSITORY_ROOT` before launching it or pass `--aoi360-repo-root=<absolute_repo_path>`.

## Step 4: Launch the Windows build

On the PC that will run the headset session:

1. make sure `SteamVR` is the active `OpenXR` runtime
2. if HTC eye tracking is used, start `SR_Runtime`
3. launch `build/windows/AOI360Runtime/AOI360Runtime.exe`

The intended runtime path is:

- `Windows build -> OpenXR -> SteamVR runtime`

## Step 5: Verify the new stimulus in the runtime

Inside the build:

1. open the stimulus selection UI in `Initial_Scene`
2. confirm that the new video appears in the repository-backed list
3. select it and let the countdown complete
4. verify that the 360 video, AOI overlay, gaze marker, and controller visuals load normally

If the video does not appear in the selection UI, the most likely issue is that the Phase 1 outputs are incomplete or named inconsistently.

## Step 6: Run the session and collect the CSV

At the end of the VR session, confirm that the runtime exports the CSV to:

- `data/exports/csv/`

This folder is the handoff point into Phase 3.

## Step 7: Continue with Phase 3 analytics

Recommended Phase 3 command:

```bash
python python/analytics/scripts/analyze_runtime_exports.py --input-dir data/exports/csv --manifest-root data/processed/metadata
```

This reads the runtime CSVs from:

- `data/exports/csv/`

and writes analytics outputs under:

- `data/exports/analytics/`

## Short version

If you only need the checklist:

1. drop the new video into `data/input_videos/`
2. run `rebuild_runtime_assets.py` for that video
3. verify `data/processed/id_maps/` and `data/processed/metadata/`
4. rebuild the player with `Tools > AOI > Build Windows x64 Player`
5. launch the repo-local `.exe` with `SteamVR` as the `OpenXR` runtime
6. run the session and confirm the CSV lands in `data/exports/csv/`
7. run Phase 3 analytics from that CSV folder
