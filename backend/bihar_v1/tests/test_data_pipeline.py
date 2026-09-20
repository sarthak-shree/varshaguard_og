import tempfile
import unittest
from pathlib import Path
from backend.bihar_v1.data_pipeline import load_observations, save_observations
from backend.bihar_v1.schemas import Observation
class DataPipelineTests(unittest.TestCase):
    def test_round_trip(self):
        obs=[Observation(timestamp="2026-09-20T10:00:00+00:00",district="patna",variable="rain_mm",value=12.5,unit="mm",source="test",station_id="s1",quality="good")]
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"obs.csv"; save_observations(obs,p); loaded=load_observations(p)
        self.assertEqual(len(loaded),1); self.assertEqual(loaded.loc[0,"district"],"patna"); self.assertAlmostEqual(loaded.loc[0,"value"],12.5)
if __name__=="__main__": unittest.main()
