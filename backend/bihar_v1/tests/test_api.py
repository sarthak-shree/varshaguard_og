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

    def test_forecast_refuses_uncalibrated_risk(self):
        response = self.client.get("/api/bihar/v1/patna/forecast")
        self.assertEqual(response.status_code, 200)
        payload = response.json
        self.assertEqual(payload["rainfall"]["status"], "model_not_trained")
        self.assertEqual(payload["flood"]["status"], "model_not_trained")
        self.assertEqual(payload["inundation"]["status"], "model_not_trained")
        self.assertEqual(payload["risk"]["risk_level"], "not_ready")
        self.assertEqual(payload["risk"]["details"]["reason"], "no_model_probabilities_available")
        self.assertFalse(payload["alert"]["active"])

    def test_forecast_accepts_feature_query_without_claiming_readiness(self):
        response = self.client.get(
            "/api/bihar/v1/patna/forecast?rainfall_24h=120&river_level_m=48.2"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["risk"]["risk_level"], "not_ready")

    def test_unknown_district(self):
        response = self.client.get("/api/bihar/v1/unknown/forecast")
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
