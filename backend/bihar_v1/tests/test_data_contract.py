import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from backend.bihar_v1.data_contract import (
    DISTRICT_REQUIRED_SOURCES,
    source_contract,
    build_source_manifest,
    validate_source_manifest,
    validate_contract,
    validate_source_file,
)


class DataContractTests(unittest.TestCase):
    def test_both_districts_require_same_core_sources(self):
        expected = {
            "hourly_rainfall",
            "river_level",
            "river_threshold",
            "flood_events",
            "district_boundaries",
            "sentinel1_inundation",
            "dem",
        }
        self.assertEqual(set(DISTRICT_REQUIRED_SOURCES["patna"]), expected)
        self.assertEqual(set(DISTRICT_REQUIRED_SOURCES["muzaffarpur"]), expected)

    def test_unknown_source_is_rejected(self):
        with self.assertRaises(ValueError):
            source_contract("made_up_source")

    def test_missing_source_blocks_contract(self):
        result = validate_contract({})
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(len(result["blockers"]), 7)

    def test_csv_schema_is_checked(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rain.csv"
            pd.DataFrame({
                "Data Acquisition Time": ["01/01/2025 00:00"],
                "District": ["Patna"],
                "Station": ["Example"],
            }).to_csv(path, index=False)
            result = validate_source_file(path, "hourly_rainfall")
        self.assertEqual(result["status"], "invalid_schema")

    def test_valid_csv_source_passes_structural_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rain.csv"
            pd.DataFrame({
                "Data Acquisition Time": ["01/01/2025 00:00"],
                "District": ["Patna"],
                "Station": ["Example"],
                "Telemetry Hourly Rainfall (mm)": [2.0],
            }).to_csv(path, index=False)
            result = validate_source_file(path, "hourly_rainfall")
        self.assertEqual(result["status"], "ready")

    def test_valid_district_geojson_passes(self):
        payload = {
            "type": "FeatureCollection",
            "features": [{
                "type": "Feature",
                "properties": {"district": "Patna"},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[85, 25], [86, 25], [86, 26], [85, 26], [85, 25]]],
                },
            }],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "districts.geojson"
            path.write_text(json.dumps(payload), encoding="utf-8")
            result = validate_source_file(path, "district_boundaries")
        self.assertEqual(result["status"], "ready")

    def test_invalid_district_geojson_is_blocked(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "districts.geojson"
            path.write_text(json.dumps({"type": "FeatureCollection", "features": []}), encoding="utf-8")
            result = validate_source_file(path, "district_boundaries")
        self.assertEqual(result["status"], "invalid_schema")

    def test_spatial_manifests_require_their_declared_schema(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sentinel = root / "sentinel.json"
            dem = root / "dem.json"
            (root / "mask.tif").write_bytes(b"mask")
            (root / "patna_dem.tif").write_bytes(b"dem")
            sentinel.write_text(json.dumps({"scenes": [{"scene_timestamp": "2025-08-01T00:00:00Z", "district": "Patna", "mask_path": "mask.tif"}]}), encoding="utf-8")
            dem.write_text(json.dumps({"elevation_path": "patna_dem.tif"}), encoding="utf-8")
            self.assertEqual(validate_source_file(sentinel, "sentinel1_inundation")["status"], "ready")
            self.assertEqual(validate_source_file(dem, "dem")["status"], "ready")

    def test_spatial_manifests_block_missing_assets(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sentinel = root / "sentinel.json"
            dem = root / "dem.json"
            sentinel.write_text(json.dumps({"scenes": [{"scene_timestamp": "2025-08-01T00:00:00Z", "district": "Patna", "mask_path": "missing.tif"}]}), encoding="utf-8")
            dem.write_text(json.dumps({"elevation_path": "missing_dem.tif"}), encoding="utf-8")
            self.assertEqual(validate_source_file(sentinel, "sentinel1_inundation")["status"], "invalid_schema")
            self.assertEqual(validate_source_file(dem, "dem")["status"], "invalid_schema")

    def test_invalid_spatial_manifests_are_blocked(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sentinel = root / "sentinel.json"
            dem = root / "dem.json"
            sentinel.write_text(json.dumps({"scenes": []}), encoding="utf-8")
            dem.write_text(json.dumps({"wrong_key": "dem.tif"}), encoding="utf-8")
            self.assertEqual(validate_source_file(sentinel, "sentinel1_inundation")["status"], "invalid_schema")
            self.assertEqual(validate_source_file(dem, "dem")["status"], "invalid_schema")

    def test_source_manifest_detects_changed_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "events.csv"
            path.write_text("Start Date,End Date,Bihar District\n", encoding="utf-8")
            manifest = build_source_manifest({"flood_events": path})
            path.write_text("changed\n", encoding="utf-8")
            result = validate_source_manifest(manifest)
        self.assertEqual(result["status"], "invalid")
        self.assertIn("flood_events:sha256_mismatch", result["errors"])

    def test_source_manifest_records_hash_and_size(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "events.csv"
            path.write_text("Start Date,End Date,Bihar District\n", encoding="utf-8")
            manifest = build_source_manifest({"flood_events": path})
        item = manifest["sources"]["flood_events"]
        self.assertEqual(item["status"], "present")
        self.assertIsNotNone(item["sha256"])
        self.assertGreater(item["size_bytes"], 0)
        self.assertEqual(manifest["schema_version"], 1)


if __name__ == "__main__":
    unittest.main()
