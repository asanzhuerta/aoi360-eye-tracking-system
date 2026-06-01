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
- a preliminary manual-vs-detector IoU validation scaffold is available for the frozen test corpus
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
- `data/manual_gt/benchmark_iou/` -> manual annotation subset and IoU validation inputs
- `python/offline/scripts/diagnose_failure_taxonomy.py` -> geometry audit for the frozen test corpus
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

Important note:

- `v1.0-pilot.1` captures the frozen pilot workflow and its archived outputs.
- If the manuscript is updated to cite the later preliminary spatial IoU
  validation and the failure-taxonomy geometry diagnostics added in the
  development repository, cut a new archival release and update the DOI
  referenced by the paper accordingly.

The release workflow used to freeze the pilot build and obtain the Zenodo DOI is
documented in:

- `docs/release/github-zenodo-release-checklist.md`

## License

Unless otherwise stated, the original source code in this repository is released
under the Apache License 2.0. See [LICENSE](LICENSE).

Important note:

- bundled third-party packages, Unity samples, fonts, and other external assets
  remain subject to their own upstream license terms where applicable
- participant materials, archived outputs, and manuscript artefacts may carry
  additional citation, privacy, or reuse constraints beyond the software license

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

## Preliminary spatial IoU validation

The repository also contains a small manual ground-truth workflow for checking
detector boxes against hand-drawn boxes on 15 key frames from the frozen test
corpus:

- `data/manual_gt/benchmark_iou/frame_subset/`
- `data/manual_gt/benchmark_iou/frame_subset_manifest.csv`
- `data/manual_gt/benchmark_iou/manual_boxes.csv`
- `python/offline/scripts/annotate_manual_boxes_opencv.py`
- `python/offline/scripts/verify_spatial_iou.py`

Running the IoU validation writes timestamped summaries under:

- `data/exports/benchmarks/spatial_iou/`

## Failure-taxonomy diagnostics

To support the manuscript discussion of why `test3Lions360` underperforms the
camera-centric pilot stimuli, the repository also includes a compact geometry
diagnostic over the frozen test metadata:

- `python/offline/scripts/diagnose_failure_taxonomy.py`

The script summarises:

- AOI count per keyframe
- total AOI bounding-box coverage per keyframe
- small-target frequency (`area < 1%`)
- seam-proximity frequency (`Δu <= 0.05`)
- polar-latitude frequency (`|elevation| > 60°`)
- optional joins with `runtime_video_summary.csv` and `runtime_video_aoi_summary.csv`

The outputs are written to:

- `data/exports/diagnostics/failure_taxonomy/`

## Notes

- `docs/latex/` may be a local linked paper workspace depending on the machine setup.
- The current Phase 3 metrics are derived from the runtime fixation-level export,
  not from a continuous raw gaze sample stream.
