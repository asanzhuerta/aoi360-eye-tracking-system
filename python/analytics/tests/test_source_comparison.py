from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd
from PIL import Image


TEST_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = TEST_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from aoi360_analytics.source_comparison import compare_runtime_aoi_sources, export_runtime_source_comparison


REQUIRED_COLUMNS = [
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


def _build_session_rows(
    *,
    participant_id: str,
    session_id: str,
    video_id: str,
    uv_x_values: list[float],
    timestamps_ms: list[float],
    is_valid_flags: list[int],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for index, timestamp_ms in enumerate(timestamps_ms):
        rows.append(
            {
                "participant_id": participant_id,
                "session_id": session_id,
                "video_id": video_id,
                "timestamp_ms": float(timestamp_ms),
                "frame_index": float(index),
                "origin_x": 0.0,
                "origin_y": 1.0,
                "origin_z": 2.0,
                "direction_x": 0.0,
                "direction_y": 0.0,
                "direction_z": -1.0,
                "azimuth_rad": 0.0,
                "elevation_rad": 0.0,
                "uv_x": float(uv_x_values[index]),
                "uv_y": 0.5,
                "aoi_id": 0.0,
                "aoi_confidence": 0.0,
                "left_pupil_diameter": 3.2,
                "right_pupil_diameter": 3.1,
                "is_valid": float(is_valid_flags[index]),
            }
        )
    return rows


def _write_manifest(
    *,
    manifest_root: Path,
    maps_root: Path,
    video_id: str,
    pixels: list[tuple[int, int, int]],
) -> None:
    map_path = maps_root / f"{video_id}.png"
    image = Image.new("RGB", (2, 1))
    image.putdata(pixels)
    image.save(map_path)

    manifest_document = {
        "video": f"{video_id}.mp4",
        "idMapResolution": [2, 1],
        "aois": [
            {
                "id": 1,
                "name": "left_target",
                "category": "left",
                "prompt": "left target",
                "color": "#FF0000",
                "confidence": 1.0,
            },
            {
                "id": 2,
                "name": "right_target",
                "category": "right",
                "prompt": "right target",
                "color": "#00FF00",
                "confidence": 1.0,
            },
        ],
        "frames": [
            {
                "frameIndex": 0,
                "mapFile": f"{video_id}.png",
            }
        ],
    }
    manifest_path = manifest_root / f"{video_id}_aoi_sequence_manifest.json"
    manifest_path.write_text(json.dumps(manifest_document, indent=2), encoding="utf-8")


class SourceComparisonFilteringTests(unittest.TestCase):
    def test_compare_runtime_aoi_sources_supports_session_filters(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            temp_root = Path(temporary_directory)
            csv_path = temp_root / "runtime.csv"
            manual_manifest_root = temp_root / "manual_manifests"
            automatic_manifest_root = temp_root / "automatic_manifests"
            manual_maps_root = temp_root / "manual_maps"
            automatic_maps_root = temp_root / "automatic_maps"
            export_root = temp_root / "comparison_export"

            manual_manifest_root.mkdir(parents=True, exist_ok=True)
            automatic_manifest_root.mkdir(parents=True, exist_ok=True)
            manual_maps_root.mkdir(parents=True, exist_ok=True)
            automatic_maps_root.mkdir(parents=True, exist_ok=True)

            timestamps = [0.0, 250.0, 500.0, 750.0, 1000.0]
            runtime_rows: list[dict[str, object]] = []
            runtime_rows.extend(
                _build_session_rows(
                    participant_id="P001",
                    session_id="S_GOOD",
                    video_id="video_good",
                    uv_x_values=[0.25, 0.25, 0.75, 0.75, 0.75],
                    timestamps_ms=timestamps,
                    is_valid_flags=[1, 1, 1, 1, 1],
                )
            )
            runtime_rows.extend(
                _build_session_rows(
                    participant_id="P001",
                    session_id="S_MANUAL_EMPTY",
                    video_id="video_manual_empty",
                    uv_x_values=[0.25, 0.25, 0.75, 0.75, 0.75],
                    timestamps_ms=timestamps,
                    is_valid_flags=[1, 1, 1, 1, 1],
                )
            )
            runtime_rows.extend(
                _build_session_rows(
                    participant_id="P001",
                    session_id="S_LOW_TRACKING",
                    video_id="video_low_tracking",
                    uv_x_values=[0.25, 0.25, 0.75, 0.75, 0.75],
                    timestamps_ms=timestamps,
                    is_valid_flags=[1, 0, 0, 0, 0],
                )
            )
            pd.DataFrame(runtime_rows, columns=REQUIRED_COLUMNS).to_csv(csv_path, index=False)

            # Session good: both sources assign AOIs.
            _write_manifest(
                manifest_root=manual_manifest_root,
                maps_root=manual_maps_root,
                video_id="video_good",
                pixels=[(255, 0, 0), (0, 255, 0)],
            )
            _write_manifest(
                manifest_root=automatic_manifest_root,
                maps_root=automatic_maps_root,
                video_id="video_good",
                pixels=[(255, 0, 0), (0, 255, 0)],
            )

            # Manual-empty session: automatic assigns AOIs, manual assigns none.
            _write_manifest(
                manifest_root=manual_manifest_root,
                maps_root=manual_maps_root,
                video_id="video_manual_empty",
                pixels=[(0, 0, 0), (0, 0, 0)],
            )
            _write_manifest(
                manifest_root=automatic_manifest_root,
                maps_root=automatic_maps_root,
                video_id="video_manual_empty",
                pixels=[(255, 0, 0), (0, 255, 0)],
            )

            # Low-tracking session: both sources assign AOIs but tracking quality is poor.
            _write_manifest(
                manifest_root=manual_manifest_root,
                maps_root=manual_maps_root,
                video_id="video_low_tracking",
                pixels=[(255, 0, 0), (0, 255, 0)],
            )
            _write_manifest(
                manifest_root=automatic_manifest_root,
                maps_root=automatic_maps_root,
                video_id="video_low_tracking",
                pixels=[(255, 0, 0), (0, 255, 0)],
            )

            tracking_result = compare_runtime_aoi_sources(
                input_csvs=[str(csv_path)],
                manual_manifest_root=manual_manifest_root,
                automatic_manifest_root=automatic_manifest_root,
                manual_maps_root=manual_maps_root,
                automatic_maps_root=automatic_maps_root,
                session_filter="tracking_usable",
            )
            self.assertEqual(tracking_result.session_filter, "tracking_usable")
            self.assertEqual(sorted(tracking_result.session_alignment["session_id"].tolist()), ["S_GOOD", "S_MANUAL_EMPTY"])

            tracking_inclusion = tracking_result.session_inclusion.set_index("session_id")
            self.assertTrue(bool(tracking_inclusion.loc["S_GOOD", "included_by_filter"]))
            self.assertTrue(bool(tracking_inclusion.loc["S_MANUAL_EMPTY", "included_by_filter"]))
            self.assertFalse(bool(tracking_inclusion.loc["S_LOW_TRACKING", "included_by_filter"]))
            self.assertEqual(tracking_inclusion.loc["S_LOW_TRACKING", "exclusion_reason"], "not_tracking_usable")

            aoi_result = compare_runtime_aoi_sources(
                input_csvs=[str(csv_path)],
                manual_manifest_root=manual_manifest_root,
                automatic_manifest_root=automatic_manifest_root,
                manual_maps_root=manual_maps_root,
                automatic_maps_root=automatic_maps_root,
                session_filter="aoi_usable",
            )
            self.assertEqual(aoi_result.session_filter, "aoi_usable")
            self.assertEqual(aoi_result.session_alignment["session_id"].tolist(), ["S_GOOD"])
            self.assertEqual(len(aoi_result.raw_rows), 5)
            self.assertEqual(aoi_result.manual_result.session_filter, "aoi_usable")
            self.assertEqual(int(aoi_result.manual_result.session_inclusion["included_by_filter"].sum()), 1)

            aoi_inclusion = aoi_result.session_inclusion.set_index("session_id")
            self.assertTrue(bool(aoi_inclusion.loc["S_GOOD", "included_by_filter"]))
            self.assertEqual(aoi_inclusion.loc["S_MANUAL_EMPTY", "exclusion_reason"], "manual_not_aoi_usable")
            self.assertEqual(
                aoi_inclusion.loc["S_LOW_TRACKING", "exclusion_reason"],
                "manual_and_automatic_not_aoi_usable",
            )

            export_paths = export_runtime_source_comparison(aoi_result, output_dir=export_root)
            self.assertTrue(export_paths["session_inclusion_path"].exists())
            exported_inclusion = pd.read_csv(export_paths["session_inclusion_path"])
            self.assertEqual(len(exported_inclusion), 3)

            snapshot = json.loads(export_paths["summary_json_path"].read_text(encoding="utf-8"))
            self.assertEqual(snapshot["session_filter"], "aoi_usable")
            self.assertEqual(snapshot["input_row_count"], 15)
            self.assertEqual(snapshot["row_count"], 5)
            self.assertEqual(snapshot["input_session_count"], 3)
            self.assertEqual(snapshot["included_session_count"], 1)
            self.assertEqual(snapshot["excluded_session_count"], 2)


if __name__ == "__main__":
    unittest.main()
