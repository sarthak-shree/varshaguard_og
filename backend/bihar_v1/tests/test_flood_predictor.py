import tempfile
import unittest
from pathlib import Path

import joblib
import numpy as np
from sklearn.dummy import DummyClassifier

from backend.bihar_v1.prediction.flood_predictor import predict


class FloodPredictorTests(unittest.TestCase):
    def test_missing_model_is_explicit(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = predict("patna", {"rain_1h": 10}, model_file=Path(tmp) / "missing.joblib")
            self.assertEqual(result.status, "model_not_trained")
            self.assertIsNone(result.probability)

    def test_model_feature_order_is_respected(self):
        with tempfile.TemporaryDirectory() as tmp:
            model = DummyClassifier(strategy="prior")
            model.fit(
                np.array([[0.0, 0.0], [1.0, 1.0], [0.0, 1.0], [1.0, 0.0]]),
                np.array([0, 1, 0, 1]),
            )
            model.feature_names_in_ = np.array(["rain_1h", "river_level_m"])
            path = Path(tmp) / "patna.joblib"
            joblib.dump(model, path)

            result = predict(
                "patna",
                {"river_level_m": 55, "rain_1h": 12},
                model_file=path,
            )
            self.assertEqual(result.status, "ok")
            self.assertIsNotNone(result.probability)
            self.assertEqual(result.details["features"], ["rain_1h", "river_level_m"])

    def test_missing_feature_returns_model_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            model = DummyClassifier(strategy="prior")
            model.fit(np.array([[0.0], [1.0]]), np.array([0, 1]))
            model.feature_names_in_ = np.array(["rain_1h"])
            path = Path(tmp) / "patna.joblib"
            joblib.dump(model, path)

            result = predict("patna", {"river_level_m": 55}, model_file=path)
            self.assertEqual(result.status, "model_error")
            self.assertIn("Missing model features", result.details["error"])


if __name__ == "__main__":
    unittest.main()
