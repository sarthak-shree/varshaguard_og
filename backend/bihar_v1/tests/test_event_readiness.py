import unittest
import pandas as pd
from backend.bihar_v1.event_readiness import summarize_event_coverage

class EventReadinessTests(unittest.TestCase):
    def test_deduplicates_event_ids_and_reports_years(self):
        events = pd.DataFrame({
            "district": ["patna", "patna", "patna", "muzaffarpur"],
            "start": ["2021-01-01", "2021-01-01", "2023-07-01", "2022-06-01"],
            "end": ["2021-01-02", "2021-01-02", "2023-07-02", "2022-06-02"],
            "uei": ["E1", "E1", "E2", "M1"],
        })
        result = summarize_event_coverage(events, district="patna")
        self.assertEqual(result["records"], 3)
        self.assertEqual(result["unique_events"], 2)
        self.assertEqual(result["events_by_year"], {"2021": 1, "2023": 1})

    def test_missing_event_columns_rejected(self):
        with self.assertRaises(ValueError):
            summarize_event_coverage(pd.DataFrame({"district": ["patna"]}), district="patna")

if __name__ == "__main__":
    unittest.main()
