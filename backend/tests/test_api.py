import unittest
from unittest.mock import Mock, patch

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
        with patch.object(backend_module, "_assistant_request_limits", return_value=(1, 1, 60)), patch.object(backend_module, "request_assistant_answer", return_value="test answer"):
            first = self.client.post("/api/assistant", json={"message": "hello"})
            second = self.client.post("/api/assistant", json={"message": "hello"})
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 429)
        self.assertEqual(second.headers.get("Retry-After"), "60")
        backend_module._RATE_LIMIT_BUCKETS.clear()


    def test_shared_rate_limit_uses_upstash_when_configured(self):
        backend_module._RATE_LIMIT_BUCKETS.clear()
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"result": 1}
        with patch.dict("os.environ", {
            "UPSTASH_REDIS_REST_URL": "https://redis.example.test",
            "UPSTASH_REDIS_REST_TOKEN": "test-token",
        }), patch("backend.app.requests.post", return_value=response) as post:
            result = backend_module._upstash_rate_limit_exceeded("assistant", 3, 60)
        self.assertFalse(result)
        self.assertIn("EVAL", post.call_args.kwargs["json"])
        self.assertEqual(post.call_args.kwargs["headers"]["Authorization"], "Bearer test-token")

    def test_shared_rate_limit_fails_closed_on_provider_error(self):
        backend_module._RATE_LIMIT_BUCKETS.clear()
        with patch.dict("os.environ", {
            "UPSTASH_REDIS_REST_URL": "https://redis.example.test",
            "UPSTASH_REDIS_REST_TOKEN": "test-token",
        }), patch("backend.app.requests.post", side_effect=RuntimeError("offline")):
            response = self.client.post("/api/assistant", json={"message": "hello"})
        self.assertEqual(response.status_code, 503)
        self.assertIn("protection", response.get_json()["error"])
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
