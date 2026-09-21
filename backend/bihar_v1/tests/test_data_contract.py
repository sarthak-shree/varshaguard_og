import tempfile
import unittest
from pathlib import Path

import pandas as pd

from backend.bihar_v1.data_contract import (
    DISTRICT_REQUIRED_SOURCES,
    source_contract,
    validate_contract,
    validate_source_file,
)


class DataContractTests(unittest.TestCase):
    def test_both_districts_require_same_core_sources(self):
        self.assertEqual(
            set(DISTRICT_REQUIRED_SOURCES["patna"]),
            {
                "hourly_rainfall",
                "river_level",
                "river_threshold",
                "flood_events",
                "sentinel1_inundation",
                "dem",
            },
        )
        self.assertEqual(
            set(DISTRICT_REQUIRED_SOURCES["muzaffarpur"]),
            set(DISTRICT_REQUIRED_SOURCES["patna"]),
        )

    def test_unknown_source_is_rejected(self):
        with self.assertRaises(ValueError):
            source_contract("made_up_source")

    def test_missing_source_blocks_contract(self):
        result = validate_contract({})
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(len(result["blockers"]), 6)

    def test_csv_schema_is_checked(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rain.csv"
            pd.DataFrame(
                {
                    "Data Acquisition Time": ["01/01/2025 00:00"],
                    "District": ["Patna"],
                    "Station": ["Example"],
                }
            ).to_csv(path, index=False)

            result = validate_source_file(path, "hourly_rainfall")

        self.assertEqual(result["status"], "invalid_schema")
        self.assertIn("Telemetry Hourly Rainfall (mm)", result["missing_columns"])

    def test_valid_csv_source_passes_structural_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rain.csv"
            pd.DataFrame(
                {
                    "Data Acquisition Time": ["01/01/2025 00:00"],
                    "District": ["Patna"],
                    "Station": ["Example"],
                    "Telemetry Hourly Rainfall (mm)": [2.0],
                }
            ).to_csv(path, index=False)

            result = validate_source_file(path, "hourly_rainfall")

        self.assertEqual(result["status"], "ready")


if __name__ == "__main__":
    unittest.main()
