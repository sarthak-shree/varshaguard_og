import unittest
import pandas as pd

from backend.bihar_v1.training_table import build_training_table, summarize_target


class TrainingTableTests(unittest.TestCase):
    def test_ongoing_events_are_excluded(self):
        obs = pd.DataFrame({
            "timestamp": pd.date_range("2026-01-01", periods=220, freq="h", tz="UTC"),
            "district": ["patna"] * 220,
            "variable": ["rain_mm"] * 220,
            "value": [1.0] * 220,
        })
        labels = pd.DataFrame({
            "timestamp": obs["timestamp"],
            "flood_event_start_next_24h": [0] * 220,
            "flood_event_ongoing": [0] * 220,
        })
        labels.loc[180:190, "flood_event_ongoing"] = 1
        labels.loc[179, "flood_event_start_next_24h"] = 1
        out = build_training_table(obs, labels, district="patna")
        self.assertNotIn(pd.Timestamp("2026-01-08 12:00:00", tz="UTC"), set(out["timestamp"]))
        self.assertEqual(summarize_target(out)["positive"], 1)

    def test_other_district_is_ignored(self):
        ts = pd.date_range("2026-01-01", periods=220, freq="h", tz="UTC")
        obs = pd.DataFrame({
            "timestamp": list(ts) * 2,
            "district": ["patna"] * 220 + ["muzaffarpur"] * 220,
            "variable": ["rain_mm"] * 440,
            "value": [1.0] * 440,
        })
        labels = pd.DataFrame({
            "timestamp": ts,
            "flood_event_start_next_24h": [0] * 220,
            "flood_event_ongoing": [0] * 220,
        })
        out = build_training_table(obs, labels, district="patna")
        self.assertEqual(len(out), 53)


if __name__ == "__main__":
    unittest.main()
