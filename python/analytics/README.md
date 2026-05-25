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
2. consuming Unity runtime CSVs from `data/exports/csv/` by default
3. still filtering out non-runtime CSVs automatically when a broader export folder also contains benchmarks or previous analytics outputs
4. validating the expected export schema
5. estimating the effective fixation cadence per session/video
6. producing a practical quality report per session and per source CSV file
7. computing AOI-level dwell time, first-fixation timing, visit counts, and normalized time-share metrics
8. aggregating quality and AOI engagement metrics by participant, by video, and by `video x AOI`
9. estimating AOI-to-AOI transition counts from the ordered fixation timeline
10. enriching AOI ids with names/categories from the AOI sequence manifests when they are available
11. reapplying two different AOI-manifest roots over the same Unity runtime logs in order to compare `manual vs automatic` AOI assignments without re-recording the session

## Phase 3 manual: installation

Recommended:

```bash
pip install -e python/analytics
```

## Phase 3 manual: execution

The expected Unity input location is:

- `data/exports/csv/`

That folder is now the repository-root handoff between the Unity runtime and the analytics stage whenever the runtime can resolve the repo root.

If the Windows build must be refreshed because a new video was added or its AOIs were regenerated, follow the operational runbook first:

- `docs/phase2/windows-build-refresh-runbook.md`

That runbook ends exactly at the Phase 3 handoff point: fresh runtime CSVs inside `data/exports/csv/`.

## Script

Analyze one directory of Unity runtime exports:

```bash
python python/analytics/scripts/analyze_runtime_exports.py --input-dir data/exports/csv --manifest-root data/processed/metadata
```

Analyze only sessions that pass the AOI-usable quality gate:

```bash
python python/analytics/scripts/analyze_runtime_exports.py --input-dir data/exports/csv --manifest-root data/processed/metadata --session-filter aoi_usable
```

Available session filters:

- `all` -> include every discovered runtime session
- `tracking_usable` -> keep only sessions usable for tracking analysis
- `aoi_usable` -> keep only sessions usable for AOI analysis

Analyze explicit CSV files:

```bash
python python/analytics/scripts/analyze_runtime_exports.py --input-csv data/exports/csv/session_01.csv --input-csv data/exports/csv/session_02.csv
```

Compare one set of runtime CSVs against two AOI sources:

```bash
python python/analytics/scripts/compare_runtime_aoi_sources.py \
  --input-dir data/exports/csv \
  --manual-manifest-root data/manual_gt/metadata \
  --automatic-manifest-root data/processed/metadata \
  --match-field aoi_category
```

Compare only sessions that are AOI-usable in both sources:

```bash
python python/analytics/scripts/compare_runtime_aoi_sources.py \
  --input-dir data/exports/csv \
  --manual-manifest-root data/manual_gt/metadata \
  --automatic-manifest-root data/processed/metadata \
  --match-field aoi_category \
  --session-filter aoi_usable
```

Comparison session filters:

- `all` -> compare every discovered runtime session
- `tracking_usable` -> compare only sessions that pass the tracking-quality gate
- `aoi_usable` -> compare only sessions that are AOI-usable in both the `manual` and `automatic` sources

For a quick self-check of the comparison pipeline before the manual package is frozen, both roots can temporarily point to the same manifest folder. In that case, the session-alignment and confusion outputs should converge toward perfect agreement.

## Outputs

The analytics script writes one timestamped folder under `data/exports/analytics/` with:

- `runtime_rows_normalized.csv`
- `runtime_source_file_summary.csv`
- `runtime_session_summary.csv`
- `runtime_session_quality.csv`
- `runtime_session_inclusion.csv`
- `runtime_participant_summary.csv`
- `runtime_video_summary.csv`
- `runtime_aoi_summary.csv`
- `runtime_video_aoi_summary.csv`
- `runtime_transition_summary.csv`
- `runtime_summary_snapshot.json`

The comparison script writes one timestamped folder under `data/exports/analytics/source_comparison/` with:

- `manual/` -> the full analytics export for the manual AOI source
- `automatic/` -> the full analytics export for the automatic AOI source
- `comparison_rows_reassigned.csv`
- `comparison_session_inclusion.csv`
- `comparison_session_alignment.csv`
- `comparison_category_confusion.csv`
- `comparison_match_field_confusion.csv`
- `manual_video_match_summary.csv`
- `automatic_video_match_summary.csv`
- `comparison_video_match_deltas.csv`
- `comparison_summary_snapshot.json`

## Metric notes

The current session-quality layer is heuristic on purpose: it gives a fast first pass over whether a run is usable for tracking analysis and whether it is usable for AOI analysis.

The new `--session-filter` option lets the downstream aggregation layer follow that quality gate directly instead of only reporting it. The exported `runtime_session_inclusion.csv` file makes the inclusion/exclusion decision explicit for each participant/session/video run.

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

The comparison layer reuses the same runtime rows and recomputes AOI ids from two manifest bundles:

- one bundle is treated as the `manual` reference source
- one bundle is treated as the `automatic` source under evaluation
- both bundles are applied to the same `video_id`, `frame_index`, and `uv` timeline exported by Unity

This lets the project answer the downstream methodological question directly: whether changing the AOI source changes the gaze metrics that would later be interpreted in the study.

The new comparison-level `--session-filter` option lets the project exclude weak sessions before the manual-vs-automatic agreement step. The exported `comparison_session_inclusion.csv` table makes that gate explicit and records whether a session was excluded for tracking quality or because one or both AOI sources were not AOI-usable.

The semantic comparison key is configurable through `--match-field`:

- `aoi_category` is the safest default when manual and automatic AOI ids are not directly aligned
- `aoi_name` is useful when both pipelines share a stable AOI naming convention
- `aoi_id` is only meaningful when both sources intentionally reuse the same numeric AOI ids

The comparison pipeline supports two AOI-frame backends:

- the packed RGB24 runtime blob, which matches the Unity runtime path
- per-frame PNG ID maps as a fallback, which keeps the workflow compatible with future manual annotations that have not been packed yet

This is the starting point for the post-processing phase, not the final analytics model. It is designed to be stable enough to test the end-to-end workflow as soon as real Unity exports are available, while already exposing the main descriptive tables needed to evaluate session quality, AOI engagement, and navigation patterns.
