import unittest

from backend.bihar_v1.spatial_mapping import assign_districts


class SpatialMappingTests(unittest.TestCase):
    def test_assigns_point_inside_authoritative_polygon(self):
        records = [{"latitude": 25.5, "longitude": 85.1, "rainfall_mm": 2.0}]
        features = [{
            "type": "Feature",
            "properties": {"district": "Patna"},
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[85.0, 25.0], [85.2, 25.0], [85.2, 26.0], [85.0, 26.0], [85.0, 25.0]]],
            },
        }]
        result = assign_districts(records, features)
        self.assertEqual(result[0]["district"], "patna")

    def test_unmatched_point_is_not_guessed(self):
        records = [{"latitude": 27.0, "longitude": 85.1, "rainfall_mm": 2.0}]
        features = [{
            "type": "Feature",
            "properties": {"district": "Patna"},
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[85.0, 25.0], [85.2, 25.0], [85.2, 26.0], [85.0, 26.0], [85.0, 25.0]]],
            },
        }]
        result = assign_districts(records, features)
        self.assertIsNone(result[0]["district"])


if __name__ == "__main__":
    unittest.main()
