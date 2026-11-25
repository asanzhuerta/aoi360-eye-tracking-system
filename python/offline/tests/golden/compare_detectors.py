"""Run each detector backend on a few frames and print a hash of its CSV.

Run it once with the baseline sources on PYTHONPATH and once with the
refactored package, then compare the printed hashes. GPU inference is
deterministic for a fixed batch size on the same machine and library versions.

Usage: python compare_detectors.py <frames_dir> <out_dir> "<prompt>" [detector ...]
"""

from __future__ import annotations

import hashlib
import sys
import time
from pathlib import Path


def main() -> int:
    frames_dir, out_dir, prompt = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
    detectors = sys.argv[4:] or ["grounding_dino", "yolo_world", "owlv2"]
    out_dir.mkdir(parents=True, exist_ok=True)

    from aoi360_pipeline.detectors import detect_frames_with_backend

    for detector in detectors:
        csv_path = out_dir / f"{detector}.csv"
        start = time.perf_counter()
        detect_frames_with_backend(
            detector=detector,
            frames_dir=frames_dir,
            output_csv=csv_path,
            text_prompt=prompt,
            batch_size=1,
            inference_max_width=1920,
            inference_max_height=960,
            log_callback=lambda _message: None,
        )
        elapsed = time.perf_counter() - start
        digest = hashlib.sha256(csv_path.read_bytes()).hexdigest()[:16]
        print(f"{detector:15s} {digest} {elapsed:7.2f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
