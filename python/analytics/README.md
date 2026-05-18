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
6. enriching AOI ids with names/categories from the AOI sequence manifests when they are available

## Install

Recommended:

```bash
pip install -e python/analytics
```

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
- `runtime_aoi_summary.csv`
- `runtime_summary_snapshot.json`

## Metric notes

The current AOI summary is intentionally simple and aligned with the Unity Phase 0 export:

- `fixation_steps`: number of valid fixation rows assigned to the AOI
- `dwell_time_ms`: `fixation_steps * fixation_step_ms_estimate`
- `time_to_first_fixation_ms`: first valid timestamp assigned to the AOI
- `visit_count`: number of AOI re-entries estimated from the ordered fixation timeline

This is the starting point for the post-processing phase, not the final analytics model. It is designed to be stable enough to test the end-to-end workflow as soon as real Unity exports are available.
