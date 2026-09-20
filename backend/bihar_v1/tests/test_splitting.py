import unittest

import pandas as pd

from backend.bihar_v1.splitting import chronological_split, split_summary


class SplittingTests(unittest.TestCase):
    def test_split_is_chronological_and_purged(self):
        ts = pd.date_range("2025-01-01", periods=1000, freq="h", tz="UTC")
        frame = pd.DataFrame({
            "timestamp": ts,
            "flood_event_start_next_24h": [1 if i in (200, 700) else 0 for i in range(1000)],
        })
        splits = chronological_split(frame, purge_hours=24)

        self.assertLess(splits["train"]["timestamp"].max(), splits["validation"]["timestamp"].min())
        self.assertLess(splits["validation"]["timestamp"].max(), splits["test"]["timestamp"].min())
        self.assertGreaterEqual(
            (splits["validation"]["timestamp"].min() - splits["train"]["timestamp"].max()).total_seconds(),
            24 * 3600,
        )
        self.assertGreaterEqual(
            (splits["test"]["timestamp"].min() - splits["validation"]["timestamp"].max()).total_seconds(),
            24 * 3600,
        )

    def test_summary_reports_class_balance(self):
        frame = pd.DataFrame({
            "timestamp": pd.date_range("2025-01-01", periods=4, freq="h", tz="UTC"),
            "flood_event_start_next_24h": [0, 1, 0, 1],
        })
        summary = split_summary({"train": frame})
        self.assertEqual(summary["train"]["rows"], 4)
        self.assertEqual(summary["train"]["positive"], 2)
        self.assertEqual(summary["train"]["negative"], 2)
        self.assertEqual(summary["train"]["positive_rate"], 0.5)


if __name__ == "__main__":
    unittest.main()
