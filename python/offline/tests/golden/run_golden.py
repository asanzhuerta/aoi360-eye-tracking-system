"""Golden-output harness for the offline pipeline refactor.

Runs the deterministic (model-free) stages on archived inputs and records a
SHA-256 per output file, so that a refactor can be checked for byte-identical
behaviour and timed stage by stage.

Usage:
    python tests/golden/run_golden.py --data-root <repo-with-data> --out <dir> record
    python tests/golden/run_golden.py --data-root <repo-with-data> --out <dir> check
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
GOLDEN_FILE = HERE / "golden_hashes.json"

# (video stem, detector) pairs with archived detections CSVs.
SEQUENCE_CASES = [
    ("sampleCamera360", "yolo_world"),
    ("test3Lions360", "grounding_dino"),
    ("sampleForest360", "grounding_dino"),
]
# Release defaults of rebuild_runtime_assets (sequence stage).
SEQUENCE_KWARGS = dict(
    fps=30,
    min_confidence=0.40,
    box_padding=64,
    frame_nms_iou_threshold=0.55,
    normalize_labels_to_prompt_vocab=True,
    frame_step=30,
    output_width=1024,
    output_height=512,
)
EXTRACTION_CASE = ("test3Lions360.mp4", 10, 600)  # video, every_n, max decoded frames


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _hash_tree(root: Path, out_root: Path) -> dict[str, str]:
    hashes = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(out_root).as_posix()
        if path.suffix == ".json":
            # Manifests embed absolute output paths; mask them before hashing.
            text = path.read_text(encoding="utf-8").replace(
                json.dumps(str(out_root))[1:-1], "<OUT>"
            )
            hashes[rel] = hashlib.sha256(text.encode("utf-8")).hexdigest()
        else:
            hashes[rel] = _sha256(path)
    return hashes


def run_sequences(data_root: Path, out_root: Path) -> dict[str, float]:
    from aoi360_pipeline.aoi_map_sequence_builder import build_aoi_sequence

    timings = {}
    for stem, detector in SEQUENCE_CASES:
        case_out = out_root / "sequence" / f"{stem}_{detector}"
        start = time.perf_counter()
        build_aoi_sequence(
            detections_csv=data_root / f"data/interim/detections/{stem}_{detector}_boxes.csv",
            frames_dir=data_root / f"data/frames/{stem}",
            output_maps_dir=case_out / "maps",
            output_keyframes_dir=case_out / "metadata",
            manifest_path=case_out / f"{stem}_aoi_sequence_manifest.json",
            runtime_pack_path=case_out / f"{stem}_aoi_sequence_rgb24.bin",
            video_name=f"{stem}.mp4",
            **SEQUENCE_KWARGS,
        )
        timings[f"sequence:{stem}"] = time.perf_counter() - start
    return timings


def run_extraction(data_root: Path, out_root: Path) -> dict[str, float]:
    from aoi360_pipeline.frame_extraction import extract_frames

    video, every_n, max_frames = EXTRACTION_CASE
    source = data_root / "data/input_videos" / video
    case_out = out_root / "extraction"
    start = time.perf_counter()
    extract_frames(source, case_out, every_n_frames=every_n)
    elapsed = time.perf_counter() - start
    # Keep only the first frames in the hash set to bound the golden file.
    kept = sorted(case_out.glob("*.jpg"))
    for extra in kept[max_frames // every_n :]:
        extra.unlink()
    return {f"extraction:{video}": elapsed}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["record", "check"])
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--skip-extraction", action="store_true")
    args = parser.parse_args()

    out_root = args.out.resolve()
    if out_root.exists():
        shutil.rmtree(out_root)
    out_root.mkdir(parents=True)

    timings = run_sequences(args.data_root, out_root)
    if not args.skip_extraction:
        timings.update(run_extraction(args.data_root, out_root))
    hashes = _hash_tree(out_root, out_root)

    for name, seconds in timings.items():
        print(f"{name:40s} {seconds:8.2f} s")

    if args.mode == "record":
        GOLDEN_FILE.write_text(json.dumps(hashes, indent=1, sort_keys=True), encoding="utf-8")
        print(f"Recorded {len(hashes)} hashes -> {GOLDEN_FILE}")
        return 0

    golden = json.loads(GOLDEN_FILE.read_text(encoding="utf-8"))
    if args.skip_extraction:
        golden = {k: v for k, v in golden.items() if not k.startswith("extraction/")}
    missing = sorted(set(golden) - set(hashes))
    extra = sorted(set(hashes) - set(golden))
    changed = sorted(k for k in set(golden) & set(hashes) if golden[k] != hashes[k])
    for label, items in (("missing", missing), ("extra", extra), ("changed", changed)):
        for item in items[:20]:
            print(f"{label}: {item}")
    ok = not (missing or extra or changed)
    print("GOLDEN OK" if ok else f"GOLDEN FAIL ({len(missing)} missing, {len(extra)} extra, {len(changed)} changed)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
