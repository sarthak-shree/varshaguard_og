import unittest
import pandas as pd
from backend.bihar_v1.feature_engineering import build_tabular_features
class FeatureEngineeringTests(unittest.TestCase):
    def test_rainfall_windows(self):
        frame=pd.DataFrame({"timestamp":pd.date_range("2026-01-01",periods=24,freq="h",tz="UTC"),"rain_mm":[1.0]*24})
        out=build_tabular_features(frame)
        self.assertTrue(pd.isna(out.loc[0,"rain_3h"]))
        self.assertEqual(out.loc[2,"rain_3h"],3.0)
        self.assertEqual(out.loc[23,"rain_24h"],24.0)
    def test_rainfall_window_does_not_bridge_long_gap(self):
        ts = pd.to_datetime(["2026-01-01 00:00", "2026-01-01 01:00", "2026-01-01 10:00"], utc=True)
        frame = pd.DataFrame({"timestamp": ts, "rain_mm": [1.0, 1.0, 5.0]})
        out = build_tabular_features(frame)
        self.assertTrue(pd.isna(out.loc[2, "rain_3h"]))

    def test_rainfall_window_requires_each_hour(self):
        ts = pd.to_datetime(["2026-01-01 00:00", "2026-01-01 01:00", "2026-01-01 03:00"], utc=True)
        frame = pd.DataFrame({"timestamp": ts, "rain_mm": [1.0, 1.0, 3.0]})
        out = build_tabular_features(frame)
        self.assertTrue(pd.isna(out.loc[2, "rain_3h"]))

    def test_river_lag_does_not_use_stale_measurement(self):
        ts = pd.to_datetime(["2026-01-01 00:00", "2026-01-01 02:00"], utc=True)
        frame = pd.DataFrame({"timestamp": ts, "river_level_m": [10.0, 11.0]})
        out = build_tabular_features(frame)
        self.assertTrue(pd.isna(out.loc[1, "river_level_lag_1h"]))

    def test_river_rise(self):
        frame=pd.DataFrame({"timestamp":pd.date_range("2026-01-01",periods=6,freq="h",tz="UTC"),"river_level_m":[10,10.1,10.2,10.3,10.4,10.5]})
        out=build_tabular_features(frame)
        self.assertAlmostEqual(out.loc[5,"river_rise_3h"],0.3)
        self.assertAlmostEqual(out.loc[5,"river_level_lag_1h"],10.4)
    def test_missing_is_not_fabricated(self):
        frame=pd.DataFrame({"timestamp":pd.date_range("2026-01-01",periods=4,freq="h",tz="UTC"),"rain_mm":[1.0,None,2.0,1.0]})
        out=build_tabular_features(frame)
        self.assertTrue(pd.isna(out.loc[2,"rain_3h"]))
if __name__=="__main__": unittest.main()
