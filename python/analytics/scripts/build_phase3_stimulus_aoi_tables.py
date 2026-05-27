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
        "was_visited",
        "fb_count",
        "fixation_steps",
        "dwell_time_ms",
        "time_to_first_fixation_ms",
        "visit_count",
    }
    missing = required_columns.difference(dataframe.columns)
    if missing:
        missing_list = ", ".join(sorted(missing))
        raise ValueError(f"Missing required columns in {input_csv}: {missing_list}")

    rows: list[dict[str, object]] = []
    group_columns = ["video_id", "aoi_id", "aoi_name", "aoi_category"]
    for group_key, group in dataframe.groupby(group_columns, dropna=False):
        visited_rows = group[group["was_visited"] == 1].copy()
        total_fixation_steps = float(visited_rows["fixation_steps"].sum()) if not visited_rows.empty else 0.0
        total_dwell_time_ms = float(visited_rows["dwell_time_ms"].sum()) if not visited_rows.empty else 0.0
        rows.append(
            {
                "video_id": group_key[0],
                "aoi_id": group_key[1],
                "aoi_name": group_key[2],
                "aoi_category": group_key[3],
                "session_rows_total": int(len(group)),
                "session_hits": int(visited_rows["was_visited"].sum()) if not visited_rows.empty else 0,
                "mean_fb": float(visited_rows["fb_count"].mean()) if not visited_rows.empty else -1.0,
                "mean_fc": float(visited_rows["fixation_steps"].mean()) if not visited_rows.empty else -1.0,
                "fd_ms": (total_dwell_time_ms / total_fixation_steps) if total_fixation_steps > 0 else -1.0,
                "mean_tfd_ms": float(visited_rows["dwell_time_ms"].mean()) if not visited_rows.empty else -1.0,
                "mean_tff_ms": float(visited_rows["time_to_first_fixation_ms"].mean()) if not visited_rows.empty else -1.0,
                "mean_visits": float(visited_rows["visit_count"].mean()) if not visited_rows.empty else -1.0,
            }
        )

    grouped = pd.DataFrame(rows)

    grouped["video_sort"] = grouped["video_id"].apply(
        lambda value: VIDEO_ORDER.index(value) if value in VIDEO_ORDER else len(VIDEO_ORDER)
    )
    grouped.sort_values(["video_sort", "aoi_id", "aoi_name"], inplace=True, ignore_index=True)
    grouped.drop(columns=["video_sort"], inplace=True)
    return grouped


def build_latex_tables(grouped: pd.DataFrame) -> str:
    lines: list[str] = []
    label_suffix_map = {
        "test1Camera360": "test1",
        "test2Camera360": "test2",
        "test3Lions360": "test3",
    }

    for video_id in VIDEO_ORDER:
        video_rows = grouped[grouped["video_id"] == video_id].copy()
        if video_rows.empty:
            continue

        lines.extend(
            [
                "\\begin{table}[htbp]",
                "\\centering",
                "\\scriptsize",
                (
                    "\\caption{Mean Phase~3 AOI metrics for "
                    f"\\texttt{{{_escape_tex(video_id)}}}. Means are computed over "
                    "participant-session runs in which the AOI was visited; AOIs "
                    "without visits remain at -1. FD is derived from grouped dwell "
                    "time and grouped fixation count.}"
                ),
                f"\\label{{tab:pilot-phase3-aoi-metrics-{label_suffix_map.get(video_id, _escape_tex(video_id))}}}",
                "\\begin{tabular}{@{}lrrrrrr@{}}",
                "\\toprule",
                "AOI & FB & TFF (ms) & FD (ms) & TFD (ms) & FC & Visits \\\\",
                "\\midrule",
            ]
        )

        for _, row in video_rows.iterrows():
            lines.append(
                " \\texttt{{{aoi_name}}} & {mean_fb:.2f} & {mean_tff_ms:.1f} & {fd_ms:.1f} & {mean_tfd_ms:.1f} & {mean_fc:.2f} & {mean_visits:.2f} \\\\".format(
                    aoi_name=_escape_tex(row["aoi_name"]),
                    mean_fb=float(row["mean_fb"]),
                    mean_tff_ms=float(row["mean_tff_ms"]),
                    mean_tfd_ms=float(row["mean_tfd_ms"]),
                    mean_fc=float(row["mean_fc"]),
                    fd_ms=float(row["fd_ms"]),
                    mean_visits=float(row["mean_visits"]),
                )
            )

        lines.extend(
            [
                "\\bottomrule",
                "\\end{tabular}",
                "\\end{table}",
                "",
            ]
        )
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build grouped Phase 3 stimulus x AOI mean metrics and optional LaTeX tables.",
    )
    parser.add_argument("--input-csv", required=True, help="Path to runtime_aoi_summary.csv")
    parser.add_argument(
        "--output-csv",
        help="Destination CSV path for grouped stimulus x AOI metrics. Defaults next to the input CSV.",
    )
    parser.add_argument(
        "--output-tex",
        help="Optional LaTeX fragment path for the stimulus-specific AOI tables.",
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
