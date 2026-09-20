import unittest

import pandas as pd

from backend.bihar_v1.readiness import (
    summarize_hourly_coverage,
    summarize_training_window_coverage,
)


class ReadinessTests(unittest.TestCase):
    def test_hourly_coverage_ignores_duplicates_and_counts_continuous_windows(self):
        ts = pd.date_range("2026-01-01", periods=170, freq="h")
        frame = pd.DataFrame({
            "timestamp": list(ts) + [ts[0], ts[1]],
            "station_id": ["A"] * 172,
        })
        result = summarize_hourly_coverage(frame, continuous_window_hours=168)

        self.assertEqual(result["rows"], 172)
        self.assertEqual(result["unique_hours"], 170)
        self.assertEqual(result["duplicate_rows"], 2)
        self.assertEqual(result["stations_with_continuous_window"], 1)
        self.assertEqual(result["usable_continuous_windows"], 3)

    def test_gap_breaks_continuous_window(self):
        ts = list(pd.date_range("2026-01-01", periods=100, freq="h"))
        ts += list(pd.date_range("2026-01-06", periods=100, freq="h"))
        frame = pd.DataFrame({"timestamp": ts, "station_id": ["A"] * len(ts)})

        result = summarize_hourly_coverage(frame, continuous_window_hours=168)

        self.assertEqual(result["stations_with_continuous_window"], 0)
        self.assertEqual(result["usable_continuous_windows"], 0)

    def test_training_window_coverage_reports_complete_feature_rows(self):
        table = pd.DataFrame({
            "rain_1h": [1.0, 1.0, None],
            "rain_168h": [1.0, None, 1.0],
            "river_level_lag_24h": [2.0, 2.0, 2.0],
        })
        result = summarize_training_window_coverage(table)

        self.assertEqual(result["rows"], 3)
        self.assertEqual(result["complete_feature_rows"], 1)
        self.assertAlmostEqual(result["feature_window_coverage_ratio"], 1 / 3)


if __name__ == "__main__":
    unittest.main()
