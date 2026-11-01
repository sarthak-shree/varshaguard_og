import unittest
from unittest.mock import Mock, patch

import pytest

from backend.bihar_v1.ingestion.cwc import CWCIngestionError, normalize_river_observation


def test_cwc_normalizer_requires_explicit_verified_mapping():
    with pytest.raises(CWCIngestionError, match="field_map"):
        normalize_river_observation([{"station": "A"}])


def test_cwc_normalizer_keeps_stage_and_discharge_units_separate():
    mapping = {"station_id": "station", "district": "district", "timestamp": "at", "value": "stage"}
    result = normalize_river_observation(
        [{"station": "Gandhighat", "district": "Patna", "at": "2026-10-01T00:00:00+05:30", "stage": "42.1"}],
        field_map=mapping,
    )
    assert result[0]["value"] == 42.1
    assert result[0]["unit"] == "m"
    with pytest.raises(CWCIngestionError, match="unit"):
        normalize_river_observation(
            [{"station": "A", "district": "Patna", "at": "2026-10-01T00:00:00Z", "stage": 1}],
            field_map=mapping, variable="discharge_m3s", unit="m",
        )


from backend.bihar_v1.ingestion import imd


class IMDIngestionTests(unittest.TestCase):
    @patch.dict("os.environ", {"IMD_API_TOKEN": "test-token"}, clear=False)
    def test_sends_bearer_auth_and_validates_payload(self):
        response = Mock()
        response.status_code = 200
        response.json.return_value = [{"district": "Patna"}]
        response.headers = {}
        response.raise_for_status.return_value = None
        session = Mock()
        session.get.return_value = response
        payload = imd.fetch_json("districtwarning", session=session, retries=0)
        self.assertEqual(payload, [{"district": "Patna"}])
        self.assertEqual(
            session.get.call_args.kwargs["headers"]["Authorization"],
            "Bearer test-token",
        )

    def test_rejects_non_json_root(self):
        response = Mock()
        response.status_code = 200
        response.json.return_value = "not-an-observation"
        response.headers = {}
        response.raise_for_status.return_value = None
        session = Mock()
        session.get.return_value = response
        with self.assertRaises(imd.IMDIngestionError):
            imd.fetch_json("current_wx", session=session, retries=0)

    def test_retries_transient_status(self):
        retry = Mock()
        retry.status_code = 503
        retry.headers = {}
        success = Mock()
        success.status_code = 200
        success.headers = {}
        success.json.return_value = {"data": []}
        success.raise_for_status.return_value = None
        session = Mock()
        session.get.side_effect = [retry, success]
        with patch("backend.bihar_v1.ingestion.imd.time.sleep"):
            payload = imd.fetch_json("districtwarning", session=session, retries=1)
        self.assertEqual(payload, {"data": []})
        self.assertEqual(session.get.call_count, 2)


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
        self.assertEqual(observations, [])


if __name__ == "__main__":
    unittest.main()
