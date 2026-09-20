import tempfile
import unittest
from pathlib import Path
from backend.bihar_v1.data_pipeline import load_observations, save_observations, validate_observations_frame
from backend.bihar_v1.schemas import Observation
class DataPipelineTests(unittest.TestCase):
    def test_validation_rejects_bad_timestamp_and_value(self):
        import pandas as pd
        frame = pd.DataFrame([{"timestamp":"bad","district":"patna","variable":"rain_mm","value":"x","unit":"mm","source":"test"}])
        result = validate_observations_frame(frame)
        self.assertFalse(result["valid"])
        self.assertEqual(result["invalid_timestamps"], 1)
        self.assertEqual(result["invalid_values"], 1)

    def test_missing_value_is_allowed(self):
        import pandas as pd
        frame = pd.DataFrame([{"timestamp":"2026-09-20T10:00:00+00:00","district":"patna","variable":"rain_mm","value":None,"unit":"mm","source":"test"}])
        result = validate_observations_frame(frame)
        self.assertTrue(result["valid"])
        self.assertEqual(result["invalid_values"], 0)

    def test_validation_rejects_duplicate_timestamps(self):
        import pandas as pd
        frame = pd.DataFrame([
            {"timestamp":"2026-09-20T10:00:00+00:00","district":"patna","variable":"rain_mm","value":1.0,"unit":"mm","source":"test"},
            {"timestamp":"2026-09-20T10:00:00+00:00","district":"patna","variable":"rain_mm","value":2.0,"unit":"mm","source":"test"},
        ])
        result = validate_observations_frame(frame)
        self.assertFalse(result["valid"])
        self.assertEqual(result["duplicate_timestamps"], 2)

    def test_round_trip(self):
        obs=[Observation(timestamp="2026-09-20T10:00:00+00:00",district="patna",variable="rain_mm",value=12.5,unit="mm",source="test",station_id="s1",quality="good")]
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"obs.csv"; save_observations(obs,p); loaded=load_observations(p)
        self.assertEqual(len(loaded),1); self.assertEqual(loaded.loc[0,"district"],"patna"); self.assertAlmostEqual(loaded.loc[0,"value"],12.5)
if __name__=="__main__": unittest.main()
