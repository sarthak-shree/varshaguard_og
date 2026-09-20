import tempfile
import unittest

import pandas as pd

from backend.bihar_v1.labeling import build_24h_event_labels, load_district_events


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

    def test_inventory_two_digit_years_are_parsed_in_source_century(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            pd.DataFrame({
                "Start Date": ["08/09/67 00:00", "04/07/23 00:00"],
                "End Date": ["09/09/67 00:00", "05/07/23 00:00"],
                "Bihar District": ["Patna", "Patna"],
                "UEI": ["E1", "E2"],
            }).to_csv(f.name, index=False)
            out = load_district_events(f.name)

        self.assertEqual(out["start"].dt.year.tolist(), [1967, 2023])


if __name__ == "__main__":
    unittest.main()
