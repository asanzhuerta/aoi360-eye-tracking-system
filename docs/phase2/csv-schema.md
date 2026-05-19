# Phase 2 CSV Schema

This document describes the fixation-based CSV exported by the current Unity runtime.

## Export model

Phase 2 does not currently export raw per-frame gaze samples.

Instead, it exports one row per committed fixation step. The current runtime uses a fixation commit cadence of `250 ms`, so `timestamp_ms` follows that fixation timeline rather than the full display frame rate.

## Fields

| Field | Meaning | Units / format | Notes |
|---|---|---|---|
| `participant_id` | Participant identifier | text | Subject identifier used in the experiment |
| `session_id` | Session identifier | text | Session or run identifier |
| `video_id` | Video identifier | text | Name or identifier of the 360 stimulus |
| `timestamp_ms` | Fixation event timestamp | milliseconds | Quantized to the current fixation cadence |
| `frame_index` | Video frame index | integer | Current Unity `VideoPlayer` frame when the fixation row is exported |
| `origin_x` | Gaze origin X | meters | World-space origin of the gaze ray |
| `origin_y` | Gaze origin Y | meters | World-space origin of the gaze ray |
| `origin_z` | Gaze origin Z | meters | World-space origin of the gaze ray |
| `direction_x` | Gaze direction X | normalized float | X component of the gaze direction vector |
| `direction_y` | Gaze direction Y | normalized float | Y component of the gaze direction vector |
| `direction_z` | Gaze direction Z | normalized float | Z component of the gaze direction vector |
| `azimuth_rad` | Horizontal spherical angle | radians | Horizontal gaze angle on the 360 sphere |
| `elevation_rad` | Vertical spherical angle | radians | Vertical gaze angle on the 360 sphere |
| `uv_x` | Equirectangular U coordinate | normalized `[0,1]` | Horizontal coordinate on the AOI map / video texture |
| `uv_y` | Equirectangular V coordinate | normalized `[0,1]` | Vertical coordinate on the AOI map / video texture |
| `aoi_id` | AOI identifier | integer | AOI resolved from the current AOI map |
| `aoi_confidence` | AOI neighborhood confidence | normalized float | Local agreement around the sampled UV |
| `left_pupil_diameter` | Left pupil diameter | millimeters | Filled when HTC eye tracker pupil data is available |
| `right_pupil_diameter` | Right pupil diameter | millimeters | Filled when HTC eye tracker pupil data is available |
| `is_valid` | Tracking validity flag | `0` or `1` | Indicates whether tracking was considered valid at export time |

## Interpretation notes

- `origin_*` and `direction_*` describe the 3D gaze ray used by the runtime.
- `azimuth_rad`, `elevation_rad`, and `uv_*` describe the same gaze sample in spherical / equirectangular coordinates.
- `aoi_id` and `aoi_confidence` describe the AOI hit result at the fixation event.
- `left_pupil_diameter` and `right_pupil_diameter` are optional enrichment fields and may be empty if the runtime or hardware does not provide pupil data.

## Source of truth

The current Unity export is implemented in:

- `unity/AOI360Runtime/Assets/Scripts/Runtime/Logging/DataRecorder.cs`

If the runtime export changes, this document should be updated together with the code.
