from __future__ import annotations

"""Compare manual and automatic AOI sources over the same Unity runtime gaze logs."""

import json
from bisect import bisect_right
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image

from aoi360_analytics.runtime_exports import (
    DEFAULT_MANIFEST_GLOB,
    MANIFEST_COLUMNS,
    SESSION_GROUP_COLUMNS,
    RuntimeAnalyticsResult,
    analyze_runtime_rows,
    discover_runtime_csv_paths,
    export_runtime_analytics,
    load_runtime_csvs,
)


DEFAULT_COMPARISON_MATCH_FIELD = "aoi_category"
VALID_COMPARISON_MATCH_FIELDS = {"aoi_id", "aoi_name", "aoi_category"}
DEFAULT_COMPARISON_OUTPUT_ROOT = Path("data") / "exports" / "analytics" / "source_comparison"

COMPARISON_SESSION_ALIGNMENT_COLUMNS = [
    "participant_id",
    "session_id",
    "video_id",
    "rows_total",
    "valid_rows",
    "manual_assigned_valid_rows",
    "automatic_assigned_valid_rows",
    "both_assigned_valid_rows",
    "manual_only_valid_rows",
    "automatic_only_valid_rows",
    "neither_assigned_valid_rows",
    "category_match_valid_rows",
    "selected_match_valid_rows",
    "manual_assignment_rate_over_valid",
    "automatic_assignment_rate_over_valid",
    "both_assigned_rate_over_valid",
    "category_match_ratio_of_both_assigned",
    "selected_match_ratio_of_both_assigned",
    "assignment_gap_rate_over_valid",
    "manual_unique_selected_keys",
    "automatic_unique_selected_keys",
    "match_field",
]

COMPARISON_CONFUSION_COLUMNS = [
    "match_field",
    "manual_value",
    "automatic_value",
    "row_count",
    "share_of_rows",
    "share_of_manual_value_rows",
    "share_of_automatic_value_rows",
]

VIDEO_MATCH_SUMMARY_COLUMNS = [
    "video_id",
    "comparison_key",
    "match_field",
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

VIDEO_MATCH_DELTA_COLUMNS = [
    "video_id",
    "comparison_key",
    "match_field",
    "presence_state",
    "manual_session_runs_total_for_video",
    "automatic_session_runs_total_for_video",
    "manual_session_hit_count",
    "automatic_session_hit_count",
    "automatic_minus_manual_session_hit_count",
    "manual_session_hit_ratio",
    "automatic_session_hit_ratio",
    "automatic_minus_manual_session_hit_ratio",
    "manual_participants_with_hits",
    "automatic_participants_with_hits",
    "automatic_minus_manual_participants_with_hits",
    "manual_total_fixation_steps",
    "automatic_total_fixation_steps",
    "automatic_minus_manual_total_fixation_steps",
    "manual_total_dwell_time_ms",
    "automatic_total_dwell_time_ms",
    "automatic_minus_manual_total_dwell_time_ms",
    "manual_total_visit_count",
    "automatic_total_visit_count",
    "automatic_minus_manual_total_visit_count",
    "manual_mean_dwell_time_ms_when_hit",
    "automatic_mean_dwell_time_ms_when_hit",
    "automatic_minus_manual_mean_dwell_time_ms_when_hit",
    "manual_mean_dwell_share_of_valid_time_when_hit",
    "automatic_mean_dwell_share_of_valid_time_when_hit",
    "automatic_minus_manual_mean_dwell_share_of_valid_time_when_hit",
    "manual_mean_dwell_share_of_assigned_time_when_hit",
    "automatic_mean_dwell_share_of_assigned_time_when_hit",
    "automatic_minus_manual_mean_dwell_share_of_assigned_time_when_hit",
    "manual_mean_fixation_steps_per_minute_valid_when_hit",
    "automatic_mean_fixation_steps_per_minute_valid_when_hit",
    "automatic_minus_manual_mean_fixation_steps_per_minute_valid_when_hit",
    "manual_mean_visit_count_per_minute_valid_when_hit",
    "automatic_mean_visit_count_per_minute_valid_when_hit",
    "automatic_minus_manual_mean_visit_count_per_minute_valid_when_hit",
    "manual_mean_time_to_first_fixation_ms_when_hit",
    "automatic_mean_time_to_first_fixation_ms_when_hit",
    "automatic_minus_manual_mean_time_to_first_fixation_ms_when_hit",
    "manual_mean_time_to_first_fixation_ratio_when_hit",
    "automatic_mean_time_to_first_fixation_ratio_when_hit",
    "automatic_minus_manual_mean_time_to_first_fixation_ratio_when_hit",
]


@dataclass(frozen=True)
class AoiDefinition:
    aoi_id: int
    aoi_name: str
    aoi_category: str
    aoi_prompt: str
    aoi_color: str
    aoi_confidence: float


@dataclass(frozen=True)
class AoiFrameEntry:
    frame_index: int
    map_path: Path | None
    pack_offset: int | None
    pack_length: int | None


class AoiSourcePackage:
    """Resolve AOI ids offline from one AOI-sequence manifest plus its frame assets."""

    def __init__(
        self,
        *,
        video_id: str,
        manifest_path: Path,
        runtime_pack_path: Path | None,
        frame_width: int,
        frame_height: int,
        frame_byte_length: int,
        frame_entries: list[AoiFrameEntry],
        aoi_definitions: list[AoiDefinition],
    ) -> None:
        self.video_id = video_id
        self.manifest_path = manifest_path
        self.runtime_pack_path = runtime_pack_path
        self.frame_width = frame_width
        self.frame_height = frame_height
        self.frame_byte_length = frame_byte_length
        self.frame_entries = sorted(frame_entries, key=lambda entry: entry.frame_index)
        self._frame_indices = [entry.frame_index for entry in self.frame_entries]
        self.aoi_by_id = {definition.aoi_id: definition for definition in aoi_definitions}
        self.color_to_aoi_id = {
            parsed_color: definition.aoi_id
            for definition in aoi_definitions
            for parsed_color in [_parse_hex_color(definition.aoi_color)]
            if parsed_color is not None
        }
        self._runtime_pack_bytes: bytes | None = None
        self._frame_cache: dict[int, np.ndarray] = {}

    def resolve_frame_entry(self, frame_index: int) -> AoiFrameEntry | None:
        if not self.frame_entries:
            return None

        insertion_index = bisect_right(self._frame_indices, frame_index) - 1
        if insertion_index < 0:
            return self.frame_entries[0]
        return self.frame_entries[insertion_index]

    def sample_pixels(self, frame_entry: AoiFrameEntry, pixel_x: np.ndarray, pixel_y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        frame_rgb = self._load_frame_rgb(frame_entry)
        sampled_rgb = frame_rgb[pixel_y, pixel_x]

        aoi_ids = np.fromiter(
            (
                self.color_to_aoi_id.get((int(rgb[0]), int(rgb[1]), int(rgb[2])), 0)
                for rgb in sampled_rgb
            ),
            dtype=np.int64,
            count=len(sampled_rgb),
        )
        aoi_confidences = np.fromiter(
            (
                self.aoi_by_id[aoi_id].aoi_confidence if aoi_id > 0 else 0.0
                for aoi_id in aoi_ids.tolist()
            ),
            dtype=float,
            count=len(aoi_ids),
        )
        return aoi_ids, aoi_confidences

    def _load_frame_rgb(self, frame_entry: AoiFrameEntry) -> np.ndarray:
        cached_frame = self._frame_cache.get(frame_entry.frame_index)
        if cached_frame is not None:
            return cached_frame

        if self.runtime_pack_path is not None and frame_entry.pack_offset is not None:
            runtime_pack_bytes = self._load_runtime_pack_bytes()
            pack_length = frame_entry.pack_length or self.frame_byte_length
            start = frame_entry.pack_offset
            stop = start + pack_length
            frame_bytes = runtime_pack_bytes[start:stop]
            expected_byte_length = self.frame_width * self.frame_height * 3
            if len(frame_bytes) != expected_byte_length:
                raise RuntimeError(
                    f"Runtime pack frame length mismatch for '{self.video_id}' frame {frame_entry.frame_index}: "
                    f"expected {expected_byte_length} bytes, got {len(frame_bytes)}."
                )

            frame_rgb = np.frombuffer(frame_bytes, dtype=np.uint8).reshape(
                (self.frame_height, self.frame_width, 3)
            )
        elif frame_entry.map_path is not None and frame_entry.map_path.exists():
            # The PNG fallback keeps the comparison pipeline compatible with future manual
            # annotations even if they are authored without the packed RGB24 runtime blob.
            with Image.open(frame_entry.map_path) as frame_image:
                frame_rgb = np.asarray(frame_image.convert("RGB"), dtype=np.uint8)
        else:
            raise RuntimeError(
                f"Cannot resolve AOI frame data for '{self.video_id}' frame {frame_entry.frame_index}."
            )

        self._frame_cache[frame_entry.frame_index] = frame_rgb
        return frame_rgb

    def _load_runtime_pack_bytes(self) -> bytes:
        if self._runtime_pack_bytes is None:
            if self.runtime_pack_path is None or not self.runtime_pack_path.exists():
                raise RuntimeError(
                    f"Runtime pack for '{self.video_id}' is missing: {self.runtime_pack_path!s}"
                )
            self._runtime_pack_bytes = self.runtime_pack_path.read_bytes()
        return self._runtime_pack_bytes


@dataclass(frozen=True)
class AoiSourceBundle:
    manifest_root: Path
    packages: dict[str, AoiSourcePackage]
    manifest_index: pd.DataFrame


@dataclass(frozen=True)
class RuntimeSourceComparisonResult:
    raw_rows: pd.DataFrame
    manual_result: RuntimeAnalyticsResult
    automatic_result: RuntimeAnalyticsResult
    comparison_rows: pd.DataFrame
    session_alignment: pd.DataFrame
    category_confusion: pd.DataFrame
    match_field_confusion: pd.DataFrame
    manual_video_match_summary: pd.DataFrame
    automatic_video_match_summary: pd.DataFrame
    video_match_deltas: pd.DataFrame
    match_field: str
    manual_manifest_root: Path
    automatic_manifest_root: Path


def compare_runtime_aoi_sources(
    *,
    input_csvs: list[str] | None = None,
    input_dir: str | Path | None = None,
    manual_manifest_root: str | Path,
    automatic_manifest_root: str | Path,
    manual_maps_root: str | Path | None = None,
    automatic_maps_root: str | Path | None = None,
    match_field: str = DEFAULT_COMPARISON_MATCH_FIELD,
) -> RuntimeSourceComparisonResult:
    """Reapply two AOI sources over the same runtime gaze logs and compare them."""

    if match_field not in VALID_COMPARISON_MATCH_FIELDS:
        valid_fields = ", ".join(sorted(VALID_COMPARISON_MATCH_FIELDS))
        raise ValueError(f"Unsupported match field '{match_field}'. Expected one of: {valid_fields}.")

    csv_paths = discover_runtime_csv_paths(input_csvs=input_csvs, input_dir=input_dir)
    raw_rows = load_runtime_csvs(csv_paths)
    raw_rows = raw_rows.copy()
    raw_rows.insert(0, "row_id", np.arange(len(raw_rows), dtype=np.int64))

    manual_bundle = load_aoi_source_bundle(manual_manifest_root, maps_root=manual_maps_root)
    automatic_bundle = load_aoi_source_bundle(automatic_manifest_root, maps_root=automatic_maps_root)

    manual_rows = reassign_runtime_rows_from_bundle(raw_rows, manual_bundle, source_label="manual")
    automatic_rows = reassign_runtime_rows_from_bundle(raw_rows, automatic_bundle, source_label="automatic")

    manual_result = analyze_runtime_rows(
        manual_rows.drop(columns=["row_id"], errors="ignore"),
        manifest_root=manual_bundle.manifest_root,
    )
    automatic_result = analyze_runtime_rows(
        automatic_rows.drop(columns=["row_id"], errors="ignore"),
        manifest_root=automatic_bundle.manifest_root,
    )

    comparison_rows = build_comparison_rows(
        raw_rows=raw_rows,
        manual_rows=manual_rows,
        automatic_rows=automatic_rows,
        manual_manifest_index=manual_bundle.manifest_index,
        automatic_manifest_index=automatic_bundle.manifest_index,
        match_field=match_field,
    )
    session_alignment = build_session_alignment_summary(comparison_rows, match_field=match_field)
    category_confusion = build_confusion_summary(
        comparison_rows,
        manual_column="manual_aoi_category",
        automatic_column="automatic_aoi_category",
        match_field="aoi_category",
    )
    match_field_confusion = build_confusion_summary(
        comparison_rows,
        manual_column=f"manual_{match_field}",
        automatic_column=f"automatic_{match_field}",
        match_field=match_field,
    )
    manual_video_match_summary = build_video_match_summary(
        manual_result,
        match_field=match_field,
    )
    automatic_video_match_summary = build_video_match_summary(
        automatic_result,
        match_field=match_field,
    )
    video_match_deltas = build_video_match_delta_summary(
        manual_video_match_summary=manual_video_match_summary,
        automatic_video_match_summary=automatic_video_match_summary,
        match_field=match_field,
    )

    return RuntimeSourceComparisonResult(
        raw_rows=raw_rows.drop(columns=["row_id"], errors="ignore"),
        manual_result=manual_result,
        automatic_result=automatic_result,
        comparison_rows=comparison_rows.drop(columns=["row_id"], errors="ignore"),
        session_alignment=session_alignment,
        category_confusion=category_confusion,
        match_field_confusion=match_field_confusion,
        manual_video_match_summary=manual_video_match_summary,
        automatic_video_match_summary=automatic_video_match_summary,
        video_match_deltas=video_match_deltas,
        match_field=match_field,
        manual_manifest_root=manual_bundle.manifest_root,
        automatic_manifest_root=automatic_bundle.manifest_root,
    )


def load_aoi_source_bundle(
    manifest_root: str | Path,
    *,
    maps_root: str | Path | None = None,
) -> AoiSourceBundle:
    """Load one AOI-sequence package bundle keyed by video id."""

    manifest_directory = Path(manifest_root).resolve()
    if not manifest_directory.exists():
        raise RuntimeError(f"AOI manifest root does not exist: {manifest_directory}")

    default_maps_root = Path(maps_root).resolve() if maps_root is not None else manifest_directory.parent / "id_maps"
    packages: dict[str, AoiSourcePackage] = {}
    manifest_rows: list[dict[str, object]] = []

    for manifest_path in sorted(manifest_directory.glob(DEFAULT_MANIFEST_GLOB)):
        manifest_document = json.loads(manifest_path.read_text(encoding="utf-8"))
        video_name = str(manifest_document.get("video") or "")
        video_id = Path(video_name).stem if video_name else manifest_path.name.replace(
            "_aoi_sequence_manifest.json",
            "",
        )
        if video_id in packages:
            raise RuntimeError(
                f"Duplicate AOI manifest for video_id '{video_id}' found in {manifest_directory}."
            )

        runtime_pack_path = _resolve_runtime_pack_path(manifest_path, manifest_document)
        frame_width, frame_height, frame_byte_length = _resolve_runtime_pack_shape(manifest_document)
        aoi_definitions = _load_aoi_definitions(manifest_document)
        frame_entries = _load_frame_entries(
            manifest_document=manifest_document,
            manifest_path=manifest_path,
            default_maps_root=default_maps_root,
        )
        packages[video_id] = AoiSourcePackage(
            video_id=video_id,
            manifest_path=manifest_path,
            runtime_pack_path=runtime_pack_path,
            frame_width=frame_width,
            frame_height=frame_height,
            frame_byte_length=frame_byte_length,
            frame_entries=frame_entries,
            aoi_definitions=aoi_definitions,
        )

        for definition in aoi_definitions:
            manifest_rows.append(
                {
                    "video_id": video_id,
                    "aoi_id": definition.aoi_id,
                    "aoi_name": definition.aoi_name,
                    "aoi_category": definition.aoi_category,
                    "aoi_prompt": definition.aoi_prompt,
                    "aoi_color": definition.aoi_color,
                }
            )

    if not packages:
        raise RuntimeError(f"No AOI manifests matching '{DEFAULT_MANIFEST_GLOB}' were found in {manifest_directory}")

    manifest_index = pd.DataFrame(manifest_rows, columns=MANIFEST_COLUMNS).drop_duplicates(
        subset=["video_id", "aoi_id"]
    )
    return AoiSourceBundle(
        manifest_root=manifest_directory,
        packages=packages,
        manifest_index=manifest_index,
    )


def reassign_runtime_rows_from_bundle(
    runtime_rows: pd.DataFrame,
    bundle: AoiSourceBundle,
    *,
    source_label: str,
) -> pd.DataFrame:
    """Recompute AOI ids from a manifest bundle over the existing runtime gaze rows."""

    rows = runtime_rows.copy()
    rows["resolved_keyframe_index"] = -1
    rows["aoi_id"] = 0
    rows["aoi_confidence"] = 0.0
    rows["aoi_source_label"] = source_label

    candidate_mask = (
        rows["video_id"].isin(bundle.packages.keys())
        & rows["frame_index"].notna()
        & rows["uv_x"].notna()
        & rows["uv_y"].notna()
    )
    if not candidate_mask.any():
        return rows

    for video_id, package in bundle.packages.items():
        video_mask = candidate_mask & (rows["video_id"] == video_id)
        if not video_mask.any():
            continue

        candidate_rows = rows.loc[video_mask, ["frame_index", "uv_x", "uv_y"]].copy()
        resolved_keyframes = _resolve_keyframe_indices(
            package,
            candidate_rows["frame_index"].astype(int).tolist(),
        )
        candidate_rows["resolved_keyframe_index"] = resolved_keyframes

        for keyframe_index, keyframe_rows in candidate_rows.groupby("resolved_keyframe_index"):
            if int(keyframe_index) < 0:
                continue

            frame_entry = package.resolve_frame_entry(int(keyframe_index))
            if frame_entry is None:
                continue

            pixel_x = np.floor(keyframe_rows["uv_x"].to_numpy(dtype=float) * package.frame_width).astype(np.int64)
            pixel_y = np.floor(keyframe_rows["uv_y"].to_numpy(dtype=float) * package.frame_height).astype(np.int64)
            pixel_x = np.clip(pixel_x, 0, package.frame_width - 1)
            pixel_y = np.clip(pixel_y, 0, package.frame_height - 1)

            aoi_ids, aoi_confidences = package.sample_pixels(frame_entry, pixel_x, pixel_y)
            rows.loc[keyframe_rows.index, "resolved_keyframe_index"] = int(keyframe_index)
            rows.loc[keyframe_rows.index, "aoi_id"] = aoi_ids
            rows.loc[keyframe_rows.index, "aoi_confidence"] = aoi_confidences

    return rows


def build_comparison_rows(
    *,
    raw_rows: pd.DataFrame,
    manual_rows: pd.DataFrame,
    automatic_rows: pd.DataFrame,
    manual_manifest_index: pd.DataFrame,
    automatic_manifest_index: pd.DataFrame,
    match_field: str,
) -> pd.DataFrame:
    """Join the two reassigned AOI views row-by-row for agreement analysis."""

    comparison_rows = raw_rows.copy()
    comparison_rows = comparison_rows.merge(
        manual_rows[["row_id", "resolved_keyframe_index", "aoi_id", "aoi_confidence"]].rename(
            columns={
                "resolved_keyframe_index": "manual_resolved_keyframe_index",
                "aoi_id": "manual_aoi_id",
                "aoi_confidence": "manual_aoi_confidence",
            }
        ),
        on="row_id",
        how="left",
    )
    comparison_rows = comparison_rows.merge(
        automatic_rows[["row_id", "resolved_keyframe_index", "aoi_id", "aoi_confidence"]].rename(
            columns={
                "resolved_keyframe_index": "automatic_resolved_keyframe_index",
                "aoi_id": "automatic_aoi_id",
                "aoi_confidence": "automatic_aoi_confidence",
            }
        ),
        on="row_id",
        how="left",
    )
    comparison_rows = _enrich_prefixed_aoi_metadata(
        comparison_rows,
        manifest_index=manual_manifest_index,
        aoi_id_column="manual_aoi_id",
        prefix="manual",
    )
    comparison_rows = _enrich_prefixed_aoi_metadata(
        comparison_rows,
        manifest_index=automatic_manifest_index,
        aoi_id_column="automatic_aoi_id",
        prefix="automatic",
    )

    comparison_rows["manual_selected_match_value"] = _build_match_series(
        comparison_rows,
        field_name=match_field,
        prefix="manual",
    )
    comparison_rows["automatic_selected_match_value"] = _build_match_series(
        comparison_rows,
        field_name=match_field,
        prefix="automatic",
    )

    valid_mask = comparison_rows["is_valid"] == 1
    manual_assigned_mask = valid_mask & (comparison_rows["manual_aoi_id"] > 0)
    automatic_assigned_mask = valid_mask & (comparison_rows["automatic_aoi_id"] > 0)
    both_assigned_mask = manual_assigned_mask & automatic_assigned_mask
    manual_only_mask = manual_assigned_mask & ~automatic_assigned_mask
    automatic_only_mask = automatic_assigned_mask & ~manual_assigned_mask
    neither_assigned_mask = valid_mask & ~manual_assigned_mask & ~automatic_assigned_mask

    comparison_rows["manual_assigned_valid"] = manual_assigned_mask.astype(int)
    comparison_rows["automatic_assigned_valid"] = automatic_assigned_mask.astype(int)
    comparison_rows["both_assigned_valid"] = both_assigned_mask.astype(int)
    comparison_rows["manual_only_valid"] = manual_only_mask.astype(int)
    comparison_rows["automatic_only_valid"] = automatic_only_mask.astype(int)
    comparison_rows["neither_assigned_valid"] = neither_assigned_mask.astype(int)
    comparison_rows["category_match_valid"] = (
        both_assigned_mask
        & _normalized_text_series(comparison_rows["manual_aoi_category"]).eq(
            _normalized_text_series(comparison_rows["automatic_aoi_category"])
        )
    ).astype(int)
    comparison_rows["selected_match_valid"] = (
        both_assigned_mask
        & _normalized_text_series(comparison_rows["manual_selected_match_value"]).eq(
            _normalized_text_series(comparison_rows["automatic_selected_match_value"])
        )
    ).astype(int)
    comparison_rows["match_field"] = match_field

    assignment_states = np.select(
        [both_assigned_mask, manual_only_mask, automatic_only_mask, neither_assigned_mask],
        ["both_assigned", "manual_only", "automatic_only", "neither_assigned"],
        default="not_comparable",
    )
    comparison_rows["assignment_state"] = assignment_states
    return comparison_rows


def build_session_alignment_summary(comparison_rows: pd.DataFrame, *, match_field: str) -> pd.DataFrame:
    """Summarize how closely both AOI sources agree within each session/video run."""

    if comparison_rows.empty:
        return pd.DataFrame(columns=COMPARISON_SESSION_ALIGNMENT_COLUMNS)

    rows = comparison_rows.copy()
    rows["valid_flag"] = (rows["is_valid"] == 1).astype(int)

    summary = (
        rows.groupby(SESSION_GROUP_COLUMNS, as_index=False).agg(
            rows_total=("participant_id", "size"),
            valid_rows=("valid_flag", "sum"),
            manual_assigned_valid_rows=("manual_assigned_valid", "sum"),
            automatic_assigned_valid_rows=("automatic_assigned_valid", "sum"),
            both_assigned_valid_rows=("both_assigned_valid", "sum"),
            manual_only_valid_rows=("manual_only_valid", "sum"),
            automatic_only_valid_rows=("automatic_only_valid", "sum"),
            neither_assigned_valid_rows=("neither_assigned_valid", "sum"),
            category_match_valid_rows=("category_match_valid", "sum"),
            selected_match_valid_rows=("selected_match_valid", "sum"),
            manual_unique_selected_keys=("manual_selected_match_value", lambda values: _count_non_empty_unique(values)),
            automatic_unique_selected_keys=("automatic_selected_match_value", lambda values: _count_non_empty_unique(values)),
        )
    )

    summary["manual_assignment_rate_over_valid"] = summary.apply(
        lambda row: _safe_divide(row["manual_assigned_valid_rows"], row["valid_rows"]),
        axis=1,
    )
    summary["automatic_assignment_rate_over_valid"] = summary.apply(
        lambda row: _safe_divide(row["automatic_assigned_valid_rows"], row["valid_rows"]),
        axis=1,
    )
    summary["both_assigned_rate_over_valid"] = summary.apply(
        lambda row: _safe_divide(row["both_assigned_valid_rows"], row["valid_rows"]),
        axis=1,
    )
    summary["category_match_ratio_of_both_assigned"] = summary.apply(
        lambda row: _safe_divide(row["category_match_valid_rows"], row["both_assigned_valid_rows"]),
        axis=1,
    )
    summary["selected_match_ratio_of_both_assigned"] = summary.apply(
        lambda row: _safe_divide(row["selected_match_valid_rows"], row["both_assigned_valid_rows"]),
        axis=1,
    )
    summary["assignment_gap_rate_over_valid"] = summary.apply(
        lambda row: _safe_divide(
            row["manual_only_valid_rows"] + row["automatic_only_valid_rows"],
            row["valid_rows"],
        ),
        axis=1,
    )
    summary["match_field"] = match_field
    return summary[COMPARISON_SESSION_ALIGNMENT_COLUMNS]


def build_confusion_summary(
    comparison_rows: pd.DataFrame,
    *,
    manual_column: str,
    automatic_column: str,
    match_field: str,
) -> pd.DataFrame:
    """Build one confusion-style table for a chosen manual/automatic semantic field."""

    if comparison_rows.empty:
        return pd.DataFrame(columns=COMPARISON_CONFUSION_COLUMNS)

    rows = comparison_rows[
        (comparison_rows["is_valid"] == 1)
        & (comparison_rows["manual_aoi_id"] > 0)
        & (comparison_rows["automatic_aoi_id"] > 0)
    ].copy()
    if rows.empty:
        return pd.DataFrame(columns=COMPARISON_CONFUSION_COLUMNS)

    rows["manual_value"] = _normalized_text_series(rows[manual_column])
    rows["automatic_value"] = _normalized_text_series(rows[automatic_column])
    rows = rows[(rows["manual_value"] != "") | (rows["automatic_value"] != "")]
    if rows.empty:
        return pd.DataFrame(columns=COMPARISON_CONFUSION_COLUMNS)

    confusion = (
        rows.groupby(["manual_value", "automatic_value"], as_index=False)
        .agg(row_count=("manual_value", "size"))
        .sort_values("row_count", ascending=False, ignore_index=True)
    )
    total_rows = int(confusion["row_count"].sum())
    manual_totals = confusion.groupby("manual_value")["row_count"].transform("sum")
    automatic_totals = confusion.groupby("automatic_value")["row_count"].transform("sum")
    confusion["match_field"] = match_field
    confusion["share_of_rows"] = confusion["row_count"].apply(lambda value: _safe_divide(value, total_rows))
    confusion["share_of_manual_value_rows"] = confusion["row_count"] / manual_totals
    confusion["share_of_automatic_value_rows"] = confusion["row_count"] / automatic_totals
    return confusion[COMPARISON_CONFUSION_COLUMNS]


def build_video_match_summary(
    analytics_result: RuntimeAnalyticsResult,
    *,
    match_field: str,
) -> pd.DataFrame:
    """Aggregate AOI metrics by video plus semantic comparison key."""

    aoi_summary = analytics_result.aoi_summary.copy()
    if aoi_summary.empty:
        return pd.DataFrame(columns=VIDEO_MATCH_SUMMARY_COLUMNS)

    aoi_summary["comparison_key"] = _build_match_series(
        aoi_summary,
        field_name=match_field,
        prefix="",
    )
    aoi_summary = aoi_summary[_normalized_text_series(aoi_summary["comparison_key"]) != ""]
    if aoi_summary.empty:
        return pd.DataFrame(columns=VIDEO_MATCH_SUMMARY_COLUMNS)

    video_summary = (
        aoi_summary.groupby(["video_id", "comparison_key"], as_index=False, dropna=False).agg(
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
        analytics_result.session_summary.groupby("video_id", as_index=False)
        .agg(session_runs_total_for_video=("participant_id", "size"))
    )
    video_summary = video_summary.merge(session_totals, on="video_id", how="left")
    video_summary["session_runs_total_for_video"] = video_summary["session_runs_total_for_video"].fillna(0).astype(int)
    video_summary["session_hit_ratio"] = video_summary.apply(
        lambda row: _safe_divide(row["session_hit_count"], row["session_runs_total_for_video"]),
        axis=1,
    )
    video_summary["match_field"] = match_field
    return video_summary[VIDEO_MATCH_SUMMARY_COLUMNS]


def build_video_match_delta_summary(
    *,
    manual_video_match_summary: pd.DataFrame,
    automatic_video_match_summary: pd.DataFrame,
    match_field: str,
) -> pd.DataFrame:
    """Join both per-video semantic summaries and expose metric deltas."""

    manual_summary = manual_video_match_summary.rename(
        columns={column: f"manual_{column}" for column in VIDEO_MATCH_SUMMARY_COLUMNS if column not in {"video_id", "comparison_key", "match_field"}}
    )
    automatic_summary = automatic_video_match_summary.rename(
        columns={column: f"automatic_{column}" for column in VIDEO_MATCH_SUMMARY_COLUMNS if column not in {"video_id", "comparison_key", "match_field"}}
    )
    delta_summary = manual_summary.merge(
        automatic_summary,
        on=["video_id", "comparison_key", "match_field"],
        how="outer",
    )
    if delta_summary.empty:
        return pd.DataFrame(columns=VIDEO_MATCH_DELTA_COLUMNS)

    manual_presence = delta_summary["manual_session_hit_count"].fillna(0) > 0
    automatic_presence = delta_summary["automatic_session_hit_count"].fillna(0) > 0
    delta_summary["presence_state"] = np.select(
        [manual_presence & automatic_presence, manual_presence, automatic_presence],
        ["both_sources", "manual_only", "automatic_only"],
        default="neither_source",
    )

    delta_columns = [
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
    for metric_name in delta_columns:
        manual_column = f"manual_{metric_name}"
        automatic_column = f"automatic_{metric_name}"
        delta_summary[manual_column] = delta_summary[manual_column].fillna(0)
        delta_summary[automatic_column] = delta_summary[automatic_column].fillna(0)
        delta_summary[f"automatic_minus_manual_{metric_name}"] = (
            delta_summary[automatic_column] - delta_summary[manual_column]
        )

    for source_column in ["manual_session_runs_total_for_video", "automatic_session_runs_total_for_video"]:
        delta_summary[source_column] = delta_summary[source_column].fillna(0).astype(int)

    return delta_summary[VIDEO_MATCH_DELTA_COLUMNS]


def export_runtime_source_comparison(
    comparison_result: RuntimeSourceComparisonResult,
    *,
    output_dir: str | Path,
) -> dict[str, Path]:
    """Persist both source analytics plus the comparison tables."""

    output_directory = Path(output_dir).resolve()
    output_directory.mkdir(parents=True, exist_ok=True)

    manual_output_dir = output_directory / "manual"
    automatic_output_dir = output_directory / "automatic"
    manual_export_paths = export_runtime_analytics(comparison_result.manual_result, output_dir=manual_output_dir)
    automatic_export_paths = export_runtime_analytics(comparison_result.automatic_result, output_dir=automatic_output_dir)

    comparison_rows_path = output_directory / "comparison_rows_reassigned.csv"
    session_alignment_path = output_directory / "comparison_session_alignment.csv"
    category_confusion_path = output_directory / "comparison_category_confusion.csv"
    match_field_confusion_path = output_directory / "comparison_match_field_confusion.csv"
    manual_video_match_summary_path = output_directory / "manual_video_match_summary.csv"
    automatic_video_match_summary_path = output_directory / "automatic_video_match_summary.csv"
    video_match_deltas_path = output_directory / "comparison_video_match_deltas.csv"
    summary_json_path = output_directory / "comparison_summary_snapshot.json"

    comparison_result.comparison_rows.to_csv(comparison_rows_path, index=False)
    comparison_result.session_alignment.to_csv(session_alignment_path, index=False)
    comparison_result.category_confusion.to_csv(category_confusion_path, index=False)
    comparison_result.match_field_confusion.to_csv(match_field_confusion_path, index=False)
    comparison_result.manual_video_match_summary.to_csv(manual_video_match_summary_path, index=False)
    comparison_result.automatic_video_match_summary.to_csv(automatic_video_match_summary_path, index=False)
    comparison_result.video_match_deltas.to_csv(video_match_deltas_path, index=False)

    valid_rows = comparison_result.comparison_rows[comparison_result.comparison_rows["is_valid"] == 1]
    both_assigned_valid_rows = int(valid_rows["both_assigned_valid"].sum()) if not valid_rows.empty else 0
    selected_match_valid_rows = int(valid_rows["selected_match_valid"].sum()) if not valid_rows.empty else 0
    category_match_valid_rows = int(valid_rows["category_match_valid"].sum()) if not valid_rows.empty else 0
    snapshot = {
        "input_row_count": int(len(comparison_result.raw_rows)),
        "input_source_file_count": int(comparison_result.raw_rows["source_file"].dropna().astype(str).nunique()),
        "session_count": int(len(comparison_result.session_alignment)),
        "video_count": int(comparison_result.raw_rows["video_id"].dropna().astype(str).nunique()),
        "match_field": comparison_result.match_field,
        "manual_manifest_root": str(comparison_result.manual_manifest_root),
        "automatic_manifest_root": str(comparison_result.automatic_manifest_root),
        "valid_row_count": int((comparison_result.comparison_rows["is_valid"] == 1).sum()),
        "both_assigned_valid_row_count": both_assigned_valid_rows,
        "selected_match_valid_row_count": selected_match_valid_rows,
        "category_match_valid_row_count": category_match_valid_rows,
        "selected_match_ratio_over_both_assigned": _safe_divide(selected_match_valid_rows, both_assigned_valid_rows),
        "category_match_ratio_over_both_assigned": _safe_divide(category_match_valid_rows, both_assigned_valid_rows),
        "video_match_presence_state_counts": comparison_result.video_match_deltas["presence_state"].value_counts().to_dict()
        if not comparison_result.video_match_deltas.empty
        else {},
    }
    summary_json_path.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")

    return {
        "manual_output_dir": manual_output_dir,
        "automatic_output_dir": automatic_output_dir,
        "comparison_rows_path": comparison_rows_path,
        "session_alignment_path": session_alignment_path,
        "category_confusion_path": category_confusion_path,
        "match_field_confusion_path": match_field_confusion_path,
        "manual_video_match_summary_path": manual_video_match_summary_path,
        "automatic_video_match_summary_path": automatic_video_match_summary_path,
        "video_match_deltas_path": video_match_deltas_path,
        "summary_json_path": summary_json_path,
        "manual_runtime_summary_path": manual_export_paths["summary_json_path"],
        "automatic_runtime_summary_path": automatic_export_paths["summary_json_path"],
    }


def _load_aoi_definitions(manifest_document: dict[str, object]) -> list[AoiDefinition]:
    definitions: list[AoiDefinition] = []
    for aoi_entry in manifest_document.get("aois", []):
        confidence_value = aoi_entry.get("confidence", 1.0)
        confidence = float(confidence_value) if confidence_value not in (None, "") else 1.0
        definitions.append(
            AoiDefinition(
                aoi_id=int(aoi_entry.get("id", 0)),
                aoi_name=str(aoi_entry.get("name", "")),
                aoi_category=str(aoi_entry.get("category", "")),
                aoi_prompt=str(aoi_entry.get("prompt", "")),
                aoi_color=str(aoi_entry.get("color", "")),
                aoi_confidence=confidence,
            )
        )
    return definitions


def _load_frame_entries(
    *,
    manifest_document: dict[str, object],
    manifest_path: Path,
    default_maps_root: Path,
) -> list[AoiFrameEntry]:
    maps_directory_value = manifest_document.get("mapsDirectory")
    maps_directory: Path | None = None
    if maps_directory_value:
        maps_directory = Path(str(maps_directory_value))
        if not maps_directory.is_absolute():
            candidate_from_default_root = default_maps_root / maps_directory
            maps_directory = candidate_from_default_root if candidate_from_default_root.exists() else manifest_path.parent / maps_directory

    frame_entries: list[AoiFrameEntry] = []
    for frame_entry in manifest_document.get("frames", []):
        map_file_value = frame_entry.get("mapFile")
        map_path: Path | None = None
        if map_file_value:
            map_candidate = Path(str(map_file_value))
            if map_candidate.is_absolute():
                map_path = map_candidate
            elif maps_directory is not None:
                map_path = maps_directory / map_candidate
            else:
                map_path = (default_maps_root / map_candidate) if (default_maps_root / map_candidate).exists() else manifest_path.parent / map_candidate

        frame_entries.append(
            AoiFrameEntry(
                frame_index=int(frame_entry.get("frameIndex", 0)),
                map_path=map_path,
                pack_offset=int(frame_entry["packOffset"]) if frame_entry.get("packOffset") is not None else None,
                pack_length=int(frame_entry["packLength"]) if frame_entry.get("packLength") is not None else None,
            )
        )
    return frame_entries


def _resolve_runtime_pack_path(manifest_path: Path, manifest_document: dict[str, object]) -> Path | None:
    runtime_pack_document = manifest_document.get("runtimePack") or {}
    runtime_pack_file = runtime_pack_document.get("file")
    if not runtime_pack_file:
        return None

    runtime_pack_path = Path(str(runtime_pack_file))
    return runtime_pack_path if runtime_pack_path.is_absolute() else manifest_path.parent / runtime_pack_path


def _resolve_runtime_pack_shape(manifest_document: dict[str, object]) -> tuple[int, int, int]:
    runtime_pack_document = manifest_document.get("runtimePack") or {}
    id_map_resolution = manifest_document.get("idMapResolution") or [0, 0]

    frame_width = int(runtime_pack_document.get("frameWidth") or id_map_resolution[0] or 0)
    frame_height = int(runtime_pack_document.get("frameHeight") or id_map_resolution[1] or 0)
    if frame_width <= 0 or frame_height <= 0:
        raise RuntimeError("Manifest is missing a valid AOI frame resolution.")

    frame_byte_length = int(runtime_pack_document.get("frameByteLength") or (frame_width * frame_height * 3))
    return frame_width, frame_height, frame_byte_length


def _resolve_keyframe_indices(package: AoiSourcePackage, frame_indices: list[int]) -> np.ndarray:
    resolved_indices: list[int] = []
    for frame_index in frame_indices:
        resolved_entry = package.resolve_frame_entry(int(frame_index))
        resolved_indices.append(resolved_entry.frame_index if resolved_entry is not None else -1)
    return np.array(resolved_indices, dtype=np.int64)


def _enrich_prefixed_aoi_metadata(
    rows: pd.DataFrame,
    *,
    manifest_index: pd.DataFrame,
    aoi_id_column: str,
    prefix: str,
) -> pd.DataFrame:
    if rows.empty:
        return rows

    metadata_columns = {
        "aoi_id": aoi_id_column,
        "aoi_name": f"{prefix}_aoi_name",
        "aoi_category": f"{prefix}_aoi_category",
        "aoi_prompt": f"{prefix}_aoi_prompt",
        "aoi_color": f"{prefix}_aoi_color",
    }
    metadata_rows = manifest_index.rename(columns=metadata_columns)
    enriched_rows = rows.merge(
        metadata_rows,
        on=["video_id", aoi_id_column],
        how="left",
    )
    for target_column in metadata_columns.values():
        if target_column == aoi_id_column:
            continue
        enriched_rows[target_column] = enriched_rows[target_column].fillna("")
    return enriched_rows


def _build_match_series(rows: pd.DataFrame, *, field_name: str, prefix: str) -> pd.Series:
    if field_name == "aoi_id":
        aoi_id_column = f"{prefix}_aoi_id" if prefix else "aoi_id"
        return rows[aoi_id_column].apply(lambda value: str(int(value)) if pd.notna(value) and int(value) > 0 else "")

    column_name = f"{prefix}_{field_name}" if prefix else field_name
    return _normalized_text_series(rows[column_name])


def _normalized_text_series(values: pd.Series) -> pd.Series:
    return values.fillna("").astype(str).str.strip()


def _count_non_empty_unique(values: pd.Series) -> int:
    normalized_values = sorted({value for value in _normalized_text_series(values) if value})
    return len(normalized_values)


def _parse_hex_color(color_value: str) -> tuple[int, int, int] | None:
    normalized = color_value.strip()
    if normalized.startswith("#") and len(normalized) == 7:
        return (
            int(normalized[1:3], 16),
            int(normalized[3:5], 16),
            int(normalized[5:7], 16),
        )
    return None


def _safe_divide(numerator: float | int, denominator: float | int) -> float:
    return float(numerator) / float(denominator) if denominator else 0.0
