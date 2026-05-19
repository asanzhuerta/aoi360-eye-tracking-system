# aoi360_analytics

Analytics package for:
- fixation detection
- AOI metrics
- validation against manual annotations
- exports to CSV / Parquet

## Current scope

The current branch starts the post-processing stage with a first practical pipeline for the fixation-based CSV logs exported by Unity.

It currently supports:

1. loading one or more runtime CSV files
2. filtering out non-runtime CSVs automatically when `data/exports/` also contains benchmarks or previous analytics outputs
3. validating the expected export schema
4. estimating the effective fixation cadence per session/video
5. producing a practical quality report per session and per source CSV file
6. computing AOI-level dwell time, first-fixation timing, visit counts, and normalized time-share metrics
7. aggregating quality and AOI engagement metrics by participant, by video, and by `video x AOI`
8. estimating AOI-to-AOI transition counts from the ordered fixation timeline
9. enriching AOI ids with names/categories from the AOI sequence manifests when they are available

## Phase 3 manual: installation

Recommended:

```bash
pip install -e python/analytics
```

## Phase 3 manual: execution

The expected Unity input location is:

- `data/exports/`

That folder is now the repository-root handoff between the Unity runtime and the analytics stage whenever the runtime can resolve the repo root.

## Script

Analyze one directory of Unity runtime exports:

```bash
python python/analytics/scripts/analyze_runtime_exports.py --input-dir data/exports --manifest-root data/processed/metadata
```

Analyze explicit CSV files:

```bash
python python/analytics/scripts/analyze_runtime_exports.py --input-csv data/exports/session_01.csv --input-csv data/exports/session_02.csv
```

## Outputs

The analytics script writes one timestamped folder under `data/exports/analytics/` with:

- `runtime_rows_normalized.csv`
- `runtime_source_file_summary.csv`
- `runtime_session_summary.csv`
- `runtime_session_quality.csv`
- `runtime_participant_summary.csv`
- `runtime_video_summary.csv`
- `runtime_aoi_summary.csv`
- `runtime_video_aoi_summary.csv`
- `runtime_transition_summary.csv`
- `runtime_summary_snapshot.json`

## Metric notes

The current session-quality layer is heuristic on purpose: it gives a fast first pass over whether a run is usable for tracking analysis and whether it is usable for AOI analysis.

The current AOI summary is aligned with the Unity Phase 2 export and now adds normalized metrics:

- `fixation_steps`: number of valid fixation rows assigned to the AOI
- `dwell_time_ms`: `fixation_steps * fixation_step_ms_estimate`
- `time_to_first_fixation_ms`: first valid timestamp assigned to the AOI
- `visit_count`: number of AOI re-entries estimated from the ordered fixation timeline
- `dwell_share_of_valid_time`: fraction of valid tracked time spent on the AOI
- `dwell_share_of_assigned_time`: fraction of AOI-assigned time spent on the AOI
- `fixation_steps_per_minute_valid`: fixation cadence over valid tracked time
- `visit_count_per_minute_valid`: AOI revisit rate normalized by valid tracked time
- `time_to_first_fixation_ratio`: first-fixation timing normalized by estimated session duration

The transition summary is derived from ordered valid fixation rows:

- `from_aoi_id` and `to_aoi_id`: AOIs involved in the transition
- `transition_count`: number of observed AOI changes within one participant/session/video run
- `mean_transition_gap_ms`: average temporal gap between the source fixation and the next AOI fixation

The `runtime_video_aoi_summary.csv` table is the main comparative table for the next phase of the project:

- it aggregates AOI engagement by `video_id` and `aoi_id`
- it reports how often each AOI appears across runs
- it keeps normalized dwell / visit / first-fixation metrics that can later be compared between manual and automatic AOIs

This is the starting point for the post-processing phase, not the final analytics model. It is designed to be stable enough to test the end-to-end workflow as soon as real Unity exports are available, while already exposing the main descriptive tables needed to evaluate session quality, AOI engagement, and navigation patterns.
