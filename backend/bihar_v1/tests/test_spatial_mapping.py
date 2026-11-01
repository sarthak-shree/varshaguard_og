import json
import tempfile
import unittest
from pathlib import Path

from backend.bihar_v1.spatial_mapping import assign_districts, load_district_features


def square_feature(name="Patna"):
    return {
        "type": "Feature",
        "properties": {"district": name},
        "geometry": {
            "type": "Polygon",
            "coordinates": [[
                [85.0, 25.0], [85.2, 25.0], [85.2, 26.0],
                [85.0, 26.0], [85.0, 25.0],
            ]],
        },
    }


class SpatialMappingTests(unittest.TestCase):
    def test_assigns_point_inside_authoritative_polygon(self):
        result = assign_districts([{"latitude": 25.5, "longitude": 85.1}], [square_feature()])
        self.assertEqual(result[0]["district"], "patna")

    def test_outer_boundary_edges_and_vertices_are_included(self):
        records = [
            {"latitude": 25.5, "longitude": 85.0},
            {"latitude": 25.5, "longitude": 85.2},
            {"latitude": 25.0, "longitude": 85.0},
            {"latitude": 26.0, "longitude": 85.2},
        ]
        result = assign_districts(records, [square_feature()])
        self.assertEqual([row["district"] for row in result], ["patna"] * 4)

    def test_point_inside_polygon_hole_is_unmatched(self):
        feature = square_feature()
        feature["geometry"]["coordinates"].append([
            [85.05, 25.4], [85.15, 25.4], [85.15, 25.6],
            [85.05, 25.6], [85.05, 25.4],
        ])
        result = assign_districts([{"latitude": 25.5, "longitude": 85.1}], [feature])
        self.assertIsNone(result[0]["district"])

    def test_hole_boundary_is_excluded(self):
        feature = square_feature()
        feature["geometry"]["coordinates"].append([
            [85.05, 25.4], [85.15, 25.4], [85.15, 25.6],
            [85.05, 25.6], [85.05, 25.4],
        ])
        result = assign_districts([{"latitude": 25.4, "longitude": 85.1}], [feature])
        self.assertIsNone(result[0]["district"])

    def test_multipolygon_matches_non_first_polygon(self):
        feature = {
            "type": "Feature", "properties": {"district": "Patna"},
            "geometry": {"type": "MultiPolygon", "coordinates": [
                [[[85, 25], [85.2, 25], [85.2, 25.2], [85, 25.2], [85, 25]]],
                [[[86, 26], [87, 26], [87, 27], [86, 27], [86, 26]]],
            ]},
        }
        result = assign_districts([{"latitude": 26.5, "longitude": 86.5}], [feature])
        self.assertEqual(result[0]["district"], "patna")

    def test_unmatched_point_is_not_guessed(self):
        result = assign_districts([{"latitude": 27, "longitude": 85.1}], [square_feature()])
        self.assertIsNone(result[0]["district"])

    def test_shared_boundary_is_rejected_as_ambiguous(self):
        left = square_feature("Patna")
        right = square_feature("Muzaffarpur")
        right["geometry"]["coordinates"] = [[
            [85.2, 25], [85.4, 25], [85.4, 26], [85.2, 26], [85.2, 25]
        ]]
        with self.assertRaisesRegex(ValueError, "multiple district"):
            assign_districts([{"latitude": 25.5, "longitude": 85.2}], [left, right])

    def test_rejects_invalid_record_coordinates(self):
        with self.assertRaisesRegex(ValueError, "outside"):
            assign_districts([{"latitude": 95, "longitude": 85}], [square_feature()])

    def test_loads_valid_feature_collection(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "districts.geojson"
            path.write_text(json.dumps({"type": "FeatureCollection", "features": [square_feature()]}))
            self.assertEqual(len(load_district_features(path)), 1)

    def test_rejects_missing_district_property(self):
        feature = square_feature()
        feature["properties"] = {}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "districts.geojson"
            path.write_text(json.dumps({"type": "FeatureCollection", "features": [feature]}))
            with self.assertRaises(ValueError):
                load_district_features(path)


if __name__ == "__main__":
    unittest.main()
