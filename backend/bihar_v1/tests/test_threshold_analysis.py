import unittest

import numpy as np
import pandas as pd

from backend.bihar_v1.threshold_analysis import threshold_analysis
from backend.bihar_v1.model_training import TARGET_COLUMN


class ThresholdAnalysisTests(unittest.TestCase):
    def test_reports_candidate_thresholds_without_selecting_one(self):
        frame = pd.DataFrame({TARGET_COLUMN: [0, 0, 1, 1]})
        rows = threshold_analysis(frame, np.array([0.1, 0.4, 0.7, 0.9]), thresholds=[0.5, 0.8])
        self.assertEqual([row["threshold"] for row in rows], [0.5, 0.8])
        self.assertIn("recall", rows[0])
        self.assertIn("precision", rows[0])
        self.assertIn("f1", rows[0])
        self.assertIn("false_alarm_rate", rows[0])
        self.assertIn("miss_rate", rows[0])
        self.assertEqual(rows[0]["true_positive"] + rows[0]["false_negative"], 2)

    def test_reports_event_level_lead_time_when_event_metadata_exists(self):
        frame = pd.DataFrame({
            TARGET_COLUMN: [1, 1, 0, 1],
            "flood_event_uei": ["E1", "E1", None, "E2"],
            "timestamp": pd.to_datetime([
                "2025-01-01T00:00:00Z",
                "2025-01-01T06:00:00Z",
                "2025-01-01T12:00:00Z",
                "2025-01-02T00:00:00Z",
            ]),
            "flood_event_start_timestamp": pd.to_datetime([
                "2025-01-01T12:00:00Z",
                "2025-01-01T12:00:00Z",
                None,
                "2025-01-02T12:00:00Z",
            ]),
        })
        rows = threshold_analysis(frame, np.array([0.8, 0.9, 0.1, 0.9]), thresholds=[0.5])
        self.assertEqual(rows[0]["events_with_predicted_positive"], 2)
        self.assertEqual(rows[0]["mean_lead_hours"], 12.0)
        self.assertEqual(rows[0]["median_lead_hours"], 12.0)
        self.assertEqual(rows[0]["events_detected_at_least_6h"], 2)
        self.assertEqual(rows[0]["events_detected_at_least_12h"], 2)
        self.assertEqual(rows[0]["events_detected_at_least_24h"], 0)

    def test_one_class_validation_is_rejected(self):
        frame = pd.DataFrame({TARGET_COLUMN: [0, 0]})
        with self.assertRaisesRegex(ValueError, "both positive and negative"):
            threshold_analysis(frame, np.array([0.2, 0.8]))

    def test_probability_length_must_match(self):
        frame = pd.DataFrame({TARGET_COLUMN: [0, 1]})
        with self.assertRaises(ValueError):
            threshold_analysis(frame, np.array([0.5]))

    def test_probability_range_is_validated(self):
        frame = pd.DataFrame({TARGET_COLUMN: [0, 1]})
        with self.assertRaises(ValueError):
            threshold_analysis(frame, np.array([-0.1, 1.1]))

    def test_threshold_range_is_validated(self):
        frame = pd.DataFrame({TARGET_COLUMN: [0, 1]})
        with self.assertRaises(ValueError):
            threshold_analysis(frame, np.array([0.2, 0.8]), thresholds=[0.0])


if __name__ == "__main__":
    unittest.main()
