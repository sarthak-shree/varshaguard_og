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
