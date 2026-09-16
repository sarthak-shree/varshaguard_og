"""Unit tests for Bihar Live freshness helpers."""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
import unittest

from .app import _freshness


class FreshnessTests(unittest.TestCase):
    def test_recent_timestamp_is_fresh(self):
        now = datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc)
        observed = (now - timedelta(minutes=10)).isoformat()
        result = _freshness(observed, now=now,)
        self.assertTrue(result["fresh"])
        self.assertEqual(result["status"], "fresh")

    def test_old_timestamp_is_stale(self):
        now = datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc)
        observed = (now - timedelta(minutes=90)).isoformat()
        result = _freshness(observed, now=now)
        self.assertFalse(result["fresh"])
        self.assertEqual(result["status"], "stale")

    def test_invalid_timestamp_is_unknown(self):
        result = _freshness("not-a-timestamp")
        self.assertFalse(result["fresh"])
        self.assertEqual(result["status"], "unknown")


if __name__ == "__main__":
    unittest.main()
