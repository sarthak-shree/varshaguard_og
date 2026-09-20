import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from backend.bihar_v1.model_training import train_patna_flood_model


class ModelTrainingTests(unittest.TestCase):
    @staticmethod
    def _write_split(root: Path, name: str, positive_events: list[str], positives: int) -> None:
        root.mkdir(parents=True, exist_ok=True)
        rows = []
        timestamps = pd.date_range("2025-01-01", periods=30, freq="h", tz="UTC")
        positive_positions = list(range(10, 10 + positives))
        for i, timestamp in enumerate(timestamps):
            is_positive = i in positive_positions
            event = positive_events[i % len(positive_events)] if is_positive else None
            rows.append({
                "timestamp": timestamp.isoformat(),
                "rain_1h": float(i % 7),
                "rain_24h": float((i % 7) * 2),
                "river_level_m": 50.0 + (i * 0.01),
                "river_rise_1h": float(i % 3) / 10.0,
                "flood_event_start_next_24h": int(is_positive),
                "flood_event_uei": event,
                "flood_event_start_timestamp": (
                    timestamp + pd.Timedelta(hours=12)
                ).isoformat() if is_positive else None,
                "flood_event_ongoing": 0,
            })
        pd.DataFrame(rows).to_csv(root / f"{name}.csv", index=False)

    def test_insufficient_events_returns_not_trainable_without_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "patna"
            self._write_split(root, "train", ["E1"], 10)
            self._write_split(root, "validation", ["E1"], 3)
            self._write_split(root, "test", ["E1"], 3)

            report = train_patna_flood_model(training_dir=Path(tmp))

            self.assertEqual(report["status"], "not_trainable")
            self.assertIn("blocking_details", report)
            self.assertNotIn("model_path", report)

    def test_train_and_report_metrics_when_readiness_gate_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "patna"
            self._write_split(root, "train", ["E1", "E2", "E3", "E4", "E5"], 10)
            self._write_split(root, "validation", ["E6", "E7"], 4)
            self._write_split(root, "test", ["E8", "E9"], 4)

            output = Path(tmp) / "models"
            report = train_patna_flood_model(
                training_dir=Path(tmp),
                output_dir=output,
            )

            self.assertEqual(report["status"], "trained")
            self.assertEqual(report["model"], "xgboost")
            self.assertNotIn("flood_event_start_timestamp", report["feature_columns"])
            for split_name in ("train", "validation", "test"):
                metrics = report["metrics"][split_name]
                self.assertIn("recall", metrics)
                self.assertIn("precision", metrics)
                self.assertIn("f1", metrics)
                self.assertIn("pr_auc", metrics)
                self.assertIn("roc_auc", metrics)
                self.assertIn("brier_score", metrics)
                self.assertIn("confusion_matrix", metrics)
                self.assertIn("calibration_bins", metrics)

            self.assertTrue(report["validation_threshold_analysis"])
            self.assertIsNone(report["operational_threshold"])
            self.assertTrue(Path(report["model_path"]).exists())
            self.assertTrue(Path(report["report_path"]).exists())
            persisted = json.loads(Path(report["report_path"]).read_text(encoding="utf-8"))
            self.assertEqual(persisted["status"], "trained")
            self.assertEqual(persisted["dataset_period"]["train_end"], "2025-01-02T05:00:00+00:00")
            manifest = json.loads((output / "patna_flood_model_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["dataset_period"]["train_start"], "2025-01-01T00:00:00+00:00")
            self.assertIn("test_end", manifest["dataset_period"])

    def test_missing_features_fail_explicitly(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "patna"
            self._write_split(root, "train", ["E1", "E2", "E3", "E4", "E5"], 10)
            self._write_split(root, "validation", ["E6", "E7"], 4)
            self._write_split(root, "test", ["E8", "E9"], 4)
            validation = pd.read_csv(root / "validation.csv")
            validation["rain_1h"] = "not-numeric"
            validation.to_csv(root / "validation.csv", index=False)

            with self.assertRaisesRegex(ValueError, "non-numeric or missing feature"):
                train_patna_flood_model(training_dir=Path(tmp))


if __name__ == "__main__":
    unittest.main()

