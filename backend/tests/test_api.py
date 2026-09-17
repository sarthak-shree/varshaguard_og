import os
import sys
import unittest
from unittest.mock import patch

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT_DIR = os.path.dirname(BACKEND_DIR)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from app import app  # noqa: E402


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.config.update(TESTING=True)
        cls.client = app.test_client()

    def test_health(self):
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertIn(body["status"], {"ok", "error"})
        self.assertEqual(body["bihar_live"], "AVAILABLE")
        self.assertEqual(response.headers["Cache-Control"], "no-store, no-cache, must-revalidate, max-age=0")

    def test_regions(self):
        response = self.client.get("/api/regions")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["regions"], ["Assam", "Uttarakhand"])

    def test_invalid_region(self):
        response = self.client.get("/api/flood-risk?region=Bihar")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.get_json()["success"])

    def test_bihar_live_validation(self):
        response = self.client.post("/api/bihar-live/forecast", json={
            "water_level_m": 52.4,
            "warning_level_m": 52.0,
            "danger_level_m": 53.0,
            "water_level_1h_before_m": 52.2,
        })
        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertTrue(body["success"])
        self.assertEqual(body["region"], "Bihar")
        self.assertIn("flood_forecast", body)
        self.assertIn("inundation_forecast", body)

    def test_bihar_live_missing_payload(self):
        response = self.client.post("/api/bihar-live/forecast")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.get_json()["success"])

    @patch("app.fetch_live_data")
    def test_bihar_station_feed_is_live_and_uncached(self, mocked_fetch):
        mocked_fetch.return_value = {
            "success": True,
            "source": "CWC/India-WRIS",
            "fetched_at": "2026-09-17T15:00:00+00:00",
            "stations": [{"station": "Test", "water_level_m": 1.2}],
        }
        response = self.client.get("/api/bihar-live/stations")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["source"], "CWC/India-WRIS")
        self.assertEqual(response.headers["Cache-Control"], "no-store, no-cache, must-revalidate, max-age=0")
        mocked_fetch.assert_called_once()

    @patch("app.fetch_live_data", side_effect=RuntimeError("upstream unavailable"))
    def test_bihar_station_feed_does_not_fallback_to_stale_data(self, mocked_fetch):
        response = self.client.get("/api/bihar-live/stations")
        self.assertEqual(response.status_code, 502)
        body = response.get_json()
        self.assertFalse(body["success"])
        self.assertIn("Live Bihar station feed unavailable", body["error"])
        mocked_fetch.assert_called_once()


if __name__ == "__main__":
    unittest.main()
