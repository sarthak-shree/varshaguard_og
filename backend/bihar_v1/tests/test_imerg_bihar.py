import unittest

from backend.bihar_v1.ingestion.imerg_bihar import bihar_precipitation_to_observations


class BiharIMERGIngestionTests(unittest.TestCase):
    def test_assigns_district_before_observation_conversion(self):
        records = [{
            "timestamp": "2026-09-01T00:00:00Z",
            "latitude": 25.5,
            "longitude": 85.1,
            "rainfall_mm": 4.2,
        }]
        features = [{
            "type": "Feature",
            "properties": {"district": "Patna"},
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[85.0, 25.0], [85.2, 25.0], [85.2, 26.0],
                                 [85.0, 26.0], [85.0, 25.0]]],
            },
        }]
        observations = bihar_precipitation_to_observations(records, features)
        self.assertEqual(observations[0].district, "patna")
        self.assertEqual(observations[0].value, 4.2)

    def test_does_not_guess_unmatched_district(self):
        records = [{
            "timestamp": "2026-09-01T00:00:00Z",
            "latitude": 27.0,
            "longitude": 85.1,
            "rainfall_mm": 4.2,
        }]
        features = [{
            "type": "Feature",
            "properties": {"district": "Patna"},
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[85.0, 25.0], [85.2, 25.0], [85.2, 26.0],
                                 [85.0, 26.0], [85.0, 25.0]]],
            },
        }]
        observations = bihar_precipitation_to_observations(records, features)
        self.assertEqual(observations[0].district, "")


if __name__ == "__main__":
    unittest.main()
