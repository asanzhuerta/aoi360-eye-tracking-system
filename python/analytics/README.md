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
2. validating the expected export schema
3. estimating the effective fixation cadence per session/video
4. summarizing session quality and valid-tracking coverage
5. computing AOI-level dwell time, first-fixation timing, and visit counts
6. aggregating quality and AOI engagement metrics by participant and by video
7. estimating AOI-to-AOI transition counts from the ordered fixation timeline
8. enriching AOI ids with names/categories from the AOI sequence manifests when they are available

## Phase 3 manual: installation

Recommended:

```bash
pip install -e python/analytics
```

## Phase 3 manual: execution

The expected Unity input location is:

- `data/exports/csv/`

That folder is now the repository-root handoff between the Unity runtime and the analytics stage whenever the runtime can resolve the repo root.

## Script

Analyze one directory of Unity runtime exports:

```bash
python python/analytics/scripts/analyze_runtime_exports.py --input-dir data/exports/csv --manifest-root data/processed/metadata
```

Analyze explicit CSV files:

```bash
python python/analytics/scripts/analyze_runtime_exports.py --input-csv data/exports/csv/session_01.csv --input-csv data/exports/csv/session_02.csv
```

## Outputs

The analytics script writes one timestamped folder under `data/exports/csv/analytics/` with:

- `runtime_rows_normalized.csv`
- `runtime_session_summary.csv`
- `runtime_participant_summary.csv`
- `runtime_video_summary.csv`
- `runtime_aoi_summary.csv`
- `runtime_transition_summary.csv`
- `runtime_summary_snapshot.json`

## Metric notes

The current AOI summary is intentionally simple and aligned with the Unity Phase 2 export:

- `fixation_steps`: number of valid fixation rows assigned to the AOI
- `dwell_time_ms`: `fixation_steps * fixation_step_ms_estimate`
- `time_to_first_fixation_ms`: first valid timestamp assigned to the AOI
- `visit_count`: number of AOI re-entries estimated from the ordered fixation timeline

The transition summary is derived from ordered valid fixation rows:

- `from_aoi_id` and `to_aoi_id`: AOIs involved in the transition
- `transition_count`: number of observed AOI changes within one participant/session/video run
- `mean_transition_gap_ms`: average temporal gap between the source fixation and the next AOI fixation

This is the starting point for the post-processing phase, not the final analytics model. It is designed to be stable enough to test the end-to-end workflow as soon as real Unity exports are available, while already exposing the main descriptive tables needed to evaluate session quality, AOI engagement, and navigation patterns.
