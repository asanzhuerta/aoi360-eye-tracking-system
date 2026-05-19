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
DEFAULT_CONTINUITY_GAP_FACTOR = 1.5

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
    "first_timestamp_ms",
    "last_timestamp_ms",
    "observed_span_ms",
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


@dataclass(frozen=True)
class RuntimeAnalyticsResult:
    raw_rows: pd.DataFrame
    session_summary: pd.DataFrame
    participant_summary: pd.DataFrame
    video_summary: pd.DataFrame
    aoi_summary: pd.DataFrame
    transition_summary: pd.DataFrame
    manifest_index: pd.DataFrame


def _empty_dataframe(columns: list[str]) -> pd.DataFrame:
    return pd.DataFrame(columns=columns)


def _weighted_average(values: pd.Series, weights: pd.Series) -> float:
    valid_mask = values.notna() & weights.notna() & weights.gt(0)
    if not valid_mask.any():
        return float("nan")

    weighted_values = values.loc[valid_mask] * weights.loc[valid_mask]
    return float(weighted_values.sum() / weights.loc[valid_mask].sum())


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

    positive_deltas = session_rows["timestamp_ms"].sort_values().diff().dropna()
    positive_deltas = positive_deltas[positive_deltas > 0]

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
        valid_rows = session_rows[session_rows["is_valid"] == 1]
        assigned_valid_rows = valid_rows[valid_rows["aoi_id"] > 0]

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
                "first_timestamp_ms": float(session_rows["timestamp_ms"].min()) if len(session_rows) else 0.0,
                "last_timestamp_ms": float(session_rows["timestamp_ms"].max()) if len(session_rows) else 0.0,
                "observed_span_ms": (
                    float(session_rows["timestamp_ms"].max() - session_rows["timestamp_ms"].min())
                    if len(session_rows) > 1
                    else 0.0
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
        )
    )
    summary["valid_ratio"] = summary["rows_valid"] / summary["rows_total"]
    summary["assigned_valid_ratio"] = summary["rows_assigned_valid"] / summary["rows_valid"].where(
        summary["rows_valid"] > 0,
        1,
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
        )
    )
    summary["valid_ratio"] = summary["rows_valid"] / summary["rows_total"]
    summary["assigned_valid_ratio"] = summary["rows_assigned_valid"] / summary["rows_valid"].where(
        summary["rows_valid"] > 0,
        1,
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
    participant_summary = build_participant_summary(session_summary, aoi_summary)
    video_summary = build_video_summary(session_summary, aoi_summary)
    transition_summary = build_transition_summary(raw_rows, session_summary)
    manifest_index = load_manifest_index(manifest_root)

    aoi_summary = _enrich_aoi_summary(aoi_summary, manifest_index)
    transition_summary = _enrich_transition_summary(transition_summary, manifest_index)

    return RuntimeAnalyticsResult(
        raw_rows=raw_rows,
        session_summary=session_summary,
        participant_summary=participant_summary,
        video_summary=video_summary,
        aoi_summary=aoi_summary,
        transition_summary=transition_summary,
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
    participant_summary_path = output_directory / "runtime_participant_summary.csv"
    video_summary_path = output_directory / "runtime_video_summary.csv"
    aoi_summary_path = output_directory / "runtime_aoi_summary.csv"
    transition_summary_path = output_directory / "runtime_transition_summary.csv"
    summary_json_path = output_directory / "runtime_summary_snapshot.json"

    analytics_result.raw_rows.to_csv(raw_rows_path, index=False)
    analytics_result.session_summary.to_csv(session_summary_path, index=False)
    analytics_result.participant_summary.to_csv(participant_summary_path, index=False)
    analytics_result.video_summary.to_csv(video_summary_path, index=False)
    analytics_result.aoi_summary.to_csv(aoi_summary_path, index=False)
    analytics_result.transition_summary.to_csv(transition_summary_path, index=False)

    snapshot = {
        "row_count": int(len(analytics_result.raw_rows)),
        "participant_count": int(analytics_result.raw_rows["participant_id"].dropna().astype(str).nunique()),
        "session_count": int(len(analytics_result.session_summary)),
        "video_count": int(analytics_result.raw_rows["video_id"].dropna().astype(str).nunique()),
        "aoi_summary_row_count": int(len(analytics_result.aoi_summary)),
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
        "videos": sorted(analytics_result.raw_rows["video_id"].dropna().astype(str).unique().tolist()),
    }
    summary_json_path.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")

    return {
        "raw_rows_path": raw_rows_path,
        "session_summary_path": session_summary_path,
        "participant_summary_path": participant_summary_path,
        "video_summary_path": video_summary_path,
        "aoi_summary_path": aoi_summary_path,
        "transition_summary_path": transition_summary_path,
        "summary_json_path": summary_json_path,
    }
