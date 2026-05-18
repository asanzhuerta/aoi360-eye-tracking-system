# Unity Manual Test Plan

This document turns the current Phase 0 checklist into a practical regression test flow for the Unity runtime.

## Scope

Use this plan when checking whether the current Unity experiment loop still behaves correctly after changes in:

- `ExperimentSelectionSceneController`
- `ExperimentPlaybackFlowController`
- `VideoPlayback`
- `AOISequenceRuntimeLoader`
- `DataRecorder`
- eye-tracking / XR bridge scripts

## Before entering Play mode

1. Confirm there is at least one ready stimulus in:
   - `data/input_videos/`
   - `data/processed/id_maps/<video_name>/`
   - `data/processed/metadata/<video_name>_aoi_sequence_manifest.json`
2. Confirm the active scene flow is still:
   - `Initial_Scene`
   - `Phase0_360Playback_VR_sampleRIG`
3. In the Unity Console, clear old logs before the test.
4. If you changed AOI textures, re-check the import settings:
   - `Read/Write Enabled`
   - `Mip Maps Off`
   - `Filter Mode Point`
   - `Compression None`

## Smoke test in the selection scene

1. Open `Initial_Scene`.
2. Enter Play mode.
3. Verify that at least one stimulus button appears.
4. Move the headset and confirm the selection canvas stays fixed in world space.
5. Verify controller rays or pointer interaction are visible and can select a stimulus.

Expected result:

- the scene is interactive
- no null-reference spam appears in the Console
- the status text lists available stimuli instead of the empty-state warning

## Scene transition and countdown

1. Select one stimulus.
2. Confirm `Phase0_360Playback_VR_sampleRIG` loads.
3. Confirm the countdown overlay appears immediately.
4. Confirm the background starts black while the video prepares.
5. Confirm playback does not start before the countdown ends.

Expected result:

- a visible `5 -> 0` countdown
- no stale frame from the previous run
- no early video playback before unlock

## Video and AOI synchronization

1. After countdown completion, verify the 360 video starts.
2. Confirm the environment looks equirectangular, not flattened or cubemap-like.
3. Confirm the AOI overlay sphere appears.
4. Look at known AOI regions and verify the AOI highlight stays aligned while rotating the head.

Expected result:

- video starts once
- AOI overlay and video remain registered through head rotation
- the first AOI frame is already primed when playback begins, or at worst appears almost immediately

## Eye tracking and fixation behavior

1. Open the runtime debug overlay.
2. Confirm `Tracking Source` becomes `OpenXREyeGaze` or `ViveEyeTracker`.
3. Hold gaze on one point long enough to create a fixation.
4. Move gaze across at least two AOIs.

Expected result:

- fixation marker appears and grows
- fixation trail updates and caps around 10 markers
- AOI id/name/category changes when gaze crosses AOIs
- pupil values appear when HTC eye tracker pupil data is available

## Recording and export

1. Let the session run for several fixation commits.
2. End the experiment with the right controller `A` button or the fallback keyboard/controller binding.
3. Confirm the completion message appears.
4. Confirm the scene returns to `Initial_Scene` after about 5 seconds.
5. Check `Application.persistentDataPath/Exports` for the generated CSV.

Expected result:

- a single CSV export per run
- no duplicate exports from the same session
- the CSV includes `aoi_id`, `aoi_confidence`, `timestamp_ms`, and `is_valid`

## CSV spot-check

Open the exported CSV and verify:

1. The file is fixation-based, not full-frame spam.
2. `timestamp_ms` advances in roughly `250 ms` steps.
3. `frame_index` advances with playback.
4. `aoi_id` is populated when the gaze is over a mapped region.
5. `is_valid` drops when tracking is lost.

## Regression cases worth repeating

Repeat the test for these cases when Unity still feels unstable:

1. Start and end the same stimulus twice in a row.
2. Return to `Initial_Scene` while looking in a different direction each time.
3. Test one short stimulus and one longer stimulus.
4. Test one stimulus with dense AOIs and one with sparse AOIs.
5. Temporarily disable eye-tracking validity and verify the runtime fails gracefully instead of freezing.

## Fast failure signals

Stop and inspect the Console immediately if you see:

- countdown completes but the video never starts
- video starts before the countdown ends
- AOI overlay is missing
- controller rays disappear after scene transition
- CSV is not exported
- repeated null-reference or missing-script errors

## Suggested testing order after changes

1. Selection scene smoke test
2. Countdown/video start test
3. AOI alignment test
4. Eye-tracking/fixation test
5. CSV export test

This order catches the highest-risk breakpoints first and avoids spending headset time on later-stage checks if the experiment loop is already broken upstream.
