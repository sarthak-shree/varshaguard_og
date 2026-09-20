import unittest

from backend.bihar_v1.services.risk_fusion import fuse


class RiskFusionTests(unittest.TestCase):
    def test_no_probabilities_is_not_ready(self):
        state = fuse("patna", None, None, None)
        self.assertEqual(state.risk_level, "not_ready")

    def test_probabilities_do_not_create_uncalibrated_alert_level(self):
        state = fuse("patna", 0.9, 0.8, None)
        self.assertEqual(state.risk_level, "not_ready")
        self.assertEqual(state.details["reason"], "operational_thresholds_not_calibrated")

    def test_calibrated_thresholds_produce_level(self):
        state = fuse(
            "patna",
            0.2,
            0.81,
            0.1,
            thresholds={"low": 0.3, "moderate": 0.6, "high": 0.8},
        )
        self.assertEqual(state.risk_level, "high")
        self.assertEqual(state.details["method"], "calibrated_max_probability")

    def test_invalid_threshold_order_is_rejected(self):
        with self.assertRaises(ValueError):
            fuse("patna", 0.5, 0.5, 0.5, thresholds={"low": 0.8, "moderate": 0.6, "high": 0.9})


if __name__ == "__main__":
    unittest.main()
