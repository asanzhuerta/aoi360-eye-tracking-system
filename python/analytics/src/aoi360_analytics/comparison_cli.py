from __future__ import annotations

"""CLI entry point for comparing manual and automatic AOI sources."""

import argparse
from pathlib import Path

import pandas as pd

from aoi360_analytics.source_comparison import (
    DEFAULT_COMPARISON_MATCH_FIELD,
    DEFAULT_COMPARISON_OUTPUT_ROOT,
    VALID_COMPARISON_MATCH_FIELDS,
    compare_runtime_aoi_sources,
    export_runtime_source_comparison,
)


DEFAULT_INPUT_ROOT = Path("data") / "exports" / "csv"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compare manual and automatic AOI sources over the same Unity runtime CSV exports.",
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
        "--manual-manifest-root",
        required=True,
        help="Directory containing the manual AOI manifests to reapply over the runtime CSVs.",
    )
    parser.add_argument(
        "--automatic-manifest-root",
        required=True,
        help="Directory containing the automatic AOI manifests to reapply over the runtime CSVs.",
    )
    parser.add_argument(
        "--manual-maps-root",
        default=None,
        help="Optional root folder for manual AOI PNG maps when manifests use relative paths.",
    )
    parser.add_argument(
        "--automatic-maps-root",
        default=None,
        help="Optional root folder for automatic AOI PNG maps when manifests use relative paths.",
    )
    parser.add_argument(
        "--match-field",
        default=DEFAULT_COMPARISON_MATCH_FIELD,
        choices=sorted(VALID_COMPARISON_MATCH_FIELDS),
        help=(
            "Semantic field used to compare both AOI sources. "
            f"Default: {DEFAULT_COMPARISON_MATCH_FIELD}."
        ),
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help=(
            "Output directory for both source analyses plus the comparison tables. "
            "Defaults to a timestamped folder in data/exports/analytics/source_comparison."
        ),
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    timestamp_label = pd.Timestamp.now().strftime("%Y%m%d_%H%M%S")
    resolved_output_dir = Path(args.output_dir) if args.output_dir else DEFAULT_COMPARISON_OUTPUT_ROOT / timestamp_label

    comparison_result = compare_runtime_aoi_sources(
        input_csvs=args.input_csvs,
        input_dir=args.input_dir,
        manual_manifest_root=args.manual_manifest_root,
        automatic_manifest_root=args.automatic_manifest_root,
        manual_maps_root=args.manual_maps_root,
        automatic_maps_root=args.automatic_maps_root,
        match_field=args.match_field,
    )
    export_paths = export_runtime_source_comparison(
        comparison_result,
        output_dir=resolved_output_dir,
    )

    print(f"[aoi360_compare] Manual analytics: {export_paths['manual_output_dir']}")
    print(f"[aoi360_compare] Automatic analytics: {export_paths['automatic_output_dir']}")
    print(f"[aoi360_compare] Row-wise comparison: {export_paths['comparison_rows_path']}")
    print(f"[aoi360_compare] Session alignment: {export_paths['session_alignment_path']}")
    print(f"[aoi360_compare] Category confusion: {export_paths['category_confusion_path']}")
    print(f"[aoi360_compare] Match-field confusion: {export_paths['match_field_confusion_path']}")
    print(f"[aoi360_compare] Manual video summary: {export_paths['manual_video_match_summary_path']}")
    print(f"[aoi360_compare] Automatic video summary: {export_paths['automatic_video_match_summary_path']}")
    print(f"[aoi360_compare] Video deltas: {export_paths['video_match_deltas_path']}")
    print(f"[aoi360_compare] Snapshot: {export_paths['summary_json_path']}")
