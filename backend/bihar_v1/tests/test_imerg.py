import unittest

import pandas as pd

from backend.bihar_v1.ingestion.imerg import normalize_precipitation, precipitation_to_observations


class ImergNormalizationTests(unittest.TestCase):
    def test_normalizes_and_sorts_records(self):
        payload = [
            {"timestamp": "2026-01-01T01:00:00Z", "latitude": 25.6, "longitude": 85.1, "rainfall_mm": 2.0},
            {"timestamp": "2026-01-01T00:30:00Z", "latitude": 25.6, "longitude": 85.1, "rainfall_mm": 1.0},
        ]
        result = normalize_precipitation(payload)
        self.assertEqual(result[0]["timestamp"], pd.Timestamp("2026-01-01T00:30:00Z"))
        self.assertEqual(result[1]["rainfall_mm"], 2.0)

    def test_converts_to_observation_contract(self):
        records = [{
            "timestamp": "2026-01-01T00:30:00Z",
            "latitude": 25.6,
            "longitude": 85.1,
            "rainfall_mm": 1.5,
        }]
        result = precipitation_to_observations(records)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].variable, "rain_mm")
        self.assertEqual(result[0].source, "nasa_gpm_imerg")
        self.assertEqual(result[0].metadata["latitude"], 25.6)

    def test_rejects_missing_columns(self):
        with self.assertRaises(ValueError):
            normalize_precipitation([{"timestamp": "2026-01-01T00:00:00Z"}])

    def test_rejects_invalid_numeric_values(self):
        with self.assertRaises(ValueError):
            normalize_precipitation([{
                "timestamp": "2026-01-01T00:00:00Z",
                "latitude": 25.6,
                "longitude": 85.1,
                "rainfall_mm": "bad",
            }])


if __name__ == "__main__":
    unittest.main()
