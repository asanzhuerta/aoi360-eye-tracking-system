from __future__ import annotations

"""Post-process fixation-based CSV exports from the Unity runtime."""

import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd


RUNTIME_REQUIRED_COLUMNS = [
    "participant_id",
    "session_id",
    "video_id",
    "timestamp_ms",
    "frame_index",
    "origin_x",
    "origin_y",
    "origin_z",
    "direction_x",
    "direction_y",
    "direction_z",
    "azimuth_rad",
    "elevation_rad",
    "uv_x",
    "uv_y",
    "aoi_id",
    "aoi_confidence",
    "left_pupil_diameter",
    "right_pupil_diameter",
    "is_valid",
]

NUMERIC_COLUMNS = [
    "timestamp_ms",
    "frame_index",
    "origin_x",
    "origin_y",
    "origin_z",
    "direction_x",
    "direction_y",
    "direction_z",
    "azimuth_rad",
    "elevation_rad",
    "uv_x",
    "uv_y",
    "aoi_id",
    "aoi_confidence",
    "left_pupil_diameter",
    "right_pupil_diameter",
    "is_valid",
]

SESSION_GROUP_COLUMNS = ["participant_id", "session_id", "video_id"]
DEFAULT_FIXATION_STEP_MS = 250.0
DEFAULT_MANIFEST_GLOB = "*_aoi_sequence_manifest.json"


@dataclass(frozen=True)
class RuntimeAnalyticsResult:
    raw_rows: pd.DataFrame
    session_summary: pd.DataFrame
    aoi_summary: pd.DataFrame
    manifest_index: pd.DataFrame


def discover_runtime_csv_paths(
    *,
    input_csvs: list[str] | None = None,
    input_dir: str | Path | None = None,
) -> list[Path]:
    """Resolve runtime CSV paths from explicit files or a directory."""

    if input_csvs:
        csv_paths = [Path(path).resolve() for path in input_csvs]
    elif input_dir is not None:
        input_directory = Path(input_dir).resolve()
        if not input_directory.exists():
            raise FileNotFoundError(f"Runtime CSV directory not found: {input_directory}")
        csv_paths = sorted(input_directory.rglob("*.csv"))
    else:
        raise ValueError("Provide either input_csvs or input_dir.")

    if not csv_paths:
        raise RuntimeError("No runtime CSV files were found to analyze.")

    return csv_paths


def load_runtime_csvs(csv_paths: list[str | Path]) -> pd.DataFrame:
    """Load and normalize one or more runtime export CSV files."""

    frames: list[pd.DataFrame] = []

    for csv_path_value in csv_paths:
        csv_path = Path(csv_path_value).resolve()
        dataframe = pd.read_csv(csv_path)
        missing_columns = [column for column in RUNTIME_REQUIRED_COLUMNS if column not in dataframe.columns]
        if missing_columns:
            missing_labels = ", ".join(missing_columns)
            raise ValueError(f"Runtime CSV '{csv_path}' is missing required columns: {missing_labels}")

        dataframe = dataframe.copy()
        dataframe["source_file"] = str(csv_path)

        for column in NUMERIC_COLUMNS:
            dataframe[column] = pd.to_numeric(dataframe[column], errors="coerce")

        dataframe["participant_id"] = dataframe["participant_id"].fillna("").astype(str)
        dataframe["session_id"] = dataframe["session_id"].fillna("").astype(str)
        dataframe["video_id"] = dataframe["video_id"].fillna("").astype(str)

        frames.append(dataframe)

    combined = pd.concat(frames, ignore_index=True)
    combined.sort_values(SESSION_GROUP_COLUMNS + ["timestamp_ms", "frame_index"], inplace=True, ignore_index=True)
    return combined


def load_manifest_index(manifest_root: str | Path | None = None) -> pd.DataFrame:
    """Build a lookup table from exported AOI manifests."""

    if manifest_root is None:
        return pd.DataFrame(columns=["video_id", "aoi_id", "aoi_name", "aoi_category", "aoi_prompt", "aoi_color"])

    manifest_directory = Path(manifest_root).resolve()
    if not manifest_directory.exists():
        return pd.DataFrame(columns=["video_id", "aoi_id", "aoi_name", "aoi_category", "aoi_prompt", "aoi_color"])

    rows: list[dict[str, object]] = []
    for manifest_path in sorted(manifest_directory.glob(DEFAULT_MANIFEST_GLOB)):
        document = json.loads(manifest_path.read_text(encoding="utf-8"))
        video_name = str(document.get("video") or "")
        manifest_video_id = Path(video_name).stem if video_name else manifest_path.name.replace(
            "_aoi_sequence_manifest.json",
            "",
        )

        for entry in document.get("aois", []):
            rows.append(
                {
                    "video_id": manifest_video_id,
                    "aoi_id": int(entry.get("id", -1)),
                    "aoi_name": entry.get("name", ""),
                    "aoi_category": entry.get("category", ""),
                    "aoi_prompt": entry.get("prompt", ""),
                    "aoi_color": entry.get("color", ""),
                }
            )

    if not rows:
        return pd.DataFrame(columns=["video_id", "aoi_id", "aoi_name", "aoi_category", "aoi_prompt", "aoi_color"])

    manifest_index = pd.DataFrame(rows)
    manifest_index.drop_duplicates(subset=["video_id", "aoi_id"], inplace=True)
    return manifest_index


def estimate_fixation_step_ms(session_rows: pd.DataFrame) -> float:
    """Estimate the fixation cadence from one session/video timeline."""

    positive_deltas = (
        session_rows["timestamp_ms"]
        .sort_values()
        .diff()
        .dropna()
    )
    positive_deltas = positive_deltas[positive_deltas > 0]

    if positive_deltas.empty:
        return DEFAULT_FIXATION_STEP_MS

    return float(positive_deltas.median())


def build_session_summary(runtime_rows: pd.DataFrame) -> pd.DataFrame:
    """Compute one summary row per participant/session/video."""

    summary_rows: list[dict[str, object]] = []

    for group_key, session_rows in runtime_rows.groupby(SESSION_GROUP_COLUMNS, dropna=False):
        participant_id, session_id, video_id = group_key
        fixation_step_ms = estimate_fixation_step_ms(session_rows)
        valid_rows = session_rows[session_rows["is_valid"] == 1]

        summary_rows.append(
            {
                "participant_id": participant_id,
                "session_id": session_id,
                "video_id": video_id,
                "rows_total": int(len(session_rows)),
                "rows_valid": int(len(valid_rows)),
                "rows_invalid": int(len(session_rows) - len(valid_rows)),
                "valid_ratio": float(valid_rows.shape[0] / len(session_rows)) if len(session_rows) else 0.0,
                "fixation_step_ms_estimate": fixation_step_ms,
                "first_timestamp_ms": float(session_rows["timestamp_ms"].min()) if len(session_rows) else 0.0,
                "last_timestamp_ms": float(session_rows["timestamp_ms"].max()) if len(session_rows) else 0.0,
                "observed_span_ms": (
                    float(session_rows["timestamp_ms"].max() - session_rows["timestamp_ms"].min())
                    if len(session_rows) > 1
                    else 0.0
                ),
                "unique_aois_valid": int(valid_rows.loc[valid_rows["aoi_id"] > 0, "aoi_id"].nunique()),
                "mean_aoi_confidence_valid": float(valid_rows["aoi_confidence"].mean()) if len(valid_rows) else 0.0,
                "mean_left_pupil_diameter": float(valid_rows["left_pupil_diameter"].dropna().mean())
                if valid_rows["left_pupil_diameter"].notna().any()
                else float("nan"),
                "mean_right_pupil_diameter": float(valid_rows["right_pupil_diameter"].dropna().mean())
                if valid_rows["right_pupil_diameter"].notna().any()
                else float("nan"),
            }
        )

    return pd.DataFrame(summary_rows)


def build_aoi_summary(runtime_rows: pd.DataFrame, session_summary: pd.DataFrame) -> pd.DataFrame:
    """Compute AOI-level metrics from fixation-based runtime rows."""

    rows = runtime_rows.copy()
    rows.sort_values(SESSION_GROUP_COLUMNS + ["timestamp_ms", "frame_index"], inplace=True, ignore_index=True)
    rows["assigned_aoi_id"] = rows["aoi_id"].where((rows["is_valid"] == 1) & (rows["aoi_id"] > 0))

    session_step_lookup = session_summary.set_index(SESSION_GROUP_COLUMNS)["fixation_step_ms_estimate"].to_dict()
    session_valid_lookup = session_summary.set_index(SESSION_GROUP_COLUMNS)["rows_valid"].to_dict()

    visit_rows: list[dict[str, object]] = []
    for group_key, session_rows in rows.groupby(SESSION_GROUP_COLUMNS, dropna=False):
        fixation_step_ms = float(session_step_lookup.get(group_key, DEFAULT_FIXATION_STEP_MS))
        session_rows = session_rows.copy()
        session_rows["timestamp_gap_ms"] = session_rows["timestamp_ms"].diff().fillna(0.0)
        session_rows["new_visit"] = (
            session_rows["assigned_aoi_id"].ne(session_rows["assigned_aoi_id"].shift())
            | session_rows["timestamp_gap_ms"].gt(fixation_step_ms * 1.5)
        )
        session_rows["visit_id"] = session_rows["new_visit"].cumsum()

        assigned_rows = session_rows.dropna(subset=["assigned_aoi_id"])
        if assigned_rows.empty:
            continue

        visit_counts = assigned_rows.groupby("assigned_aoi_id")["visit_id"].nunique()
        for aoi_id, visit_count in visit_counts.items():
            visit_rows.append(
                {
                    "participant_id": group_key[0],
                    "session_id": group_key[1],
                    "video_id": group_key[2],
                    "aoi_id": int(aoi_id),
                    "visit_count": int(visit_count),
                }
            )

    visit_summary = pd.DataFrame(visit_rows)
    valid_assigned_rows = rows.dropna(subset=["assigned_aoi_id"]).copy()
    if valid_assigned_rows.empty:
        return pd.DataFrame(
            columns=[
                "participant_id",
                "session_id",
                "video_id",
                "aoi_id",
                "fixation_steps",
                "dwell_time_ms",
                "time_to_first_fixation_ms",
                "last_timestamp_ms",
                "mean_aoi_confidence",
                "first_frame_index",
                "last_frame_index",
                "visit_count",
                "share_of_valid_fixation_steps",
            ]
        )

    valid_assigned_rows["aoi_id"] = valid_assigned_rows["assigned_aoi_id"].astype(int)
    summary = (
        valid_assigned_rows
        .groupby(SESSION_GROUP_COLUMNS + ["aoi_id"], as_index=False)
        .agg(
            fixation_steps=("aoi_id", "count"),
            time_to_first_fixation_ms=("timestamp_ms", "min"),
            last_timestamp_ms=("timestamp_ms", "max"),
            mean_aoi_confidence=("aoi_confidence", "mean"),
            first_frame_index=("frame_index", "min"),
            last_frame_index=("frame_index", "max"),
            mean_left_pupil_diameter=("left_pupil_diameter", "mean"),
            mean_right_pupil_diameter=("right_pupil_diameter", "mean"),
        )
    )

    summary["fixation_step_ms_estimate"] = summary.apply(
        lambda row: float(
            session_step_lookup.get(
                (row["participant_id"], row["session_id"], row["video_id"]),
                DEFAULT_FIXATION_STEP_MS,
            )
        ),
        axis=1,
    )
    summary["dwell_time_ms"] = summary["fixation_steps"] * summary["fixation_step_ms_estimate"]
    summary["visit_count"] = 1
    if not visit_summary.empty:
        summary = summary.merge(
            visit_summary,
            on=SESSION_GROUP_COLUMNS + ["aoi_id"],
            how="left",
            suffixes=("", "_override"),
        )
        summary["visit_count"] = summary["visit_count_override"].fillna(summary["visit_count"]).astype(int)
        summary.drop(columns=["visit_count_override"], inplace=True)

    summary["share_of_valid_fixation_steps"] = summary.apply(
        lambda row: float(
            row["fixation_steps"] / session_valid_lookup.get(
                (row["participant_id"], row["session_id"], row["video_id"]),
                1,
            )
        ),
        axis=1,
    )
    return summary


def analyze_runtime_exports(
    *,
    input_csvs: list[str] | None = None,
    input_dir: str | Path | None = None,
    manifest_root: str | Path | None = None,
) -> RuntimeAnalyticsResult:
    """Run the first post-processing pass over Unity runtime CSV exports."""

    csv_paths = discover_runtime_csv_paths(input_csvs=input_csvs, input_dir=input_dir)
    raw_rows = load_runtime_csvs(csv_paths)
    session_summary = build_session_summary(raw_rows)
    aoi_summary = build_aoi_summary(raw_rows, session_summary)
    manifest_index = load_manifest_index(manifest_root)

    if not manifest_index.empty and not aoi_summary.empty:
        aoi_summary = aoi_summary.merge(
            manifest_index,
            on=["video_id", "aoi_id"],
            how="left",
        )

    return RuntimeAnalyticsResult(
        raw_rows=raw_rows,
        session_summary=session_summary,
        aoi_summary=aoi_summary,
        manifest_index=manifest_index,
    )


def export_runtime_analytics(
    analytics_result: RuntimeAnalyticsResult,
    *,
    output_dir: str | Path,
) -> dict[str, Path]:
    """Persist runtime analytics tables as CSV files plus one JSON summary."""

    output_directory = Path(output_dir).resolve()
    output_directory.mkdir(parents=True, exist_ok=True)

    raw_rows_path = output_directory / "runtime_rows_normalized.csv"
    session_summary_path = output_directory / "runtime_session_summary.csv"
    aoi_summary_path = output_directory / "runtime_aoi_summary.csv"
    summary_json_path = output_directory / "runtime_summary_snapshot.json"

    analytics_result.raw_rows.to_csv(raw_rows_path, index=False)
    analytics_result.session_summary.to_csv(session_summary_path, index=False)
    analytics_result.aoi_summary.to_csv(aoi_summary_path, index=False)

    snapshot = {
        "row_count": int(len(analytics_result.raw_rows)),
        "session_count": int(len(analytics_result.session_summary)),
        "aoi_summary_row_count": int(len(analytics_result.aoi_summary)),
        "videos": sorted(analytics_result.raw_rows["video_id"].dropna().astype(str).unique().tolist()),
    }
    summary_json_path.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")

    return {
        "raw_rows_path": raw_rows_path,
        "session_summary_path": session_summary_path,
        "aoi_summary_path": aoi_summary_path,
        "summary_json_path": summary_json_path,
    }
