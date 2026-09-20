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

    def test_manifest_schema_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            model = DummyClassifier(strategy="prior")
            model.fit(np.array([[0.0], [1.0]]), np.array([0, 1]))
            model.feature_names_in_ = np.array(["rain_1h"])
            path = Path(tmp) / "patna_flood_xgboost.joblib"
            joblib.dump(model, path)
            (Path(tmp) / "patna_flood_model_manifest.json").write_text(
                '{"schema_version": 1, "district": "patna", '
                '"model_type": "xgboost_binary_classifier", '
                '"target": "flood_event_start_next_24h", "horizon_hours": 24, '
                '"feature_columns": ["river_level_m"], '
                '"operational_threshold": null, '
                '"operational_threshold_status": "not_calibrated"}',
                encoding="utf-8",
            )

            result = predict("patna", {"rain_1h": 12}, model_file=path)
            self.assertEqual(result.status, "model_error")
            self.assertIn("feature schema", result.details["error"])

    def test_manifest_checksum_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            model = DummyClassifier(strategy="prior")
            model.fit(np.array([[0.0], [1.0]]), np.array([0, 1]))
            model.feature_names_in_ = np.array(["rain_1h"])
            path = Path(tmp) / "patna_flood_xgboost.joblib"
            joblib.dump(model, path)
            (Path(tmp) / "patna_flood_model_manifest.json").write_text(
                '{"schema_version": 1, "district": "patna", '
                '"model_type": "xgboost_binary_classifier", '
                '"target": "flood_event_start_next_24h", "horizon_hours": 24, '
                '"feature_columns": ["rain_1h"], "model_sha256": "wrong", '
                '"operational_threshold": null, '
                '"operational_threshold_status": "not_calibrated"}',
                encoding="utf-8",
            )
            result = predict("patna", {"rain_1h": 12}, model_file=path)
            self.assertEqual(result.status, "model_error")
            self.assertIn("checksum", result.details["error"])


if __name__ == "__main__":
    unittest.main()
