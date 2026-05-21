from __future__ import annotations

"""Post-process fixation-based CSV exports from the Unity runtime."""

import csv
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
DEFAULT_CONTINUITY_GAP_FACTOR = 1.5
DEFAULT_EXCLUDED_EXPORT_FOLDERS = {"analytics", "benchmarks"}
DEFAULT_SESSION_FILTER = "all"
VALID_SESSION_FILTERS = {"all", "tracking_usable", "aoi_usable"}
MIN_SESSION_ROWS_FOR_ANALYSIS = 3
MIN_VALID_RATIO_FOR_TRACKING_USABILITY = 0.5
MIN_ASSIGNED_VALID_RATIO_FOR_AOI_USABILITY = 0.2
MIN_OBSERVED_SPAN_MS_FOR_USABILITY = 1000.0
MAX_FIXATION_STEP_JITTER_RATIO = 0.25

MANIFEST_COLUMNS = ["video_id", "aoi_id", "aoi_name", "aoi_category", "aoi_prompt", "aoi_color"]
SESSION_SUMMARY_COLUMNS = [
    "participant_id",
    "session_id",
    "video_id",
    "rows_total",
    "rows_valid",
    "rows_invalid",
    "valid_ratio",
    "rows_assigned_valid",
    "assigned_valid_ratio",
    "fixation_step_ms_estimate",
    "fixation_step_jitter_ms",
    "fixation_step_jitter_ratio",
    "first_timestamp_ms",
    "last_timestamp_ms",
    "observed_span_ms",
    "session_duration_ms_estimate",
    "valid_duration_ms_estimate",
    "assigned_valid_duration_ms_estimate",
    "assigned_valid_share_of_session_duration",
    "unique_aois_valid",
    "mean_aoi_confidence_valid",
    "mean_left_pupil_diameter",
    "mean_right_pupil_diameter",
]
AOI_SUMMARY_COLUMNS = [
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
    "mean_left_pupil_diameter",
    "mean_right_pupil_diameter",
    "fixation_step_ms_estimate",
    "visit_count",
    "share_of_valid_fixation_steps",
    "dwell_share_of_valid_time",
    "dwell_share_of_assigned_time",
    "fixation_steps_per_minute_valid",
    "visit_count_per_minute_valid",
    "time_to_first_fixation_ratio",
]
PARTICIPANT_SUMMARY_COLUMNS = [
    "participant_id",
    "session_runs_total",
    "sessions_total",
    "videos_total",
    "rows_total",
    "rows_valid",
    "rows_invalid",
    "valid_ratio",
    "rows_assigned_valid",
    "assigned_valid_ratio",
    "observed_span_ms_total",
    "fixation_step_ms_median",
    "session_duration_total_ms",
    "valid_duration_total_ms",
    "assigned_valid_duration_total_ms",
    "assigned_valid_time_share",
    "unique_video_aois",
    "assigned_fixation_steps_total",
    "total_dwell_time_ms",
    "total_visit_count",
    "mean_aoi_confidence_valid",
    "mean_left_pupil_diameter",
    "mean_right_pupil_diameter",
]
VIDEO_SUMMARY_COLUMNS = [
    "video_id",
    "session_runs_total",
    "participants_total",
    "rows_total",
    "rows_valid",
    "rows_invalid",
    "valid_ratio",
    "rows_assigned_valid",
    "assigned_valid_ratio",
    "observed_span_ms_mean",
    "fixation_step_ms_median",
    "session_duration_total_ms",
    "valid_duration_total_ms",
    "assigned_valid_duration_total_ms",
    "assigned_valid_time_share",
    "mean_valid_duration_ms_per_session",
    "mean_assigned_valid_duration_ms_per_session",
    "unique_aois_observed",
    "assigned_fixation_steps_total",
    "total_dwell_time_ms",
    "mean_dwell_time_ms_per_session",
    "total_visit_count",
    "mean_aoi_confidence_valid",
    "mean_left_pupil_diameter",
    "mean_right_pupil_diameter",
]
TRANSITION_SUMMARY_COLUMNS = [
    "participant_id",
    "session_id",
    "video_id",
    "from_aoi_id",
    "to_aoi_id",
    "transition_count",
    "mean_transition_gap_ms",
    "first_transition_ms",
    "last_transition_ms",
]
SESSION_QUALITY_COLUMNS = [
    "participant_id",
    "session_id",
    "video_id",
    "source_file_count",
    "source_files",
    "rows_total",
    "rows_valid",
    "rows_assigned_valid",
    "valid_ratio",
    "assigned_valid_ratio",
    "observed_span_ms",
    "session_duration_ms_estimate",
    "fixation_step_ms_estimate",
    "fixation_step_jitter_ms",
    "fixation_step_jitter_ratio",
    "valid_duration_ms_estimate",
    "assigned_valid_duration_ms_estimate",
    "has_valid_tracking",
    "has_assigned_aois",
    "has_pupil_data",
    "is_usable_for_tracking_analysis",
    "is_usable_for_aoi_analysis",
    "quality_status",
    "quality_issue_count",
    "quality_issues",
]
SESSION_INCLUSION_COLUMNS = SESSION_QUALITY_COLUMNS + [
    "session_filter",
    "included_by_filter",
    "exclusion_reason",
]
SOURCE_FILE_SUMMARY_COLUMNS = [
    "source_file",
    "session_runs_total",
    "participants_total",
    "videos_total",
    "rows_total",
    "rows_valid",
    "rows_assigned_valid",
    "valid_ratio_mean",
    "assigned_valid_ratio_mean",
    "tracking_usable_sessions",
    "aoi_usable_sessions",
    "quality_fail_sessions",
    "quality_warn_sessions",
]
VIDEO_AOI_SUMMARY_COLUMNS = [
    "video_id",
    "aoi_id",
    "aoi_name",
    "aoi_category",
    "aoi_prompt",
    "aoi_color",
    "session_runs_total_for_video",
    "session_hit_count",
    "session_hit_ratio",
    "participants_with_hits",
    "total_fixation_steps",
    "total_dwell_time_ms",
    "total_visit_count",
    "mean_dwell_time_ms_when_hit",
    "mean_dwell_share_of_valid_time_when_hit",
    "mean_dwell_share_of_assigned_time_when_hit",
    "mean_fixation_steps_per_minute_valid_when_hit",
    "mean_visit_count_per_minute_valid_when_hit",
    "mean_time_to_first_fixation_ms_when_hit",
    "mean_time_to_first_fixation_ratio_when_hit",
]


@dataclass(frozen=True)
class RuntimeAnalyticsResult:
    raw_rows: pd.DataFrame
    source_file_summary: pd.DataFrame
    session_summary: pd.DataFrame
    session_quality: pd.DataFrame
    session_inclusion: pd.DataFrame
    participant_summary: pd.DataFrame
    video_summary: pd.DataFrame
    aoi_summary: pd.DataFrame
    video_aoi_summary: pd.DataFrame
    transition_summary: pd.DataFrame
    manifest_index: pd.DataFrame
    session_filter: str
    input_row_count: int
    input_session_count: int


def _empty_dataframe(columns: list[str]) -> pd.DataFrame:
    return pd.DataFrame(columns=columns)


def _validate_session_filter(session_filter: str) -> str:
    normalized_filter = str(session_filter or DEFAULT_SESSION_FILTER).strip()
    if normalized_filter not in VALID_SESSION_FILTERS:
        valid_filters = ", ".join(sorted(VALID_SESSION_FILTERS))
        raise ValueError(f"Unsupported session filter '{normalized_filter}'. Expected one of: {valid_filters}.")

    return normalized_filter


def _weighted_average(values: pd.Series, weights: pd.Series) -> float:
    valid_mask = values.notna() & weights.notna() & weights.gt(0)
    if not valid_mask.any():
        return float("nan")

    weighted_values = values.loc[valid_mask] * weights.loc[valid_mask]
    return float(weighted_values.sum() / weights.loc[valid_mask].sum())


def _safe_divide(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        return 0.0

    return float(numerator / denominator)


def _positive_timestamp_deltas(session_rows: pd.DataFrame) -> pd.Series:
    positive_deltas = session_rows["timestamp_ms"].sort_values().diff().dropna()
    return positive_deltas[positive_deltas > 0]


def _median_absolute_deviation(values: pd.Series) -> float:
    if values.empty:
        return 0.0

    median_value = float(values.median())
    return float((values - median_value).abs().median())


def _looks_like_runtime_export_csv(csv_path: Path) -> bool:
    try:
        with csv_path.open("r", encoding="utf-8-sig", newline="", errors="replace") as handle:
            reader = csv.reader(handle)
            header = next(reader, [])
    except OSError:
        return False

    normalized_header = {column.strip() for column in header}
    return set(RUNTIME_REQUIRED_COLUMNS).issubset(normalized_header)


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
        csv_paths = []
        for candidate_path in sorted(input_directory.rglob("*.csv")):
            relative_path = candidate_path.relative_to(input_directory)
            relative_parts = {part.lower() for part in relative_path.parts}
            if relative_parts & DEFAULT_EXCLUDED_EXPORT_FOLDERS:
                continue

            if not _looks_like_runtime_export_csv(candidate_path):
                continue

            csv_paths.append(candidate_path)
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
        return _empty_dataframe(MANIFEST_COLUMNS)

    manifest_directory = Path(manifest_root).resolve()
    if not manifest_directory.exists():
        return _empty_dataframe(MANIFEST_COLUMNS)

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
        return _empty_dataframe(MANIFEST_COLUMNS)

    manifest_index = pd.DataFrame(rows)
    manifest_index.drop_duplicates(subset=["video_id", "aoi_id"], inplace=True)
    return manifest_index


def estimate_fixation_step_ms(session_rows: pd.DataFrame) -> float:
    """Estimate the fixation cadence from one session/video timeline."""

    positive_deltas = _positive_timestamp_deltas(session_rows)

    if positive_deltas.empty:
        return DEFAULT_FIXATION_STEP_MS

    return float(positive_deltas.median())


def build_session_summary(runtime_rows: pd.DataFrame) -> pd.DataFrame:
    """Compute one summary row per participant/session/video."""

    if runtime_rows.empty:
        return _empty_dataframe(SESSION_SUMMARY_COLUMNS)

    summary_rows: list[dict[str, object]] = []

    for group_key, session_rows in runtime_rows.groupby(SESSION_GROUP_COLUMNS, dropna=False):
        participant_id, session_id, video_id = group_key
        fixation_step_ms = estimate_fixation_step_ms(session_rows)
        fixation_step_jitter_ms = _median_absolute_deviation(_positive_timestamp_deltas(session_rows))
        valid_rows = session_rows[session_rows["is_valid"] == 1]
        assigned_valid_rows = valid_rows[valid_rows["aoi_id"] > 0]
        observed_span_ms = (
            float(session_rows["timestamp_ms"].max() - session_rows["timestamp_ms"].min())
            if len(session_rows) > 1
            else 0.0
        )
        session_duration_ms_estimate = max(observed_span_ms + fixation_step_ms, fixation_step_ms)
        valid_duration_ms_estimate = float(len(valid_rows) * fixation_step_ms)
        assigned_valid_duration_ms_estimate = float(len(assigned_valid_rows) * fixation_step_ms)

        summary_rows.append(
            {
                "participant_id": participant_id,
                "session_id": session_id,
                "video_id": video_id,
                "rows_total": int(len(session_rows)),
                "rows_valid": int(len(valid_rows)),
                "rows_invalid": int(len(session_rows) - len(valid_rows)),
                "valid_ratio": float(valid_rows.shape[0] / len(session_rows)) if len(session_rows) else 0.0,
                "rows_assigned_valid": int(len(assigned_valid_rows)),
                "assigned_valid_ratio": float(len(assigned_valid_rows) / len(valid_rows)) if len(valid_rows) else 0.0,
                "fixation_step_ms_estimate": fixation_step_ms,
                "fixation_step_jitter_ms": fixation_step_jitter_ms,
                "fixation_step_jitter_ratio": _safe_divide(fixation_step_jitter_ms, fixation_step_ms),
                "first_timestamp_ms": float(session_rows["timestamp_ms"].min()) if len(session_rows) else 0.0,
                "last_timestamp_ms": float(session_rows["timestamp_ms"].max()) if len(session_rows) else 0.0,
                "observed_span_ms": observed_span_ms,
                "session_duration_ms_estimate": session_duration_ms_estimate,
                "valid_duration_ms_estimate": valid_duration_ms_estimate,
                "assigned_valid_duration_ms_estimate": assigned_valid_duration_ms_estimate,
                "assigned_valid_share_of_session_duration": _safe_divide(
                    assigned_valid_duration_ms_estimate,
                    session_duration_ms_estimate,
                ),
                "unique_aois_valid": int(assigned_valid_rows["aoi_id"].nunique()),
                "mean_aoi_confidence_valid": float(valid_rows["aoi_confidence"].mean()) if len(valid_rows) else 0.0,
                "mean_left_pupil_diameter": float(valid_rows["left_pupil_diameter"].dropna().mean())
                if valid_rows["left_pupil_diameter"].notna().any()
                else float("nan"),
                "mean_right_pupil_diameter": float(valid_rows["right_pupil_diameter"].dropna().mean())
                if valid_rows["right_pupil_diameter"].notna().any()
                else float("nan"),
            }
        )

    return pd.DataFrame(summary_rows, columns=SESSION_SUMMARY_COLUMNS)


def _prepare_assigned_rows(
    runtime_rows: pd.DataFrame,
    session_summary: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[tuple[str, str, str], float], dict[tuple[str, str, str], int]]:
    rows = runtime_rows.copy()
    rows.sort_values(SESSION_GROUP_COLUMNS + ["timestamp_ms", "frame_index"], inplace=True, ignore_index=True)
    rows["assigned_aoi_id"] = rows["aoi_id"].where((rows["is_valid"] == 1) & (rows["aoi_id"] > 0))

    session_step_lookup = session_summary.set_index(SESSION_GROUP_COLUMNS)["fixation_step_ms_estimate"].to_dict()
    session_valid_lookup = session_summary.set_index(SESSION_GROUP_COLUMNS)["rows_valid"].to_dict()
    return rows, session_step_lookup, session_valid_lookup


def build_aoi_summary(runtime_rows: pd.DataFrame, session_summary: pd.DataFrame) -> pd.DataFrame:
    """Compute AOI-level metrics from fixation-based runtime rows."""

    rows, session_step_lookup, session_valid_lookup = _prepare_assigned_rows(runtime_rows, session_summary)
    session_duration_lookup = session_summary.set_index(SESSION_GROUP_COLUMNS)["session_duration_ms_estimate"].to_dict()
    valid_duration_lookup = session_summary.set_index(SESSION_GROUP_COLUMNS)["valid_duration_ms_estimate"].to_dict()
    assigned_duration_lookup = session_summary.set_index(SESSION_GROUP_COLUMNS)[
        "assigned_valid_duration_ms_estimate"
    ].to_dict()

    visit_rows: list[dict[str, object]] = []
    for group_key, session_rows in rows.groupby(SESSION_GROUP_COLUMNS, dropna=False):
        fixation_step_ms = float(session_step_lookup.get(group_key, DEFAULT_FIXATION_STEP_MS))
        session_rows = session_rows.copy()
        session_rows["timestamp_gap_ms"] = session_rows["timestamp_ms"].diff().fillna(0.0)
        session_rows["new_visit"] = (
            session_rows["assigned_aoi_id"].ne(session_rows["assigned_aoi_id"].shift())
            | session_rows["timestamp_gap_ms"].gt(fixation_step_ms * DEFAULT_CONTINUITY_GAP_FACTOR)
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
        return _empty_dataframe(AOI_SUMMARY_COLUMNS)

    valid_assigned_rows["aoi_id"] = valid_assigned_rows["assigned_aoi_id"].astype(int)
    summary = (
        valid_assigned_rows.groupby(SESSION_GROUP_COLUMNS + ["aoi_id"], as_index=False).agg(
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
        )
        if session_valid_lookup.get((row["participant_id"], row["session_id"], row["video_id"]), 0) > 0
        else 0.0,
        axis=1,
    )
    summary["dwell_share_of_valid_time"] = summary.apply(
        lambda row: _safe_divide(
            row["dwell_time_ms"],
            float(
                valid_duration_lookup.get(
                    (row["participant_id"], row["session_id"], row["video_id"]),
                    0.0,
                )
            ),
        ),
        axis=1,
    )
    summary["dwell_share_of_assigned_time"] = summary.apply(
        lambda row: _safe_divide(
            row["dwell_time_ms"],
            float(
                assigned_duration_lookup.get(
                    (row["participant_id"], row["session_id"], row["video_id"]),
                    0.0,
                )
            ),
        ),
        axis=1,
    )
    summary["fixation_steps_per_minute_valid"] = summary.apply(
        lambda row: _safe_divide(
            row["fixation_steps"] * 60000.0,
            float(
                valid_duration_lookup.get(
                    (row["participant_id"], row["session_id"], row["video_id"]),
                    0.0,
                )
            ),
        ),
        axis=1,
    )
    summary["visit_count_per_minute_valid"] = summary.apply(
        lambda row: _safe_divide(
            row["visit_count"] * 60000.0,
            float(
                valid_duration_lookup.get(
                    (row["participant_id"], row["session_id"], row["video_id"]),
                    0.0,
                )
            ),
        ),
        axis=1,
    )
    summary["time_to_first_fixation_ratio"] = summary.apply(
        lambda row: _safe_divide(
            row["time_to_first_fixation_ms"],
            float(
                session_duration_lookup.get(
                    (row["participant_id"], row["session_id"], row["video_id"]),
                    0.0,
                )
            ),
        ),
        axis=1,
    )
    return summary[AOI_SUMMARY_COLUMNS]


def build_transition_summary(runtime_rows: pd.DataFrame, session_summary: pd.DataFrame) -> pd.DataFrame:
    """Count AOI-to-AOI transitions within each participant/session/video timeline."""

    rows, session_step_lookup, _ = _prepare_assigned_rows(runtime_rows, session_summary)
    transition_rows: list[dict[str, object]] = []

    for group_key, session_rows in rows.groupby(SESSION_GROUP_COLUMNS, dropna=False):
        fixation_step_ms = float(session_step_lookup.get(group_key, DEFAULT_FIXATION_STEP_MS))
        assigned_rows = session_rows.dropna(subset=["assigned_aoi_id"]).copy()
        if len(assigned_rows) < 2:
            continue

        assigned_rows["next_aoi_id"] = assigned_rows["assigned_aoi_id"].shift(-1)
        assigned_rows["next_timestamp_ms"] = assigned_rows["timestamp_ms"].shift(-1)
        assigned_rows["transition_gap_ms"] = assigned_rows["next_timestamp_ms"] - assigned_rows["timestamp_ms"]

        transitions = assigned_rows[
            assigned_rows["next_aoi_id"].notna()
            & assigned_rows["assigned_aoi_id"].ne(assigned_rows["next_aoi_id"])
            & assigned_rows["transition_gap_ms"].gt(0)
            & assigned_rows["transition_gap_ms"].le(fixation_step_ms * DEFAULT_CONTINUITY_GAP_FACTOR)
        ].copy()
        if transitions.empty:
            continue

        transitions["from_aoi_id"] = transitions["assigned_aoi_id"].astype(int)
        transitions["to_aoi_id"] = transitions["next_aoi_id"].astype(int)
        grouped = (
            transitions.groupby(["from_aoi_id", "to_aoi_id"], as_index=False).agg(
                transition_count=("from_aoi_id", "count"),
                mean_transition_gap_ms=("transition_gap_ms", "mean"),
                first_transition_ms=("timestamp_ms", "min"),
                last_transition_ms=("timestamp_ms", "max"),
            )
        )

        for record in grouped.to_dict(orient="records"):
            transition_rows.append(
                {
                    "participant_id": group_key[0],
                    "session_id": group_key[1],
                    "video_id": group_key[2],
                    **record,
                }
            )

    if not transition_rows:
        return _empty_dataframe(TRANSITION_SUMMARY_COLUMNS)

    return pd.DataFrame(transition_rows, columns=TRANSITION_SUMMARY_COLUMNS)


def build_participant_summary(session_summary: pd.DataFrame, aoi_summary: pd.DataFrame) -> pd.DataFrame:
    """Aggregate runtime quality and AOI engagement metrics per participant."""

    if session_summary.empty:
        return _empty_dataframe(PARTICIPANT_SUMMARY_COLUMNS)

    summary = (
        session_summary.groupby("participant_id", as_index=False).agg(
            session_runs_total=("video_id", "size"),
            sessions_total=("session_id", "nunique"),
            videos_total=("video_id", "nunique"),
            rows_total=("rows_total", "sum"),
            rows_valid=("rows_valid", "sum"),
            rows_invalid=("rows_invalid", "sum"),
            rows_assigned_valid=("rows_assigned_valid", "sum"),
            observed_span_ms_total=("observed_span_ms", "sum"),
            fixation_step_ms_median=("fixation_step_ms_estimate", "median"),
            session_duration_total_ms=("session_duration_ms_estimate", "sum"),
            valid_duration_total_ms=("valid_duration_ms_estimate", "sum"),
            assigned_valid_duration_total_ms=("assigned_valid_duration_ms_estimate", "sum"),
        )
    )
    summary["valid_ratio"] = summary["rows_valid"] / summary["rows_total"]
    summary["assigned_valid_ratio"] = summary["rows_assigned_valid"] / summary["rows_valid"].where(
        summary["rows_valid"] > 0,
        1,
    )
    summary["assigned_valid_time_share"] = summary.apply(
        lambda row: _safe_divide(
            row["assigned_valid_duration_total_ms"],
            row["valid_duration_total_ms"],
        ),
        axis=1,
    )

    weighted_quality_rows: list[dict[str, object]] = []
    for participant_id, group in session_summary.groupby("participant_id", dropna=False):
        weighted_quality_rows.append(
            {
                "participant_id": participant_id,
                "mean_aoi_confidence_valid": _weighted_average(
                    group["mean_aoi_confidence_valid"],
                    group["rows_valid"],
                ),
                "mean_left_pupil_diameter": _weighted_average(
                    group["mean_left_pupil_diameter"],
                    group["rows_valid"],
                ),
                "mean_right_pupil_diameter": _weighted_average(
                    group["mean_right_pupil_diameter"],
                    group["rows_valid"],
                ),
            }
        )
    summary = summary.merge(pd.DataFrame(weighted_quality_rows), on="participant_id", how="left")

    if aoi_summary.empty:
        summary["unique_video_aois"] = 0
        summary["assigned_fixation_steps_total"] = 0
        summary["total_dwell_time_ms"] = 0.0
        summary["total_visit_count"] = 0
        return summary[PARTICIPANT_SUMMARY_COLUMNS]

    enriched = aoi_summary.copy()
    enriched["video_aoi_key"] = enriched["video_id"].astype(str) + "::" + enriched["aoi_id"].astype(str)
    aoi_aggregate = (
        enriched.groupby("participant_id", as_index=False).agg(
            unique_video_aois=("video_aoi_key", "nunique"),
            assigned_fixation_steps_total=("fixation_steps", "sum"),
            total_dwell_time_ms=("dwell_time_ms", "sum"),
            total_visit_count=("visit_count", "sum"),
        )
    )
    summary = summary.merge(aoi_aggregate, on="participant_id", how="left")
    summary[["unique_video_aois", "assigned_fixation_steps_total", "total_visit_count"]] = (
        summary[["unique_video_aois", "assigned_fixation_steps_total", "total_visit_count"]]
        .fillna(0)
        .astype(int)
    )
    summary["total_dwell_time_ms"] = summary["total_dwell_time_ms"].fillna(0.0)
    return summary[PARTICIPANT_SUMMARY_COLUMNS]


def build_video_summary(session_summary: pd.DataFrame, aoi_summary: pd.DataFrame) -> pd.DataFrame:
    """Aggregate runtime quality and AOI engagement metrics per video stimulus."""

    if session_summary.empty:
        return _empty_dataframe(VIDEO_SUMMARY_COLUMNS)

    summary = (
        session_summary.groupby("video_id", as_index=False).agg(
            session_runs_total=("participant_id", "size"),
            participants_total=("participant_id", "nunique"),
            rows_total=("rows_total", "sum"),
            rows_valid=("rows_valid", "sum"),
            rows_invalid=("rows_invalid", "sum"),
            rows_assigned_valid=("rows_assigned_valid", "sum"),
            observed_span_ms_mean=("observed_span_ms", "mean"),
            fixation_step_ms_median=("fixation_step_ms_estimate", "median"),
            session_duration_total_ms=("session_duration_ms_estimate", "sum"),
            valid_duration_total_ms=("valid_duration_ms_estimate", "sum"),
            assigned_valid_duration_total_ms=("assigned_valid_duration_ms_estimate", "sum"),
        )
    )
    summary["valid_ratio"] = summary["rows_valid"] / summary["rows_total"]
    summary["assigned_valid_ratio"] = summary["rows_assigned_valid"] / summary["rows_valid"].where(
        summary["rows_valid"] > 0,
        1,
    )
    summary["assigned_valid_time_share"] = summary.apply(
        lambda row: _safe_divide(
            row["assigned_valid_duration_total_ms"],
            row["valid_duration_total_ms"],
        ),
        axis=1,
    )
    summary["mean_valid_duration_ms_per_session"] = summary.apply(
        lambda row: _safe_divide(
            row["valid_duration_total_ms"],
            row["session_runs_total"],
        ),
        axis=1,
    )
    summary["mean_assigned_valid_duration_ms_per_session"] = summary.apply(
        lambda row: _safe_divide(
            row["assigned_valid_duration_total_ms"],
            row["session_runs_total"],
        ),
        axis=1,
    )

    weighted_quality_rows: list[dict[str, object]] = []
    for video_id, group in session_summary.groupby("video_id", dropna=False):
        weighted_quality_rows.append(
            {
                "video_id": video_id,
                "mean_aoi_confidence_valid": _weighted_average(
                    group["mean_aoi_confidence_valid"],
                    group["rows_valid"],
                ),
                "mean_left_pupil_diameter": _weighted_average(
                    group["mean_left_pupil_diameter"],
                    group["rows_valid"],
                ),
                "mean_right_pupil_diameter": _weighted_average(
                    group["mean_right_pupil_diameter"],
                    group["rows_valid"],
                ),
            }
        )
    summary = summary.merge(pd.DataFrame(weighted_quality_rows), on="video_id", how="left")

    if aoi_summary.empty:
        summary["unique_aois_observed"] = 0
        summary["assigned_fixation_steps_total"] = 0
        summary["total_dwell_time_ms"] = 0.0
        summary["mean_dwell_time_ms_per_session"] = 0.0
        summary["total_visit_count"] = 0
        return summary[VIDEO_SUMMARY_COLUMNS]

    aoi_aggregate = (
        aoi_summary.groupby("video_id", as_index=False).agg(
            unique_aois_observed=("aoi_id", "nunique"),
            assigned_fixation_steps_total=("fixation_steps", "sum"),
            total_dwell_time_ms=("dwell_time_ms", "sum"),
            total_visit_count=("visit_count", "sum"),
        )
    )
    summary = summary.merge(aoi_aggregate, on="video_id", how="left")
    summary[["unique_aois_observed", "assigned_fixation_steps_total", "total_visit_count"]] = (
        summary[["unique_aois_observed", "assigned_fixation_steps_total", "total_visit_count"]]
        .fillna(0)
        .astype(int)
    )
    summary["total_dwell_time_ms"] = summary["total_dwell_time_ms"].fillna(0.0)
    summary["mean_dwell_time_ms_per_session"] = summary["total_dwell_time_ms"] / summary["session_runs_total"].where(
        summary["session_runs_total"] > 0,
        1,
    )
    return summary[VIDEO_SUMMARY_COLUMNS]


def _enrich_aoi_summary(aoi_summary: pd.DataFrame, manifest_index: pd.DataFrame) -> pd.DataFrame:
    if manifest_index.empty or aoi_summary.empty:
        return aoi_summary

    return aoi_summary.merge(manifest_index, on=["video_id", "aoi_id"], how="left")


def _enrich_transition_summary(transition_summary: pd.DataFrame, manifest_index: pd.DataFrame) -> pd.DataFrame:
    if manifest_index.empty or transition_summary.empty:
        return transition_summary

    from_index = manifest_index.rename(
        columns={
            "aoi_id": "from_aoi_id",
            "aoi_name": "from_aoi_name",
            "aoi_category": "from_aoi_category",
            "aoi_prompt": "from_aoi_prompt",
            "aoi_color": "from_aoi_color",
        }
    )
    to_index = manifest_index.rename(
        columns={
            "aoi_id": "to_aoi_id",
            "aoi_name": "to_aoi_name",
            "aoi_category": "to_aoi_category",
            "aoi_prompt": "to_aoi_prompt",
            "aoi_color": "to_aoi_color",
        }
    )

    enriched = transition_summary.merge(
        from_index[
            [
                "video_id",
                "from_aoi_id",
                "from_aoi_name",
                "from_aoi_category",
                "from_aoi_prompt",
                "from_aoi_color",
            ]
        ],
        on=["video_id", "from_aoi_id"],
        how="left",
    )
    enriched = enriched.merge(
        to_index[
            [
                "video_id",
                "to_aoi_id",
                "to_aoi_name",
                "to_aoi_category",
                "to_aoi_prompt",
                "to_aoi_color",
            ]
        ],
        on=["video_id", "to_aoi_id"],
        how="left",
    )
    return enriched


def build_session_quality_report(runtime_rows: pd.DataFrame, session_summary: pd.DataFrame) -> pd.DataFrame:
    """Assign practical quality heuristics to each participant/session/video run."""

    if runtime_rows.empty or session_summary.empty:
        return _empty_dataframe(SESSION_QUALITY_COLUMNS)

    source_lookup_rows = (
        runtime_rows[SESSION_GROUP_COLUMNS + ["source_file"]]
        .drop_duplicates()
        .groupby(SESSION_GROUP_COLUMNS, dropna=False)["source_file"]
        .agg(lambda values: sorted({str(value) for value in values if str(value)}))
    )
    source_lookup = source_lookup_rows.to_dict()

    quality_rows: list[dict[str, object]] = []
    for session_record in session_summary.to_dict(orient="records"):
        group_key = (
            session_record["participant_id"],
            session_record["session_id"],
            session_record["video_id"],
        )
        source_files = source_lookup.get(group_key, [])

        has_valid_tracking = session_record["rows_valid"] > 0
        has_assigned_aois = session_record["rows_assigned_valid"] > 0
        has_pupil_data = not (
            pd.isna(session_record["mean_left_pupil_diameter"])
            and pd.isna(session_record["mean_right_pupil_diameter"])
        )

        quality_issues: list[str] = []
        if session_record["rows_total"] < MIN_SESSION_ROWS_FOR_ANALYSIS:
            quality_issues.append("too_few_rows")
        if not has_valid_tracking:
            quality_issues.append("no_valid_tracking")
        elif session_record["valid_ratio"] < MIN_VALID_RATIO_FOR_TRACKING_USABILITY:
            quality_issues.append("low_valid_tracking")
        if session_record["observed_span_ms"] < MIN_OBSERVED_SPAN_MS_FOR_USABILITY:
            quality_issues.append("short_observation")
        if (
            session_record["rows_total"] >= MIN_SESSION_ROWS_FOR_ANALYSIS
            and session_record["fixation_step_jitter_ratio"] > MAX_FIXATION_STEP_JITTER_RATIO
        ):
            quality_issues.append("unstable_fixation_cadence")
        if not has_assigned_aois:
            quality_issues.append("no_assigned_aois")
        elif session_record["assigned_valid_ratio"] < MIN_ASSIGNED_VALID_RATIO_FOR_AOI_USABILITY:
            quality_issues.append("low_aoi_assignment")
        if not has_pupil_data:
            quality_issues.append("no_pupil_data")

        is_usable_for_tracking_analysis = (
            session_record["rows_total"] >= MIN_SESSION_ROWS_FOR_ANALYSIS
            and has_valid_tracking
            and session_record["valid_ratio"] >= MIN_VALID_RATIO_FOR_TRACKING_USABILITY
            and session_record["observed_span_ms"] >= MIN_OBSERVED_SPAN_MS_FOR_USABILITY
            and session_record["fixation_step_jitter_ratio"] <= MAX_FIXATION_STEP_JITTER_RATIO
        )
        is_usable_for_aoi_analysis = (
            is_usable_for_tracking_analysis
            and has_assigned_aois
            and session_record["assigned_valid_ratio"] >= MIN_ASSIGNED_VALID_RATIO_FOR_AOI_USABILITY
        )

        if "too_few_rows" in quality_issues or "no_valid_tracking" in quality_issues:
            quality_status = "fail"
        elif quality_issues:
            quality_status = "warn"
        else:
            quality_status = "pass"

        quality_rows.append(
            {
                "participant_id": session_record["participant_id"],
                "session_id": session_record["session_id"],
                "video_id": session_record["video_id"],
                "source_file_count": len(source_files),
                "source_files": ";".join(source_files),
                "rows_total": session_record["rows_total"],
                "rows_valid": session_record["rows_valid"],
                "rows_assigned_valid": session_record["rows_assigned_valid"],
                "valid_ratio": session_record["valid_ratio"],
                "assigned_valid_ratio": session_record["assigned_valid_ratio"],
                "observed_span_ms": session_record["observed_span_ms"],
                "session_duration_ms_estimate": session_record["session_duration_ms_estimate"],
                "fixation_step_ms_estimate": session_record["fixation_step_ms_estimate"],
                "fixation_step_jitter_ms": session_record["fixation_step_jitter_ms"],
                "fixation_step_jitter_ratio": session_record["fixation_step_jitter_ratio"],
                "valid_duration_ms_estimate": session_record["valid_duration_ms_estimate"],
                "assigned_valid_duration_ms_estimate": session_record["assigned_valid_duration_ms_estimate"],
                "has_valid_tracking": bool(has_valid_tracking),
                "has_assigned_aois": bool(has_assigned_aois),
                "has_pupil_data": bool(has_pupil_data),
                "is_usable_for_tracking_analysis": bool(is_usable_for_tracking_analysis),
                "is_usable_for_aoi_analysis": bool(is_usable_for_aoi_analysis),
                "quality_status": quality_status,
                "quality_issue_count": len(quality_issues),
                "quality_issues": ";".join(quality_issues),
            }
        )

    return pd.DataFrame(quality_rows, columns=SESSION_QUALITY_COLUMNS)


def build_session_inclusion_report(
    session_quality: pd.DataFrame,
    *,
    session_filter: str = DEFAULT_SESSION_FILTER,
) -> pd.DataFrame:
    """Mark which session/video runs are included under one analysis filter."""

    normalized_filter = _validate_session_filter(session_filter)
    if session_quality.empty:
        return _empty_dataframe(SESSION_INCLUSION_COLUMNS)

    inclusion = session_quality.copy()
    if normalized_filter == "all":
        inclusion["included_by_filter"] = True
        inclusion["exclusion_reason"] = ""
    elif normalized_filter == "tracking_usable":
        inclusion["included_by_filter"] = inclusion["is_usable_for_tracking_analysis"].fillna(False).astype(bool)
        inclusion["exclusion_reason"] = inclusion["included_by_filter"].map(
            lambda is_included: "" if is_included else "not_tracking_usable"
        )
    else:
        inclusion["included_by_filter"] = inclusion["is_usable_for_aoi_analysis"].fillna(False).astype(bool)
        inclusion["exclusion_reason"] = inclusion["included_by_filter"].map(
            lambda is_included: "" if is_included else "not_aoi_usable"
        )

    inclusion["session_filter"] = normalized_filter
    return inclusion[SESSION_INCLUSION_COLUMNS]


def filter_runtime_rows_by_session_inclusion(
    runtime_rows: pd.DataFrame,
    session_inclusion: pd.DataFrame,
) -> pd.DataFrame:
    """Keep only the participant/session/video runs included by the chosen filter."""

    if runtime_rows.empty or session_inclusion.empty:
        return runtime_rows.iloc[0:0].copy()

    included_sessions = session_inclusion[session_inclusion["included_by_filter"]]
    if included_sessions.empty:
        return runtime_rows.iloc[0:0].copy()

    row_index = pd.MultiIndex.from_frame(runtime_rows[SESSION_GROUP_COLUMNS])
    included_index = pd.MultiIndex.from_frame(included_sessions[SESSION_GROUP_COLUMNS].drop_duplicates())
    return runtime_rows.loc[row_index.isin(included_index)].copy()


def build_source_file_summary(runtime_rows: pd.DataFrame, session_quality: pd.DataFrame) -> pd.DataFrame:
    """Summarize runtime exports by source CSV file for quick ingestion QA."""

    if runtime_rows.empty:
        return _empty_dataframe(SOURCE_FILE_SUMMARY_COLUMNS)

    rows = runtime_rows.copy()
    rows["valid_flag"] = (rows["is_valid"] == 1).astype(int)
    rows["assigned_valid_flag"] = ((rows["is_valid"] == 1) & (rows["aoi_id"] > 0)).astype(int)
    row_summary = (
        rows.groupby("source_file", as_index=False).agg(
            rows_total=("source_file", "size"),
            rows_valid=("valid_flag", "sum"),
            rows_assigned_valid=("assigned_valid_flag", "sum"),
        )
    )

    if session_quality.empty:
        row_summary["session_runs_total"] = 0
        row_summary["participants_total"] = 0
        row_summary["videos_total"] = 0
        row_summary["valid_ratio_mean"] = 0.0
        row_summary["assigned_valid_ratio_mean"] = 0.0
        row_summary["tracking_usable_sessions"] = 0
        row_summary["aoi_usable_sessions"] = 0
        row_summary["quality_fail_sessions"] = 0
        row_summary["quality_warn_sessions"] = 0
        return row_summary[SOURCE_FILE_SUMMARY_COLUMNS]

    session_sources = runtime_rows[SESSION_GROUP_COLUMNS + ["source_file"]].drop_duplicates()
    session_sources = session_sources.merge(
        session_quality[
            SESSION_GROUP_COLUMNS
            + [
                "valid_ratio",
                "assigned_valid_ratio",
                "is_usable_for_tracking_analysis",
                "is_usable_for_aoi_analysis",
                "quality_status",
            ]
        ],
        on=SESSION_GROUP_COLUMNS,
        how="left",
    )
    session_summary = (
        session_sources.groupby("source_file", as_index=False).agg(
            session_runs_total=("participant_id", "size"),
            participants_total=("participant_id", "nunique"),
            videos_total=("video_id", "nunique"),
            valid_ratio_mean=("valid_ratio", "mean"),
            assigned_valid_ratio_mean=("assigned_valid_ratio", "mean"),
            tracking_usable_sessions=("is_usable_for_tracking_analysis", "sum"),
            aoi_usable_sessions=("is_usable_for_aoi_analysis", "sum"),
            quality_fail_sessions=("quality_status", lambda values: int((values == "fail").sum())),
            quality_warn_sessions=("quality_status", lambda values: int((values == "warn").sum())),
        )
    )

    summary = row_summary.merge(session_summary, on="source_file", how="left")
    int_columns = [
        "rows_total",
        "rows_valid",
        "rows_assigned_valid",
        "session_runs_total",
        "participants_total",
        "videos_total",
        "tracking_usable_sessions",
        "aoi_usable_sessions",
        "quality_fail_sessions",
        "quality_warn_sessions",
    ]
    summary[int_columns] = summary[int_columns].fillna(0).astype(int)
    summary["valid_ratio_mean"] = summary["valid_ratio_mean"].fillna(0.0)
    summary["assigned_valid_ratio_mean"] = summary["assigned_valid_ratio_mean"].fillna(0.0)
    return summary[SOURCE_FILE_SUMMARY_COLUMNS]


def build_video_aoi_summary(aoi_summary: pd.DataFrame, session_summary: pd.DataFrame) -> pd.DataFrame:
    """Aggregate AOI engagement by video to support manual-vs-automatic comparisons."""

    if aoi_summary.empty or session_summary.empty:
        return _empty_dataframe(VIDEO_AOI_SUMMARY_COLUMNS)

    rows = aoi_summary.copy()
    for column in ["aoi_name", "aoi_category", "aoi_prompt", "aoi_color"]:
        if column not in rows.columns:
            rows[column] = ""

    summary = (
        rows.groupby(
            ["video_id", "aoi_id", "aoi_name", "aoi_category", "aoi_prompt", "aoi_color"],
            as_index=False,
            dropna=False,
        ).agg(
            session_hit_count=("participant_id", "size"),
            participants_with_hits=("participant_id", "nunique"),
            total_fixation_steps=("fixation_steps", "sum"),
            total_dwell_time_ms=("dwell_time_ms", "sum"),
            total_visit_count=("visit_count", "sum"),
            mean_dwell_time_ms_when_hit=("dwell_time_ms", "mean"),
            mean_dwell_share_of_valid_time_when_hit=("dwell_share_of_valid_time", "mean"),
            mean_dwell_share_of_assigned_time_when_hit=("dwell_share_of_assigned_time", "mean"),
            mean_fixation_steps_per_minute_valid_when_hit=("fixation_steps_per_minute_valid", "mean"),
            mean_visit_count_per_minute_valid_when_hit=("visit_count_per_minute_valid", "mean"),
            mean_time_to_first_fixation_ms_when_hit=("time_to_first_fixation_ms", "mean"),
            mean_time_to_first_fixation_ratio_when_hit=("time_to_first_fixation_ratio", "mean"),
        )
    )

    session_totals = (
        session_summary.groupby("video_id", as_index=False)
        .agg(session_runs_total_for_video=("participant_id", "size"))
    )
    summary = summary.merge(session_totals, on="video_id", how="left")
    summary["session_runs_total_for_video"] = summary["session_runs_total_for_video"].fillna(0).astype(int)
    summary["session_hit_ratio"] = summary.apply(
        lambda row: _safe_divide(row["session_hit_count"], row["session_runs_total_for_video"]),
        axis=1,
    )
    return summary[VIDEO_AOI_SUMMARY_COLUMNS]


def analyze_runtime_exports(
    *,
    input_csvs: list[str] | None = None,
    input_dir: str | Path | None = None,
    manifest_root: str | Path | None = None,
    session_filter: str = DEFAULT_SESSION_FILTER,
) -> RuntimeAnalyticsResult:
    """Run the first post-processing pass over Unity runtime CSV exports."""

    csv_paths = discover_runtime_csv_paths(input_csvs=input_csvs, input_dir=input_dir)
    raw_rows = load_runtime_csvs(csv_paths)
    return analyze_runtime_rows(
        raw_rows,
        manifest_root=manifest_root,
        session_filter=session_filter,
    )


def analyze_runtime_rows(
    runtime_rows: pd.DataFrame,
    *,
    manifest_root: str | Path | None = None,
    session_filter: str = DEFAULT_SESSION_FILTER,
) -> RuntimeAnalyticsResult:
    """Run the Phase 3 analytics stack over already loaded runtime rows."""

    normalized_filter = _validate_session_filter(session_filter)
    input_rows = runtime_rows.copy()
    input_row_count = int(len(input_rows))
    input_session_summary = build_session_summary(input_rows)
    input_session_quality = build_session_quality_report(input_rows, input_session_summary)
    session_inclusion = build_session_inclusion_report(
        input_session_quality,
        session_filter=normalized_filter,
    )

    raw_rows = filter_runtime_rows_by_session_inclusion(input_rows, session_inclusion)
    session_summary = build_session_summary(raw_rows)
    session_quality = (
        session_inclusion[session_inclusion["included_by_filter"]]
        .drop(columns=["session_filter", "included_by_filter", "exclusion_reason"])
        .reset_index(drop=True)
    )
    source_file_summary = build_source_file_summary(raw_rows, session_quality)
    aoi_summary = build_aoi_summary(raw_rows, session_summary)
    participant_summary = build_participant_summary(session_summary, aoi_summary)
    video_summary = build_video_summary(session_summary, aoi_summary)
    transition_summary = build_transition_summary(raw_rows, session_summary)
    manifest_index = load_manifest_index(manifest_root)

    aoi_summary = _enrich_aoi_summary(aoi_summary, manifest_index)
    video_aoi_summary = build_video_aoi_summary(aoi_summary, session_summary)
    transition_summary = _enrich_transition_summary(transition_summary, manifest_index)

    return RuntimeAnalyticsResult(
        raw_rows=raw_rows,
        source_file_summary=source_file_summary,
        session_summary=session_summary,
        session_quality=session_quality,
        session_inclusion=session_inclusion,
        participant_summary=participant_summary,
        video_summary=video_summary,
        aoi_summary=aoi_summary,
        video_aoi_summary=video_aoi_summary,
        transition_summary=transition_summary,
        manifest_index=manifest_index,
        session_filter=normalized_filter,
        input_row_count=input_row_count,
        input_session_count=int(len(input_session_summary)),
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
    source_file_summary_path = output_directory / "runtime_source_file_summary.csv"
    session_summary_path = output_directory / "runtime_session_summary.csv"
    session_quality_path = output_directory / "runtime_session_quality.csv"
    session_inclusion_path = output_directory / "runtime_session_inclusion.csv"
    participant_summary_path = output_directory / "runtime_participant_summary.csv"
    video_summary_path = output_directory / "runtime_video_summary.csv"
    aoi_summary_path = output_directory / "runtime_aoi_summary.csv"
    video_aoi_summary_path = output_directory / "runtime_video_aoi_summary.csv"
    transition_summary_path = output_directory / "runtime_transition_summary.csv"
    summary_json_path = output_directory / "runtime_summary_snapshot.json"

    analytics_result.raw_rows.to_csv(raw_rows_path, index=False)
    analytics_result.source_file_summary.to_csv(source_file_summary_path, index=False)
    analytics_result.session_summary.to_csv(session_summary_path, index=False)
    analytics_result.session_quality.to_csv(session_quality_path, index=False)
    analytics_result.session_inclusion.to_csv(session_inclusion_path, index=False)
    analytics_result.participant_summary.to_csv(participant_summary_path, index=False)
    analytics_result.video_summary.to_csv(video_summary_path, index=False)
    analytics_result.aoi_summary.to_csv(aoi_summary_path, index=False)
    analytics_result.video_aoi_summary.to_csv(video_aoi_summary_path, index=False)
    analytics_result.transition_summary.to_csv(transition_summary_path, index=False)

    snapshot = {
        "session_filter": analytics_result.session_filter,
        "input_row_count": analytics_result.input_row_count,
        "row_count": int(len(analytics_result.raw_rows)),
        "source_file_count": int(analytics_result.raw_rows["source_file"].dropna().astype(str).nunique()),
        "input_session_count": analytics_result.input_session_count,
        "participant_count": int(analytics_result.raw_rows["participant_id"].dropna().astype(str).nunique()),
        "session_count": int(len(analytics_result.session_summary)),
        "included_session_count": int(analytics_result.session_inclusion["included_by_filter"].sum())
        if not analytics_result.session_inclusion.empty
        else 0,
        "excluded_session_count": int((~analytics_result.session_inclusion["included_by_filter"]).sum())
        if not analytics_result.session_inclusion.empty
        else 0,
        "video_count": int(analytics_result.raw_rows["video_id"].dropna().astype(str).nunique()),
        "session_quality_row_count": int(len(analytics_result.session_quality)),
        "session_inclusion_row_count": int(len(analytics_result.session_inclusion)),
        "aoi_summary_row_count": int(len(analytics_result.aoi_summary)),
        "video_aoi_summary_row_count": int(len(analytics_result.video_aoi_summary)),
        "transition_row_count": int(len(analytics_result.transition_summary)),
        "mean_valid_ratio": float(analytics_result.session_summary["valid_ratio"].mean())
        if not analytics_result.session_summary.empty
        else 0.0,
        "mean_assigned_valid_ratio": float(analytics_result.session_summary["assigned_valid_ratio"].mean())
        if not analytics_result.session_summary.empty
        else 0.0,
        "mean_fixation_step_ms": float(analytics_result.session_summary["fixation_step_ms_estimate"].mean())
        if not analytics_result.session_summary.empty
        else DEFAULT_FIXATION_STEP_MS,
        "tracking_usable_session_count": int(
            analytics_result.session_quality["is_usable_for_tracking_analysis"].sum()
        )
        if not analytics_result.session_quality.empty
        else 0,
        "aoi_usable_session_count": int(
            analytics_result.session_quality["is_usable_for_aoi_analysis"].sum()
        )
        if not analytics_result.session_quality.empty
        else 0,
        "quality_status_counts": analytics_result.session_quality["quality_status"].value_counts().to_dict()
        if not analytics_result.session_quality.empty
        else {},
        "videos": sorted(analytics_result.raw_rows["video_id"].dropna().astype(str).unique().tolist()),
    }
    summary_json_path.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")

    return {
        "raw_rows_path": raw_rows_path,
        "source_file_summary_path": source_file_summary_path,
        "session_summary_path": session_summary_path,
        "session_quality_path": session_quality_path,
        "session_inclusion_path": session_inclusion_path,
        "participant_summary_path": participant_summary_path,
        "video_summary_path": video_summary_path,
        "aoi_summary_path": aoi_summary_path,
        "video_aoi_summary_path": video_aoi_summary_path,
        "transition_summary_path": transition_summary_path,
        "summary_json_path": summary_json_path,
    }
