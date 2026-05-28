# aoi360_analytics

Phase 3 analytics package for the AOI360 project.

It operates over the fixation-level CSV exports produced by the Unity runtime
and computes the main descriptive outputs used in the pilot and the paper.

## Current scope

The current package supports:

1. loading one or more Unity runtime CSV files
2. discovering runtime CSVs from `data/exports/csv/`
3. filtering out non-runtime CSVs automatically when broader export folders also contain benchmarks or previous analytics outputs
4. validating the expected CSV schema
5. estimating the effective fixation cadence per `participant x session x video`
6. producing practical quality and inclusion reports
7. computing AOI-level dwell time, first-fixation timing, fixations-before (`FB`), visit counts, revisit flags, and normalized time-share metrics
8. aggregating metrics by participant, by video, and by `video x AOI`
9. estimating AOI-to-AOI transitions from the ordered fixation timeline
10. enriching AOI ids with names/categories from the AOI sequence manifests when available
11. comparing two AOI sources over the same runtime gaze timeline (`manual` vs `automatic`)
12. generating a static HTML viewer for AOI-level inspection

## License note

The project source code is released under the Apache License 2.0. Bundled
third-party packages, archived outputs, and other external materials may remain
subject to their own upstream or publication-specific terms where applicable.

Important note:

- the current input is the runtime fixation-level export, not a continuous raw gaze sample stream
- literature metrics such as `FB`, `TFF`, `FD`, `TFD`, `FC`, and visits are therefore operationalised from fixation-level rows

## Installation

Recommended:

```bash
pip install -e python/analytics
```

Alternative:

```bash
pip install -r python/analytics/requirements.txt
```

## Main scripts

- `python/analytics/scripts/analyze_runtime_exports.py`
- `python/analytics/scripts/compare_runtime_aoi_sources.py`
- `python/analytics/scripts/build_runtime_aoi_html_report.py`
- `python/analytics/scripts/normalize_runtime_participant_ids.py`
- `python/analytics/scripts/build_phase3_stimulus_aoi_tables.py`

## Analyze runtime exports

Analyze one directory of Unity runtime exports:

```bash
python python/analytics/scripts/analyze_runtime_exports.py --input-dir data/exports/csv --manifest-root data/processed/metadata
```

Analyze only sessions that pass the AOI-usable quality gate:

```bash
python python/analytics/scripts/analyze_runtime_exports.py --input-dir data/exports/csv --manifest-root data/processed/metadata --session-filter aoi_usable
```

Analyze explicit CSV files:

```bash
python python/analytics/scripts/analyze_runtime_exports.py --input-csv data/exports/csv/session_01.csv --input-csv data/exports/csv/session_02.csv --manifest-root data/processed/metadata
```

Available session filters:

- `all` -> include every discovered runtime session
- `tracking_usable` -> keep only sessions usable for tracking analysis
- `aoi_usable` -> keep only sessions usable for AOI analysis

## Compare two AOI sources

Compare one set of runtime CSVs against two AOI sources:

```bash
python python/analytics/scripts/compare_runtime_aoi_sources.py ^
  --input-dir data/exports/csv ^
  --manual-manifest-root data/manual_gt/metadata ^
  --automatic-manifest-root data/processed/metadata ^
  --match-field aoi_category
```

Compare only sessions that are AOI-usable in both sources:

```bash
python python/analytics/scripts/compare_runtime_aoi_sources.py ^
  --input-dir data/exports/csv ^
  --manual-manifest-root data/manual_gt/metadata ^
  --automatic-manifest-root data/processed/metadata ^
  --match-field aoi_category ^
  --session-filter aoi_usable
```

Recommended semantic comparison keys:

- `aoi_category` -> safest default when ids differ
- `aoi_name` -> useful when both sources share stable AOI names
- `aoi_id` -> only when both sources intentionally reuse the same numeric AOI ids

## Build the HTML AOI viewer

Generate a static HTML explorer from `runtime_aoi_summary.csv`:

```bash
python python/analytics/scripts/build_runtime_aoi_html_report.py --input-csv data/exports/analytics/<timestamp>/runtime_aoi_summary.csv
```

Explicit output path:

```bash
python python/analytics/scripts/build_runtime_aoi_html_report.py --input-csv data/exports/analytics/<timestamp>/runtime_aoi_summary.csv --output-html data/exports/analytics/<timestamp>/runtime_aoi_summary_viewer.html --title "AOI360 Phase 3 Explorer"
```

The HTML viewer supports:

- filter by participant
- filter by stimulus/video
- filter by AOI, narrowed automatically to the selected stimulus
- free-text search
- direct inspection of pre-attentive metrics (`FB`, `TFF`) and sustained metrics (`FD`, `TFD`, `FC`, `Visits`)
- a checkbox-style revisits field
- `-1` sentinel values for AOIs that were not visited in the current participant/session/stimulus row

Normalize pilot participant IDs so the analytics outputs use `P01`...`P08`
instead of the internal runtime IDs:

```bash
python python/analytics/scripts/normalize_runtime_participant_ids.py --input-root data/exports/csv
```

Build the grouped `stimulus x AOI` Phase 3 means used in the manuscript:

```bash
python python/analytics/scripts/build_phase3_stimulus_aoi_tables.py --input-csv data/exports/analytics/<timestamp>/runtime_aoi_summary.csv --output-csv data/exports/analytics/<timestamp>/runtime_video_aoi_mean_metrics.csv
```

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
- `runtime_video_aoi_mean_metrics.csv`
- `runtime_video_aoi_summary.csv`
- `runtime_transition_summary.csv`
- `runtime_summary_snapshot.json`

The comparison script writes one timestamped folder under `data/exports/analytics/source_comparison/` with:

- `manual/`
- `automatic/`
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

Session-quality layer:

- `runtime_session_quality.csv` reports quality flags and issues per run
- `runtime_session_inclusion.csv` makes the inclusion/exclusion decision explicit for each chosen `--session-filter`

Main AOI metrics:

- `fb_count` -> fixations before first AOI hit (`FB`)
- `fixation_steps` -> fixation count proxy (`FC`)
- `dwell_time_ms` -> total fixation duration (`TFD`)
- `time_to_first_fixation_ms` -> time to first fixation (`TFF`)
- `visit_count` -> AOI visit count
- `has_revisits` -> whether the AOI was revisited after the first visit
- `dwell_share_of_valid_time` -> share of valid tracked time spent on the AOI
- `dwell_share_of_assigned_time` -> share of AOI-assigned time spent on the AOI

Detailed AOI rows:

- `runtime_aoi_summary.csv` now expands each `participant x session x stimulus` run against the manifest AOI list for that stimulus
- AOIs that were not visited keep their semantic metadata but export `-1` for AOI-dependent metrics such as `FB`, `TFF`, `TFD`, `FC`, and `Visits`

Grouped AOI means:

- `runtime_video_aoi_mean_metrics.csv` aggregates the detailed AOI rows by `stimulus x AOI`
- `mean_fb` -> mean fixations-before count over visited runs
- `mean_fc` -> mean fixation count over runs in which the AOI was visited
- `fd_ms` -> derived fixation duration from grouped dwell time and grouped fixation count
- `mean_tfd_ms` -> mean total fixation duration per visited run
- `mean_tff_ms` -> mean time to first fixation per visited run
- `mean_visits` -> mean AOI visit count per visited run

Transition metrics:

- `from_aoi_id` and `to_aoi_id`
- `transition_count`
- `mean_transition_gap_ms`

## Pilot reference

The completed eight-participant pilot currently has a clean analytics export at:

- `data/exports/analytics/20260525_pilot_P01_P08_clean/`

Key files from that run:

- `runtime_summary_snapshot.json`
- `runtime_participant_summary.csv`
- `runtime_video_summary.csv`
- `runtime_aoi_summary.csv`
- `runtime_video_aoi_mean_metrics.csv`
- `runtime_video_aoi_summary.csv`
- `runtime_transition_summary.csv`
- `runtime_aoi_summary_viewer.html`

## Archived pilot release

The frozen pilot release that backs the manuscript and the published Phase 3
outputs is:

- GitHub release/tag: `v1.0-pilot.1`
- Zenodo DOI: `10.5281/zenodo.20425675`

Landing pages:

- GitHub repository: `https://github.com/asanzhuerta/aoi360-eye-tracking-system`
- Zenodo record: `https://doi.org/10.5281/zenodo.20425675`
