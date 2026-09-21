import unittest

import pandas as pd

from backend.bihar_v1.readiness import (
    summarize_hourly_coverage,
    summarize_training_window_coverage,
)


class ReadinessTests(unittest.TestCase):
    def test_hourly_coverage_ignores_duplicates_and_counts_continuous_windows(self):
        ts = pd.date_range("2026-01-01", periods=170, freq="h")
        frame = pd.DataFrame({
            "timestamp": list(ts) + [ts[0], ts[1]],
            "station_id": ["A"] * 172,
        })
        result = summarize_hourly_coverage(frame, continuous_window_hours=168)

        self.assertEqual(result["rows"], 172)
        self.assertEqual(result["unique_hours"], 170)
        self.assertEqual(result["duplicate_rows"], 2)
        self.assertEqual(result["stations_with_continuous_window"], 1)
        self.assertEqual(result["usable_continuous_windows"], 3)

    def test_gap_breaks_continuous_window(self):
        ts = list(pd.date_range("2026-01-01", periods=100, freq="h"))
        ts += list(pd.date_range("2026-01-06", periods=100, freq="h"))
        frame = pd.DataFrame({"timestamp": ts, "station_id": ["A"] * len(ts)})

        result = summarize_hourly_coverage(frame, continuous_window_hours=168)

        self.assertEqual(result["stations_with_continuous_window"], 0)
        self.assertEqual(result["usable_continuous_windows"], 0)

    def test_training_window_coverage_reports_complete_feature_rows(self):
        table = pd.DataFrame({
            "rain_1h": [1.0, 1.0, None],
            "rain_168h": [1.0, None, 1.0],
            "river_level_lag_24h": [2.0, 2.0, 2.0],
        })
        result = summarize_training_window_coverage(table)

        self.assertEqual(result["rows"], 3)
        self.assertEqual(result["complete_feature_rows"], 1)
        self.assertAlmostEqual(result["feature_window_coverage_ratio"], 1 / 3)


if __name__ == "__main__":
    unittest.main()


    def test_source_readiness_uses_formal_contract(self):
        from backend.bihar_v1.readiness import build_source_readiness

        result = build_source_readiness(district="patna", source_paths={})
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(len(result["sources"]), 7)
        self.assertTrue(any("hourly_rainfall: missing" == blocker for blocker in result["blockers"]))

    def test_source_readiness_accepts_structural_csv_sources(self):
        import tempfile
        from pathlib import Path
        from backend.bihar_v1.readiness import build_source_readiness

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pd.DataFrame(columns=["Data Acquisition Time", "District", "Station", "Telemetry Hourly Rainfall (mm)"]).to_csv(root / "rain.csv", index=False)
            pd.DataFrame(columns=["Data Acquisition Time", "District", "Station", "River Water Level Telemetry Hourly (meter)"]).to_csv(root / "river.csv", index=False)
            pd.DataFrame(columns=["Station", "Danger Level"]).to_csv(root / "threshold.csv", index=False)
            pd.DataFrame(columns=["Start Date", "End Date", "Bihar District"]).to_csv(root / "events.csv", index=False)
            sentinel = root / "sentinel.json"
            dem = root / "dem.json"
            sentinel.write_text(
                '{"scenes":[{"scene_timestamp":"2025-08-01T00:00:00Z","district":"Patna","mask_path":"mask.tif"}]}',
                encoding="utf-8",
            )
            dem.write_text('{"elevation_path":"patna_dem.tif"}', encoding="utf-8")
            paths = {
                "hourly_rainfall": root / "rain.csv", "river_level": root / "river.csv",
                "river_threshold": root / "threshold.csv", "flood_events": root / "events.csv",
                "sentinel1_inundation": sentinel, "dem": dem,
                "district_boundaries": root / "districts.geojson",
            }
            result = build_source_readiness(district="patna", source_paths=paths)

        self.assertEqual(result["status"], "ready")

    def test_model_readiness_requires_real_target_and_threshold_evidence(self):
        from backend.bihar_v1.readiness import build_model_readiness

        timestamps = pd.date_range("2026-01-01", periods=168, freq="h", tz="UTC")
        rainfall = pd.DataFrame({
            "timestamp": timestamps,
            "station_id": ["rain-1"] * len(timestamps),
        })
        river = pd.DataFrame({
            "timestamp": timestamps,
            "station_id": ["river-1"] * len(timestamps),
        })
        result = build_model_readiness(
            district="patna",
            rainfall_hourly=rainfall,
            river=river,
            event_inventory={"unique_events": 5},
            synchronized_hourly={"stations_with_continuous_window": 1},
            evaluation_ready=True,
            evaluation_reason=None,
        )
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["models"]["heavy_rainfall"]["status"], "blocked")
        self.assertTrue(any("target/label" in reason for reason in result["models"]["heavy_rainfall"]["reasons"]))
        self.assertTrue(any("danger-level" in reason for reason in result["models"]["river_flood"]["reasons"]))
        self.assertEqual(result["models"]["inundation"]["status"], "blocked")

    def test_model_readiness_reports_missing_sources(self):
        from backend.bihar_v1.readiness import build_model_readiness

        result = build_model_readiness(
            district="muzaffarpur",
            rainfall_hourly=pd.DataFrame(),
            river=pd.DataFrame(),
            event_inventory={"unique_events": 0},
            synchronized_hourly={"stations_with_continuous_window": 0},
            evaluation_ready=False,
            evaluation_reason="evaluation thresholds not met",
        )
        self.assertEqual(result["status"], "blocked")
        self.assertTrue(result["models"]["heavy_rainfall"]["reasons"])
        self.assertTrue(result["models"]["river_flood"]["reasons"])
