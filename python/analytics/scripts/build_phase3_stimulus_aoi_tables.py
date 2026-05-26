from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


VIDEO_ORDER = [
    "test1Camera360",
    "test2Camera360",
    "test3Lions360",
]


def _escape_tex(value: str) -> str:
    return (
        str(value)
        .replace("\\", "\\textbackslash{}")
        .replace("_", "\\_")
        .replace("&", "\\&")
        .replace("%", "\\%")
        .replace("#", "\\#")
    )


def build_grouped_summary(input_csv: Path) -> pd.DataFrame:
    dataframe = pd.read_csv(input_csv)
    required_columns = {
        "video_id",
        "aoi_id",
        "aoi_name",
        "aoi_category",
        "fixation_steps",
        "dwell_time_ms",
        "time_to_first_fixation_ms",
        "visit_count",
    }
    missing = required_columns.difference(dataframe.columns)
    if missing:
        missing_list = ", ".join(sorted(missing))
        raise ValueError(f"Missing required columns in {input_csv}: {missing_list}")

    grouped = (
        dataframe.groupby(["video_id", "aoi_id", "aoi_name", "aoi_category"], dropna=False, as_index=False)
        .agg(
            session_hits=("aoi_name", "size"),
            mean_fc=("fixation_steps", "mean"),
            total_fixation_steps=("fixation_steps", "sum"),
            total_dwell_time_ms=("dwell_time_ms", "sum"),
            mean_tfd_ms=("dwell_time_ms", "mean"),
            mean_tff_ms=("time_to_first_fixation_ms", "mean"),
            mean_visits=("visit_count", "mean"),
        )
    )
    grouped["fd_ms"] = grouped["total_dwell_time_ms"] / grouped["total_fixation_steps"].where(
        grouped["total_fixation_steps"] > 0,
        pd.NA,
    )
    grouped["mean_tfd_s"] = grouped["mean_tfd_ms"] / 1000.0
    grouped["mean_tff_s"] = grouped["mean_tff_ms"] / 1000.0

    grouped = grouped[
        [
            "video_id",
            "aoi_id",
            "aoi_name",
            "aoi_category",
            "session_hits",
            "mean_fc",
            "fd_ms",
            "mean_tfd_s",
            "mean_tff_s",
            "mean_visits",
        ]
    ].copy()

    grouped["video_sort"] = grouped["video_id"].apply(
        lambda value: VIDEO_ORDER.index(value) if value in VIDEO_ORDER else len(VIDEO_ORDER)
    )
    grouped.sort_values(["video_sort", "aoi_id", "aoi_name"], inplace=True, ignore_index=True)
    grouped.drop(columns=["video_sort"], inplace=True)
    return grouped


def build_latex_tables(grouped: pd.DataFrame) -> str:
    lines: list[str] = [
        "\\begin{table}[htbp]",
        "\\centering",
        "\\caption{Mean Phase~3 AOI metrics grouped by stimulus and AOI. Means are computed over participant-session runs in which the AOI was visited. FD is derived from grouped dwell time and grouped fixation count.}",
        "\\label{tab:pilot-phase3-aoi-metrics-by-stimulus}",
    ]

    for index, video_id in enumerate(VIDEO_ORDER):
        video_rows = grouped[grouped["video_id"] == video_id].copy()
        if video_rows.empty:
            continue

        if index > 0:
            lines.extend(["\\medskip"])

        lines.extend(
            [
                "\\begin{subtable}{\\textwidth}",
                "\\centering",
                f"\\caption{{\\texttt{{{_escape_tex(video_id)}}}}}",
                "\\begin{tabular}{@{}lrrrrr@{}}",
                "\\toprule",
                "AOI & FC & FD (ms) & TFD (s) & TFF (s) & Visits \\\\",
                "\\midrule",
            ]
        )

        for _, row in video_rows.iterrows():
            lines.append(
                " \\texttt{{{aoi_name}}} & {mean_fc:.2f} & {fd_ms:.1f} & {mean_tfd_s:.2f} & {mean_tff_s:.2f} & {mean_visits:.2f} \\\\".format(
                    aoi_name=_escape_tex(row["aoi_name"]),
                    mean_fc=float(row["mean_fc"]),
                    fd_ms=float(row["fd_ms"]),
                    mean_tfd_s=float(row["mean_tfd_s"]),
                    mean_tff_s=float(row["mean_tff_s"]),
                    mean_visits=float(row["mean_visits"]),
                )
            )

        lines.extend(
            [
                "\\bottomrule",
                "\\end{tabular}",
                "\\end{subtable}",
            ]
        )

    lines.append("\\end{table}")
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build grouped Phase 3 stimulus x AOI mean metrics and optional LaTeX subtables.",
    )
    parser.add_argument("--input-csv", required=True, help="Path to runtime_aoi_summary.csv")
    parser.add_argument(
        "--output-csv",
        help="Destination CSV path for grouped stimulus x AOI metrics. Defaults next to the input CSV.",
    )
    parser.add_argument(
        "--output-tex",
        help="Optional LaTeX fragment path for the stimulus-specific AOI subtables.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_csv = Path(args.input_csv).resolve()
    if not input_csv.exists():
        raise FileNotFoundError(f"Input CSV not found: {input_csv}")

    output_csv = (
        Path(args.output_csv).resolve()
        if args.output_csv
        else input_csv.with_name("runtime_video_aoi_mean_metrics.csv")
    )
    grouped = build_grouped_summary(input_csv)
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    grouped.to_csv(output_csv, index=False, encoding="utf-8")
    print(f"[build_phase3_stimulus_aoi_tables] CSV: {output_csv}")

    if args.output_tex:
        output_tex = Path(args.output_tex).resolve()
        output_tex.parent.mkdir(parents=True, exist_ok=True)
        output_tex.write_text(build_latex_tables(grouped), encoding="utf-8")
        print(f"[build_phase3_stimulus_aoi_tables] TEX: {output_tex}")


if __name__ == "__main__":
    main()
