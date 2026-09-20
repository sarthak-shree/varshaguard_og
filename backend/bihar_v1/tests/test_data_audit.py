import tempfile
import unittest
from pathlib import Path
import pandas as pd

from backend.bihar_v1.data_audit import audit_csv


class DataAuditTests(unittest.TestCase):
    def test_same_station_timestamp_from_different_agencies_is_not_duplicate(self):
        frame = pd.DataFrame([
            {"Data Acquisition Time": "20/09/2026 10:00", "Station": "A", "Agency": "IMD", "Telemetry Hourly Rainfall (mm)": 1.0},
            {"Data Acquisition Time": "20/09/2026 10:00", "Station": "A", "Agency": "CWC", "Telemetry Hourly Rainfall (mm)": 2.0},
        ])
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "raw.csv"
            frame.to_csv(path, index=False)
            result = audit_csv(path)
        self.assertEqual(result["duplicate_observation_keys"], 0)

    def test_exact_station_agency_duplicate_is_reported(self):
        frame = pd.DataFrame([
            {"Data Acquisition Time": "20/09/2026 10:00", "Station": "A", "Agency": "IMD", "Telemetry Hourly Rainfall (mm)": 1.0},
            {"Data Acquisition Time": "20/09/2026 10:00", "Station": "A", "Agency": "IMD", "Telemetry Hourly Rainfall (mm)": 1.0},
        ])
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "raw.csv"
            frame.to_csv(path, index=False)
            result = audit_csv(path)
        self.assertEqual(result["duplicate_observation_keys"], 1)


if __name__ == "__main__":
    unittest.main()
