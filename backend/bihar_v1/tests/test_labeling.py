import unittest
import pandas as pd

from backend.bihar_v1.labeling import build_24h_event_labels


class LabelingTests(unittest.TestCase):
    def test_event_start_gets_positive_lead_window(self):
        events = pd.DataFrame({
            "district": ["patna"],
            "start": [pd.Timestamp("2026-07-10")],
            "end": [pd.Timestamp("2026-07-12")],
            "UEI": ["E1"],
        })
        timestamps = pd.Series(pd.date_range("2026-07-09", periods=97, freq="h", tz="UTC"))
        out = build_24h_event_labels(timestamps, events, district="patna")
        start = pd.Timestamp("2026-07-10", tz="UTC")
        self.assertEqual(int(out.loc[out.timestamp == start - pd.Timedelta(hours=1), "flood_event_start_next_24h"].iloc[0]), 1)
        self.assertEqual(int(out.loc[out.timestamp == start, "flood_event_start_next_24h"].iloc[0]), 0)
        self.assertEqual(int(out.loc[out.timestamp == start, "flood_event_ongoing"].iloc[0]), 1)

    def test_other_district_is_not_labeled(self):
        events = pd.DataFrame({
            "district": ["patna"],
            "start": [pd.Timestamp("2026-07-10")],
            "end": [pd.Timestamp("2026-07-12")],
            "UEI": ["E1"],
        })
        timestamps = pd.Series(pd.date_range("2026-07-09", periods=48, freq="h", tz="UTC"))
        out = build_24h_event_labels(timestamps, events, district="muzaffarpur")
        self.assertEqual(int(out["flood_event_start_next_24h"].sum()), 0)


if __name__ == "__main__":
    unittest.main()
