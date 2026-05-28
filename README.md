# AOI360 Eye Tracking System

Research system for dynamic area-of-interest (AOI) analysis in 360 video, split
into three practical phases:

- `Phase 1`: offline AOI preprocessing in Python
- `Phase 2`: Unity/OpenXR runtime for VR playback, gaze capture, AOI lookup, and CSV export
- `Phase 3`: post-processing and analytics over the runtime exports

## Current delivery state

The repository is now in a usable end-to-end state for the pilot workflow:

- a frozen three-video pilot corpus is supported in the runtime
- Unity exports fixation-level CSVs into `data/exports/csv/`
- Phase 3 generates participant-, session-, video-, AOI-, and transition-level summaries
- the pilot paper and participant materials live under `docs/`

Frozen pilot stimuli:

- `test1Camera360`
- `test2Camera360`
- `test3Lions360`

## Repository map

- `python/offline/` -> Phase 1 preprocessing and AOI asset generation
- `unity/AOI360Runtime/` -> Phase 2 Unity runtime
- `python/analytics/` -> Phase 3 analytics package
- `data/` -> input videos, processed assets, runtime exports, and analytics outputs
- `docs/phase2/` -> Unity/runtime operational documentation
- `docs/pilot_latex/` -> consent form and operator sheet for pilot sessions
- `docs/latex/` -> scientific manuscript workspace
- `experiments/model_benchmark/` -> detector benchmark material

## Recommended end-to-end workflow

1. Add or update a source video under `data/input_videos/`.
2. Regenerate its AOI assets with the offline pipeline in `python/offline/`.
3. Build or refresh the Unity player under `build/windows/AOI360Runtime/`.
4. Run the VR session and collect CSVs in `data/exports/csv/`.
5. Run Phase 3 analytics over those CSVs.
6. Optionally generate the HTML AOI explorer for inspection.

## Where to start

Phase-specific manuals:

- Phase 1: `python/offline/README.md`
- Phase 2: `docs/phase2/README.md`
- Phase 3: `python/analytics/README.md`

Operational runbooks:

- add new video and refresh Windows build: `docs/phase2/windows-build-refresh-runbook.md`
- review runtime behavior and validation flow: `docs/phase2/runtime-unity.md`

Pilot materials:

- consent form and print-ready PDFs: `docs/pilot_latex/README.md`

## Citation and archival release

The repository already includes the metadata files needed for a GitHub + Zenodo
archival release:

- `.zenodo.json` for Zenodo release metadata
- `CITATION.cff` for GitHub's citation panel

The archived pilot release is:

- GitHub release/tag: `v1.0-pilot.1`
- Zenodo DOI: [10.5281/zenodo.20425675](https://doi.org/10.5281/zenodo.20425675)

The release workflow used to freeze the pilot build and obtain the Zenodo DOI is
documented in:

- `docs/release/github-zenodo-release-checklist.md`

## Phase 2 runtime summary

The current Unity runtime supports:

- 360 video playback in VR
- OpenXR eye gaze capture with HTC VIVE fallback
- spherical gaze mapping to equirectangular coordinates
- exact-color AOI lookup from precomputed ID maps
- optional AOI overlay rendering for validation
- fixation-level CSV export with pupil diameters when available

Repository-local Windows build:

- `build/windows/AOI360Runtime/AOI360Runtime.exe`

## Phase 3 outputs

The analytics layer writes timestamped folders under `data/exports/analytics/`
and currently exports:

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

For AOI-level inspection, the repository also supports a static HTML viewer built
from `runtime_aoi_summary.csv`. The current Phase 3 viewer uses:

- participant and stimulus filters
- AOI filtering that narrows automatically to the selected stimulus
- pre-attentive metrics on the left (`FB`, `TFF`)
- sustained metrics on the right (`FD`, `TFD`, `FC`, `Visits`)
- a checkbox field that marks AOIs with revisits
- `-1` sentinel values for AOIs that were not visited in a given participant/session/stimulus row

## Pilot reference outputs

The completed eight-participant pilot currently lives under:

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

## Notes

- `docs/latex/` may be a local linked paper workspace depending on the machine setup.
- The current Phase 3 metrics are derived from the runtime fixation-level export,
  not from a continuous raw gaze sample stream.
