"""Tests for Layer 1.3C snapshot persistence helpers."""

from datetime import timezone
import unittest

from .persist import _parse_timestamp, _to_observation


class PersistenceTests(unittest.TestCase):
    def test_parse_source_timestamp_to_utc(self) -> None:
        parsed = _parse_timestamp("11-Aug-2026 15:00")
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.tzinfo, timezone.utc)

    def test_invalid_timestamp_becomes_none(self) -> None:
        self.assertIsNone(_parse_timestamp("not-a-date"))

    def test_record_maps_to_canonical_observation(self) -> None:
        observation = _to_observation(
            {
                "river": "Ganga",
                "station": "Patna",
                "district": "Patna",
                "water_level_m": 47.2,
                "warning_level_m": 48.0,
                "danger_level_m": 49.0,
                "hfl_m": 50.1,
                "trend_normalized": "rising",
                "water_level_1h_before_m": 47.0,
                "observed_at": "11-Aug-2026 15:00",
                "fetched_at": "2026-08-11T10:00:00+00:00",
            }
        )
        self.assertEqual(observation.river, "Ganga")
        self.assertEqual(observation.station, "Patna")
        self.assertEqual(observation.water_level_m, 47.2)
        self.assertEqual(observation.trend, "rising")
        self.assertEqual(observation.observed_at.tzinfo, timezone.utc)


if __name__ == "__main__":
    unittest.main()
