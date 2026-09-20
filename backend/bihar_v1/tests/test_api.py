import unittest

from backend.bihar_v1.app import create_app


class BiharV1ApiTests(unittest.TestCase):
    def setUp(self):
        self.client = create_app().test_client()

    def test_health(self):
        response = self.client.get("/api/bihar/v1/health")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json["success"])

    def test_districts(self):
        response = self.client.get("/api/bihar/v1/districts")
        self.assertEqual(response.status_code, 200)
        self.assertEqual({d["slug"] for d in response.json["districts"]}, {"patna", "muzaffarpur"})

    def test_status_exposes_readiness_without_claiming_live_operation(self):
        response = self.client.get("/api/bihar/v1/patna/status")
        self.assertEqual(response.status_code, 200)
        payload = response.json
        self.assertEqual(payload["models"]["rainfall"]["status"], "model_not_trained")
        self.assertEqual(payload["models"]["inundation"]["status"], "model_not_trained")
        self.assertFalse(payload["models"]["flood"]["artifact_available"])
        self.assertIsNone(payload["models"]["flood"]["operational_threshold"])
        self.assertEqual(payload["models"]["flood"]["operational_threshold_status"], "not_calibrated")
        self.assertEqual(payload["data_feeds"]["status"], "not_ready")
        self.assertEqual(payload["operational_risk"], "not_ready")

    def test_forecast_refuses_uncalibrated_risk(self):
        response = self.client.get("/api/bihar/v1/patna/forecast")
        self.assertEqual(response.status_code, 200)
        payload = response.json
        self.assertEqual(payload["risk"]["risk_level"], "not_ready")
        self.assertFalse(payload["alert"]["active"])

    def test_unknown_district(self):
        response = self.client.get("/api/bihar/v1/unknown/status")
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
