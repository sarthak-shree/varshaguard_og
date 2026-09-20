import unittest
import pandas as pd

from backend.bihar_v1.training_table import build_training_table, summarize_target


class TrainingTableTests(unittest.TestCase):
    def test_ongoing_events_are_excluded(self):
        obs = pd.DataFrame({
            "timestamp": pd.date_range("2026-01-01", periods=180, freq="h", tz="UTC"),
            "district": ["patna"] * 180,
            "variable": ["rain_mm"] * 180,
            "value": [1.0] * 180,
        })
        labels = pd.DataFrame({
            "timestamp": obs["timestamp"],
            "flood_event_start_next_24h": [0] * 180,
            "flood_event_ongoing": [0] * 180,
        })
        labels.loc[100:110, "flood_event_ongoing"] = 1
        labels.loc[99, "flood_event_start_next_24h"] = 1
        out = build_training_table(obs, labels, district="patna")
        self.assertNotIn(pd.Timestamp("2026-01-05 04:00:00", tz="UTC"), set(out["timestamp"]))
        self.assertEqual(summarize_target(out)["positive"], 1)

    def test_other_district_is_ignored(self):
        ts = pd.date_range("2026-01-01", periods=180, freq="h", tz="UTC")
        obs = pd.DataFrame({
            "timestamp": list(ts) * 2,
            "district": ["patna"] * 180 + ["muzaffarpur"] * 180,
            "variable": ["rain_mm"] * 360,
            "value": [1.0] * 360,
        })
        labels = pd.DataFrame({
            "timestamp": ts,
            "flood_event_start_next_24h": [0] * 180,
            "flood_event_ongoing": [0] * 180,
        })
        out = build_training_table(obs, labels, district="patna")
        self.assertTrue((out["district"] if "district" in out else pd.Series(["patna"])).isin(["patna"]).all())


if __name__ == "__main__":
    unittest.main()
