from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd


TEST_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = TEST_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from aoi360_analytics.runtime_exports import analyze_runtime_rows, export_runtime_analytics


def _build_session_rows(
    *,
    participant_id: str,
    session_id: str,
    video_id: str,
    source_file: str,
    timestamps_ms: list[float],
    is_valid_flags: list[int],
    aoi_ids: list[int],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for index, timestamp_ms in enumerate(timestamps_ms):
        is_valid = is_valid_flags[index]
        aoi_id = aoi_ids[index]
        rows.append(
            {
                "participant_id": participant_id,
                "session_id": session_id,
                "video_id": video_id,
                "timestamp_ms": float(timestamp_ms),
                "frame_index": float(index * 10),
                "origin_x": 0.0,
                "origin_y": 1.0,
                "origin_z": 2.0,
                "direction_x": 0.0,
                "direction_y": 0.0,
                "direction_z": -1.0,
                "azimuth_rad": 0.1,
                "elevation_rad": 0.2,
                "uv_x": 0.5,
                "uv_y": 0.5,
                "aoi_id": float(aoi_id),
                "aoi_confidence": 1.0 if aoi_id > 0 else 0.0,
                "left_pupil_diameter": 3.2,
                "right_pupil_diameter": 3.1,
                "is_valid": float(is_valid),
                "source_file": source_file,
            }
        )
    return rows


def _build_runtime_rows() -> pd.DataFrame:
    timestamps = [0.0, 250.0, 500.0, 750.0, 1000.0]
    rows: list[dict[str, object]] = []
    rows.extend(
        _build_session_rows(
            participant_id="P001",
            session_id="S_GOOD",
            video_id="video_good",
            source_file="session_good.csv",
            timestamps_ms=timestamps,
            is_valid_flags=[1, 1, 1, 1, 1],
            aoi_ids=[1, 1, 2, 2, 2],
        )
    )
    rows.extend(
        _build_session_rows(
            participant_id="P001",
            session_id="S_NO_AOI",
            video_id="video_no_aoi",
            source_file="session_no_aoi.csv",
            timestamps_ms=timestamps,
            is_valid_flags=[1, 1, 1, 1, 1],
            aoi_ids=[0, 0, 0, 0, 0],
        )
    )
    rows.extend(
        _build_session_rows(
            participant_id="P001",
            session_id="S_LOW_TRACKING",
            video_id="video_low_tracking",
            source_file="session_low_tracking.csv",
            timestamps_ms=timestamps,
            is_valid_flags=[1, 0, 0, 0, 0],
            aoi_ids=[1, 0, 0, 0, 0],
        )
    )
    dataframe = pd.DataFrame(rows)
    return dataframe.sort_values(["participant_id", "session_id", "video_id", "timestamp_ms"]).reset_index(drop=True)


class RuntimeExportFilteringTests(unittest.TestCase):
    def setUp(self) -> None:
        self.runtime_rows = _build_runtime_rows()

    def test_analyze_runtime_rows_keeps_all_sessions_by_default(self) -> None:
        result = analyze_runtime_rows(self.runtime_rows)

        self.assertEqual(result.session_filter, "all")
        self.assertEqual(len(result.raw_rows), 15)
        self.assertEqual(len(result.session_summary), 3)
        self.assertEqual(len(result.session_inclusion), 3)
        self.assertTrue(result.session_inclusion["included_by_filter"].all())

    def test_tracking_usable_filter_excludes_low_tracking_sessions(self) -> None:
        result = analyze_runtime_rows(self.runtime_rows, session_filter="tracking_usable")

        remaining_sessions = sorted(result.session_summary["session_id"].tolist())
        self.assertEqual(remaining_sessions, ["S_GOOD", "S_NO_AOI"])
        self.assertEqual(len(result.raw_rows), 10)

        inclusion = result.session_inclusion.set_index("session_id")
        self.assertTrue(bool(inclusion.loc["S_GOOD", "included_by_filter"]))
        self.assertTrue(bool(inclusion.loc["S_NO_AOI", "included_by_filter"]))
        self.assertFalse(bool(inclusion.loc["S_LOW_TRACKING", "included_by_filter"]))
        self.assertEqual(inclusion.loc["S_LOW_TRACKING", "exclusion_reason"], "not_tracking_usable")

    def test_aoi_usable_filter_keeps_only_sessions_with_usable_aoi_assignments(self) -> None:
        result = analyze_runtime_rows(self.runtime_rows, session_filter="aoi_usable")

        remaining_sessions = result.session_summary["session_id"].tolist()
        self.assertEqual(remaining_sessions, ["S_GOOD"])
        self.assertEqual(len(result.raw_rows), 5)
        self.assertEqual(result.session_quality["quality_status"].tolist(), ["pass"])

        inclusion = result.session_inclusion.set_index("session_id")
        self.assertFalse(bool(inclusion.loc["S_NO_AOI", "included_by_filter"]))
        self.assertEqual(inclusion.loc["S_NO_AOI", "exclusion_reason"], "not_aoi_usable")
        self.assertFalse(bool(inclusion.loc["S_LOW_TRACKING", "included_by_filter"]))
        self.assertEqual(inclusion.loc["S_LOW_TRACKING", "exclusion_reason"], "not_aoi_usable")

    def test_invalid_session_filter_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            analyze_runtime_rows(self.runtime_rows, session_filter="banana")

    def test_export_runtime_analytics_writes_session_inclusion_metadata(self) -> None:
        result = analyze_runtime_rows(self.runtime_rows, session_filter="aoi_usable")

        with TemporaryDirectory() as temporary_directory:
            export_paths = export_runtime_analytics(result, output_dir=temporary_directory)

            self.assertTrue(export_paths["session_inclusion_path"].exists())
            inclusion_rows = pd.read_csv(export_paths["session_inclusion_path"])
            self.assertEqual(len(inclusion_rows), 3)
            self.assertEqual(int(inclusion_rows["included_by_filter"].sum()), 1)

            snapshot = json.loads(export_paths["summary_json_path"].read_text(encoding="utf-8"))
            self.assertEqual(snapshot["session_filter"], "aoi_usable")
            self.assertEqual(snapshot["input_row_count"], 15)
            self.assertEqual(snapshot["row_count"], 5)
            self.assertEqual(snapshot["input_session_count"], 3)
            self.assertEqual(snapshot["included_session_count"], 1)
            self.assertEqual(snapshot["excluded_session_count"], 2)


if __name__ == "__main__":
    unittest.main()
