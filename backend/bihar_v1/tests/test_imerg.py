import unittest

import pandas as pd

from backend.bihar_v1.ingestion.imerg import normalize_precipitation


class ImergNormalizationTests(unittest.TestCase):
    def test_normalizes_and_sorts_records(self):
        payload = [
            {"timestamp": "2026-01-01T01:00:00Z", "latitude": 25.6, "longitude": 85.1, "rainfall_mm": 2.0},
            {"timestamp": "2026-01-01T00:30:00Z", "latitude": 25.6, "longitude": 85.1, "rainfall_mm": 1.0},
        ]
        result = normalize_precipitation(payload)
        self.assertEqual(result[0]["timestamp"], pd.Timestamp("2026-01-01T00:30:00Z"))
        self.assertEqual(result[1]["rainfall_mm"], 2.0)

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
