import tempfile
import unittest
from pathlib import Path

import pandas as pd

from backend.bihar_v1.dataset_assembler import assemble


class DatasetAssemblerTests(unittest.TestCase):
    def test_filters_supported_stations_and_keeps_daily_separate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            hourly = root / "hourly.csv"
            daily = root / "daily.csv"
            river = root / "river.csv"
            events = root / "events.csv"

            ts = pd.date_range("2026-01-01", periods=220, freq="h")
            pd.DataFrame({
                "District": ["PATNA"] * 220 + ["PATNA"] * 2,
                "Station": ["Kharuara_1"] * 220 + ["Unsupported"] * 2,
                "Agency": ["CWC"] * 222,
                "Data Acquisition Time": [x.strftime("%d-%m-%Y %H:%M") for x in ts] + ["01-01-2026 00:00", "01-01-2026 01:00"],
                "Telemetry Hourly Rainfall (mm)": [1.0] * 222,
            }).to_csv(hourly, index=False)

            pd.DataFrame({
                "District": ["PATNA", "PATNA"],
                "Station": ["Gandhi Ghat", "Unsupported"],
                "Agency": ["Bihar", "Bihar"],
                "Data Acquisition Time": ["01-01-2026 08:00", "01-01-2026 09:00"],
                "Manual Rainfall (mm)": [12.0, 99.0],
            }).to_csv(daily, index=False)

            pd.DataFrame({
                "District": ["PATNA"] * 220 + ["MUZAFFARPUR"],
                "Station": ["Kharuara_1"] * 220 + ["Benibad"],
                "Agency": ["CWC"] * 221,
                "Data Acquisition Time": [x.strftime("%d-%m-%Y %H:%M") for x in ts] + ["01-01-2026 00:00"],
                "River Water Level Telemetry Hourly (meter)": [50.0] * 221,
                "River": ["Ganga"] * 220 + ["Bagmati"],
            }).to_csv(river, index=False)

            pd.DataFrame({
                "Start Date": ["08-01-2026"],
                "End Date": ["10-01-2026"],
                "Bihar District": ["Patna"],
                "UEI": ["E1"],
            }).to_csv(events, index=False)

            report = assemble(
                hourly_rainfall=hourly,
                daily_rainfall=daily,
                river=river,
                events=events,
                output_root=root / "out",
            )

            self.assertEqual(report["sources"]["rainfall_daily"]["rows"], 1)
            self.assertEqual(report["sources"]["river"]["rows"], 220)
            self.assertEqual(report["districts"]["patna"]["status"], "trainable")
            self.assertTrue((root / "out" / "processed" / "dataset_audit.json").exists())
            self.assertTrue((root / "out" / "training" / "patna_flood_training.csv").exists())
            self.assertIn("muzaffarpur", report["districts"])
            self.assertEqual(report["districts"]["muzaffarpur"]["status"], "not_trainable")

    def test_muzaffarpur_without_supported_river_is_not_synthesized(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            events = root / "events.csv"
            river = root / "river.csv"

            pd.DataFrame({
                "Start Date": ["08-01-2026"],
                "End Date": ["10-01-2026"],
                "Bihar District": ["Muzaffarpur"],
                "UEI": ["E1"],
            }).to_csv(events, index=False)
            pd.DataFrame({
                "District": ["MUZAFFARPUR"] * 2,
                "Station": ["Benibad"] * 2,
                "Agency": ["CWC"] * 2,
                "Data Acquisition Time": ["01-01-2026 00:00", "01-01-2026 01:00"],
                "River Water Level Telemetry Hourly (meter)": [54.0, 54.1],
            }).to_csv(river, index=False)

            report = assemble(river=river, events=events, output_root=root / "out")
            self.assertEqual(report["districts"]["muzaffarpur"]["status"], "not_trainable")
            self.assertEqual(report["districts"]["muzaffarpur"]["training"]["rows"], 0)

    def test_missing_event_inventory_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                assemble(output_root=Path(tmp) / "out")


if __name__ == "__main__":
    unittest.main()
