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

    def test_forecast_is_explicitly_not_trained(self):
        response = self.client.get("/api/bihar/v1/patna/forecast")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["rainfall"]["status"], "model_not_trained")

    def test_unknown_district(self):
        response = self.client.get("/api/bihar/v1/unknown/forecast")
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
