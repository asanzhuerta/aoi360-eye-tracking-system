from __future__ import annotations

"""CLI entry points for the analytics package."""

import argparse
from pathlib import Path

import pandas as pd

from aoi360_analytics.runtime_exports import analyze_runtime_exports, export_runtime_analytics


DEFAULT_OUTPUT_ROOT = Path("data") / "exports" / "analytics"
DEFAULT_INPUT_ROOT = Path("data") / "exports" / "csv"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Analyze fixation-based CSV exports from the AOI360 Unity runtime.",
    )
    parser.add_argument(
        "--input-csv",
        dest="input_csvs",
        action="append",
        help="Explicit runtime CSV to analyze. Repeat the option to include multiple files.",
    )
    parser.add_argument(
        "--input-dir",
        default=str(DEFAULT_INPUT_ROOT),
        help="Directory containing one or more runtime CSVs. Used when --input-csv is omitted. Defaults to data/exports/csv.",
    )
    parser.add_argument(
        "--manifest-root",
        default="data/processed/metadata",
        help="Directory containing AOI sequence manifests used to enrich AOI ids with names and categories.",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Output directory for normalized rows and summary tables. Defaults to a timestamped folder in data/exports/analytics.",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    timestamp_label = pd.Timestamp.now().strftime("%Y%m%d_%H%M%S")
    resolved_output_dir = Path(args.output_dir) if args.output_dir else DEFAULT_OUTPUT_ROOT / timestamp_label

    analytics_result = analyze_runtime_exports(
        input_csvs=args.input_csvs,
        input_dir=args.input_dir,
        manifest_root=args.manifest_root,
    )
    export_paths = export_runtime_analytics(
        analytics_result,
        output_dir=resolved_output_dir,
    )

    print(f"[aoi360_analytics] Normalized rows: {export_paths['raw_rows_path']}")
    print(f"[aoi360_analytics] Source file summary: {export_paths['source_file_summary_path']}")
    print(f"[aoi360_analytics] Session summary: {export_paths['session_summary_path']}")
    print(f"[aoi360_analytics] Session quality: {export_paths['session_quality_path']}")
    print(f"[aoi360_analytics] Participant summary: {export_paths['participant_summary_path']}")
    print(f"[aoi360_analytics] Video summary: {export_paths['video_summary_path']}")
    print(f"[aoi360_analytics] AOI summary: {export_paths['aoi_summary_path']}")
    print(f"[aoi360_analytics] Video x AOI summary: {export_paths['video_aoi_summary_path']}")
    print(f"[aoi360_analytics] Transition summary: {export_paths['transition_summary_path']}")
    print(f"[aoi360_analytics] Snapshot: {export_paths['summary_json_path']}")
