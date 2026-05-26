from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path


PARTICIPANT_DIR_PATTERN = re.compile(r"^P\d{2}$", re.IGNORECASE)


def _iter_runtime_csvs(input_root: Path) -> list[Path]:
    csv_paths: list[Path] = []
    for participant_dir in sorted(path for path in input_root.iterdir() if path.is_dir()):
        if not PARTICIPANT_DIR_PATTERN.match(participant_dir.name):
            continue
        csv_paths.extend(sorted(participant_dir.glob("*.csv")))
    return csv_paths


def _rewrite_participant_id(csv_path: Path, participant_id: str) -> tuple[int, bool]:
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        if "participant_id" not in fieldnames:
            raise ValueError(f"'participant_id' column not found in {csv_path}")
        rows = list(reader)

    changed = False
    for row in rows:
        if row.get("participant_id") != participant_id:
            row["participant_id"] = participant_id
            changed = True

    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    return len(rows), changed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Normalize participant_id values in pilot runtime CSVs to match their PXX folder names.",
    )
    parser.add_argument(
        "--input-root",
        default="data/exports/csv",
        help="Root directory containing P01...P08 folders with runtime CSV exports.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_root = Path(args.input_root).resolve()
    if not input_root.exists():
        raise FileNotFoundError(f"Input root not found: {input_root}")

    csv_paths = _iter_runtime_csvs(input_root)
    if not csv_paths:
        raise RuntimeError(f"No participant CSVs found under: {input_root}")

    total_files = 0
    total_rows = 0
    changed_files = 0
    for csv_path in csv_paths:
        participant_id = csv_path.parent.name.upper()
        row_count, changed = _rewrite_participant_id(csv_path, participant_id)
        total_files += 1
        total_rows += row_count
        changed_files += int(changed)
        status = "updated" if changed else "ok"
        print(f"[normalize_runtime_participant_ids] {status}: {csv_path} -> {participant_id} ({row_count} rows)")

    print(
        f"[normalize_runtime_participant_ids] Completed. Files={total_files}, changed={changed_files}, rows={total_rows}"
    )


if __name__ == "__main__":
    main()
