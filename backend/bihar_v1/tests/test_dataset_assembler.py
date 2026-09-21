import json
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
            self.assertEqual(report["districts"]["patna"]["status"], "not_evaluation_ready")
            self.assertTrue((root / "out" / "processed" / "dataset_audit.json").exists())
            self.assertTrue((root / "out" / "training" / "patna_flood_training.csv").exists())
            self.assertTrue((root / "out" / "training" / "patna" / "train.csv").exists())
            self.assertTrue((root / "out" / "training" / "patna" / "validation.csv").exists())
            self.assertTrue((root / "out" / "training" / "patna" / "test.csv").exists())
            self.assertIn("pre_isolation_split_summary", report["districts"]["patna"])
            self.assertIn("event_isolation_removed", report["districts"]["patna"])
            self.assertIn("muzaffarpur", report["districts"])
            self.assertIn("source_coverage_matrix", report)
            self.assertTrue((root / "out" / "processed" / "raw_source_manifest.json").exists())
            self.assertEqual(report["raw_source_manifest_schema_version"], 1)

            self.assertEqual(report["source_coverage_matrix"]["patna"]["river_rows"], 220)
            self.assertEqual(report["source_coverage_matrix"]["muzaffarpur"]["river_rows"], 0)
            self.assertEqual(report["districts"]["muzaffarpur"]["status"], "not_trainable")
            self.assertEqual(report["districts"]["muzaffarpur"]["readiness_blockers"]["heavy_rainfall"]["status"], "blocked")
            self.assertEqual(report["districts"]["muzaffarpur"]["readiness_blockers"]["river_flood"]["status"], "blocked")
            self.assertEqual(report["districts"]["muzaffarpur"]["readiness_blockers"]["inundation"]["status"], "blocked")

    def test_coverage_audit_is_station_aware(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            events = root / "events.csv"
            river = root / "river.csv"
            pd.DataFrame({
                "Start Date": ["08-01-2026"], "End Date": ["10-01-2026"],
                "Bihar District": ["Patna"], "UEI": ["E1"],
            }).to_csv(events, index=False)
            ts = ["01-01-2026 00:00", "01-01-2026 01:00", "01-01-2026 00:00", "01-01-2026 01:00"]
            pd.DataFrame({
                "District": ["PATNA"] * 4,
                "Station": ["Kharuara_1"] * 4,
                "Agency": ["CWC", "CWC", "CWC", "CWC"] ,
                "Data Acquisition Time": ts,
                "River Water Level Telemetry Hourly (meter)": [50.0, 50.1, 50.2, 50.3],
            }).to_csv(river, index=False)
            report = assemble(river=river, events=events, output_root=root / "out")
            audit = report["sources"]["river"]
            self.assertEqual(audit["duplicate_observation_keys"], 2)
            self.assertEqual(audit["gaps_over_1h"], 0)

    def test_duplicate_rows_do_not_create_zero_hour_intervals(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            events = root / "events.csv"
            river = root / "river.csv"
            pd.DataFrame({
                "Start Date": ["08-01-2026"], "End Date": ["10-01-2026"],
                "Bihar District": ["Patna"], "UEI": ["E1"],
            }).to_csv(events, index=False)
            pd.DataFrame({
                "District": ["PATNA"] * 3,
                "Station": ["Kharuara_1"] * 3,
                "Agency": ["CWC"] * 3,
                "Data Acquisition Time": ["01-01-2026 00:00", "01-01-2026 00:00", "01-01-2026 01:00"],
                "River Water Level Telemetry Hourly (meter)": [50.0, 50.0, 50.1],
            }).to_csv(river, index=False)
            report = assemble(river=river, events=events, output_root=root / "out")
            self.assertEqual(report["sources"]["river"]["duplicate_observation_keys"], 1)
            self.assertEqual(report["sources"]["river"]["median_interval_hours"], 1.0)

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

    def test_empty_district_still_reports_model_readiness(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            events = root / "events.csv"
            pd.DataFrame({
                "Start Date": ["08-01-2026"],
                "End Date": ["10-01-2026"],
                "Bihar District": ["Muzaffarpur"],
                "UEI": ["E1"],
            }).to_csv(events, index=False)

            report = assemble(events=events, output_root=root / "out")
            readiness = report["districts"]["muzaffarpur"]["model_readiness"]
            self.assertEqual(readiness["status"], "blocked")
            self.assertIn("heavy_rainfall", readiness["models"])
            self.assertIn("river_flood", readiness["models"])
            self.assertIn("inundation", readiness["models"])

    def test_missing_event_inventory_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                assemble(output_root=Path(tmp) / "out")

    def test_district_boundaries_are_passed_to_contract_and_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            events = root / "events.csv"
            boundaries = root / "districts.geojson"
            pd.DataFrame({
                "Start Date": ["08-01-2026"], "End Date": ["10-01-2026"],
                "Bihar District": ["Patna"], "UEI": ["E1"],
            }).to_csv(events, index=False)
            boundaries.write_text(
                '{"type":"FeatureCollection","features":[{"type":"Feature",'
                '"properties":{"district":"Patna"},"geometry":{"type":"Polygon",'
                '"coordinates":[[[85.0,25.0],[85.1,25.0],[85.1,25.1],[85.0,25.1],[85.0,25.0]]]}}]}',
                encoding="utf-8",
            )
            report = assemble(
                events=events,
                district_boundaries=boundaries,
                output_root=root / "out",
            )
            contract = report["data_acquisition_contract"]
            self.assertEqual(contract["sources"]["district_boundaries"]["status"], "ready")
            manifest = json.loads((root / "out" / "processed" / "raw_source_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["sources"]["district_boundaries"]["status"], "present")

    def test_dataset_audit_exposes_data_acquisition_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            events = root / "events.csv"
            pd.DataFrame({
                "Start Date": ["08-01-2026"], "End Date": ["10-01-2026"],
                "Bihar District": ["Patna"], "UEI": ["E1"],
            }).to_csv(events, index=False)
            report = assemble(events=events, output_root=root / "out")

        contract = report["data_acquisition_contract"]
        self.assertEqual(contract["status"], "blocked")
        self.assertEqual(contract["sources"]["flood_events"]["status"], "ready")
        self.assertEqual(contract["sources"]["hourly_rainfall"]["status"], "missing")
        self.assertEqual(contract["sources"]["river_threshold"]["status"], "missing")

if __name__ == "__main__":
    unittest.main()
