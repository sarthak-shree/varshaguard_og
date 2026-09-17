import os
import sys
import unittest

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


if __name__ == "__main__":
    unittest.main()
