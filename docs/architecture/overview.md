# System Architecture

This repository follows a three-part architecture:

1. Offline AOI generation in Python
2. Runtime eye tracking and AOI lookup in Unity
3. Post-hoc analytics in Python

## Design intent

The system is intentionally split so that computer vision and segmentation stay offline, while the runtime experiment remains deterministic and lightweight.

- Python offline pipeline:
  - prepares AOI maps and metadata
  - can later integrate Grounding DINO, segmentation, and tracking
- Unity runtime:
  - plays the 360 stimulus
  - reads eye tracking in real time
  - maps gaze to spherical coordinates
  - resolves AOI hits from precomputed maps
  - logs fixation-based events
- Python analytics:
  - reconstructs fixations and AOI metrics from exported CSV data

## Current runtime implementation

Phase 2 is centered on `Phase2_360Playback_VR_sampleRIG` and includes:

- skybox-based 360 playback
- OpenXR eye gaze input
- HTC eye tracker fallback
- AOI overlay rendering
- AOI lookup on equirectangular textures
- fixation commits every 250 ms
- fixation trail visualization
- CSV export for later analysis

See `docs/phase2/` for runtime-specific details.
