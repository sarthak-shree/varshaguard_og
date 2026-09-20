import unittest

import pandas as pd

from backend.bihar_v1.splitting import (
    chronological_split,
    split_summary,
    validate_split_readiness,
)


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

    def test_summary_reports_class_balance_and_events(self):
        frame = pd.DataFrame({
            "timestamp": pd.date_range("2025-01-01", periods=4, freq="h", tz="UTC"),
            "flood_event_start_next_24h": [0, 1, 0, 1],
            "flood_event_uei": [pd.NA, "E1", pd.NA, "E1"],
        })
        summary = split_summary({"train": frame})
        self.assertEqual(summary["train"]["rows"], 4)
        self.assertEqual(summary["train"]["positive"], 2)
        self.assertEqual(summary["train"]["negative"], 2)
        self.assertEqual(summary["train"]["positive_rate"], 0.5)
        self.assertEqual(summary["train"]["positive_events"], 1)

    def test_readiness_requires_independent_events(self):
        frame = pd.DataFrame({
            "timestamp": pd.date_range("2025-01-01", periods=30, freq="h", tz="UTC"),
            "flood_event_start_next_24h": [1] * 10 + [0] * 20,
            "flood_event_uei": ["E1"] * 10 + [pd.NA] * 20,
        })
        splits = {"train": frame, "validation": frame, "test": frame}
        readiness = validate_split_readiness(
            splits,
            minimum_positive_train=5,
            minimum_positive_validation=5,
            minimum_positive_test=5,
            minimum_events_train=2,
            minimum_events_validation=2,
            minimum_events_test=2,
        )
        self.assertFalse(readiness["ready_for_model_evaluation"])
        self.assertFalse(readiness["splits"]["train"]["ready"])
        self.assertEqual(readiness["splits"]["train"]["positive_samples"], 10)
        self.assertEqual(readiness["splits"]["train"]["positive_events"], 1)


if __name__ == "__main__":
    unittest.main()
