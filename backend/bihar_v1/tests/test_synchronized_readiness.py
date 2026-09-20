import unittest
import pandas as pd
from backend.bihar_v1.synchronized_readiness import summarize_synchronized_hourly_coverage

class SynchronizedReadinessTests(unittest.TestCase):
    def test_only_common_hours_count(self):
        rain = pd.DataFrame({
            "timestamp": pd.date_range("2026-01-01", periods=170, freq="h"),
            "station_id": ["rain"] * 170,
        })
        river = pd.DataFrame({
            "timestamp": pd.date_range("2026-01-01 01:00", periods=170, freq="h"),
            "station_id": ["river"] * 170,
        })
        result = summarize_synchronized_hourly_coverage(rain, river)
        self.assertEqual(result["synchronized_hours"], 169)
        self.assertEqual(result["stations_with_continuous_window"], 1)
        self.assertEqual(result["usable_continuous_windows"], 2)

    def test_gap_blocks_continuous_window(self):
        rain_ts = list(pd.date_range("2026-01-01", periods=100, freq="h")) + list(pd.date_range("2026-01-06", periods=100, freq="h"))
        river_ts = list(pd.date_range("2026-01-01", periods=200, freq="h"))
        rain = pd.DataFrame({"timestamp": rain_ts, "station_id": ["rain"] * len(rain_ts)})
        river = pd.DataFrame({"timestamp": river_ts, "station_id": ["river"] * len(river_ts)})
        result = summarize_synchronized_hourly_coverage(rain, river)
        self.assertEqual(result["stations_with_continuous_window"], 0)
        self.assertEqual(result["usable_continuous_windows"], 0)

if __name__ == "__main__":
    unittest.main()
