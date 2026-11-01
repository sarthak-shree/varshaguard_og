import unittest

import backend.app as backend_module
from backend.app import app


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.config.update(TESTING=True)
        cls.client = app.test_client()

    def test_health_contract(self):
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertIn(body["status"], {"ok", "degraded"})
        self.assertIn("legacy_model", body["dependencies"])
        self.assertIn("bihar_live", body["dependencies"])
        self.assertIn("bihar_v1", body["dependencies"])
        self.assertIn(body["prediction"], {"READY", "ERROR"})


    def test_assistant_rate_limit_returns_retry_after(self):
        backend_module._RATE_LIMIT_BUCKETS.clear()
        backend_module._assistant_request_limits = lambda: (1, 1, 60)
        backend_module.request_assistant_answer = lambda message, context: "test answer"
        first = self.client.post("/api/assistant", json={"message": "hello"})
        second = self.client.post("/api/assistant", json={"message": "hello"})
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 429)
        self.assertEqual(second.headers.get("Retry-After"), "60")
        backend_module._RATE_LIMIT_BUCKETS.clear()

    def test_regions(self):
        response = self.client.get("/api/regions")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["regions"], ["Assam", "Uttarakhand"])

    def test_invalid_region(self):
        response = self.client.get("/api/flood-risk?region=Bihar")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.get_json()["success"])


if __name__ == "__main__":
    unittest.main()
