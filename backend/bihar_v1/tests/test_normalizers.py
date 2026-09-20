import unittest
import pandas as pd

from backend.bihar_v1.ingestion.normalizers import normalize_rainfall_csv, normalize_river_csv


class NormalizerTests(unittest.TestCase):
    def test_rainfall_normalizer_converts_local_time_to_utc(self):
        frame = pd.DataFrame([{
            "District": "PATNA",
            "Station": "Test Rain",
            "Agency": "Bihar",
            "Data Acquisition Time": "20-09-2026 08:00",
            "Telemetry Hourly Rainfall (mm)": 12.5,
        }])
        obs = normalize_rainfall_csv(frame, value_column="Telemetry Hourly Rainfall (mm)")
        self.assertEqual(obs[0].district, "patna")
        self.assertEqual(obs[0].value, 12.5)
        self.assertEqual(obs[0].timestamp, "2026-09-20T02:30:00+00:00")

    def test_rainfall_normalizer_handles_non_identifier_value_column(self):
        frame = pd.DataFrame([{
            "District": "PATNA",
            "Station": "Gandhighat",
            "Agency": "Bihar",
            "Data Acquisition Time": "20-09-2026 08:00",
            "Manual Daily Rainfall (mm)": 18.0,
        }])
        obs = normalize_rainfall_csv(frame, value_column="Manual Daily Rainfall (mm)")
        self.assertEqual(obs[0].value, 18.0)

    def test_river_normalizer_preserves_station_and_value(self):
        frame = pd.DataFrame([{
            "District": "MUZAFFARPUR",
            "Station": "Benibad",
            "Agency": "CWC",
            "Data Acquisition Time": "20-09-2026 09:00",
            "River Water Level Telemetry Hourly (meter)": 54.2,
            "River": "Bagmati",
        }])
        obs = normalize_river_csv(frame, value_column="River Water Level Telemetry Hourly (meter)")
        self.assertEqual(obs[0].district, "muzaffarpur")
        self.assertEqual(obs[0].station_id, "Benibad")
        self.assertAlmostEqual(obs[0].value, 54.2)


if __name__ == "__main__":
    unittest.main()
