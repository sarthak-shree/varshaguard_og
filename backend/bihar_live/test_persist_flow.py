"""Layer 1.3C end-to-end flow test without requiring PostgreSQL."""

import unittest
from unittest.mock import patch

from .persist import persist_live_snapshot
from .storage import RiverObservation


class FakeRepository:
    def __init__(self, accepted_count=None):
        self.saved = []
        self.accepted_count = accepted_count

    def save_observations(self, observations):
        self.saved = list(observations)
        if self.accepted_count is None:
            return len(self.saved)
        return self.accepted_count

    def get_history(self, *, station=None, district=None, since=None, limit=500):
        return []


class PersistenceFlowTests(unittest.TestCase):
    def test_fmics_snapshot_flows_through_processing_into_repository(self):
        source_snapshot = {
            "success": True,
            "source": "Bihar FMISC/WRD",
            "source_url": "https://beams.fmiscwrdbihar.gov.in/Alerttotalinfo/realtimetotal.aspx",
            "fetched_at": "2026-08-11T10:00:00+00:00",
            "count": 2,
            "records": [
                {
                    "river": "Ganga",
                    "station": "Patna",
                    "district": "Patna",
                    "water_level_m": 47.2,
                    "water_level_1h_before_m": 47.0,
                    "warning_level_m": 48.0,
                    "danger_level_m": 49.0,
                    "hfl_m": 50.1,
                    "trend": "Rising",
                    "observed_at": "11-Aug-2026 15:00",
                    "fetched_at": "2026-08-11T10:00:00+00:00",
                },
                {
                    "river": "Ganga",
                    "station": "Digha",
                    "district": "Patna",
                    "water_level_m": 46.8,
                    "water_level_1h_before_m": 46.9,
                    "warning_level_m": 48.0,
                    "danger_level_m": 49.0,
                    "hfl_m": 50.1,
                    "trend": "Falling",
                    "observed_at": "11-Aug-2026 15:00",
                    "fetched_at": "2026-08-11T10:00:00+00:00",
                },
            ],
        }
        repository = FakeRepository()

        with patch(".persist.fetch_live_river_observations", return_value=source_snapshot):
            result = persist_live_snapshot(repository)

        self.assertTrue(result["success"])
        self.assertEqual(result["fetched_count"], 2)
        self.assertEqual(result["processed_count"], 2)
        self.assertEqual(result["accepted_count"], 2)
        self.assertEqual(result["duplicate_or_ignored_count"], 0)
        self.assertEqual(len(repository.saved), 2)
        self.assertTrue(all(isinstance(item, RiverObservation) for item in repository.saved))
        self.assertEqual(repository.saved[0].trend, "rising")
        self.assertEqual(repository.saved[0].water_level_m, 47.2)

    def test_duplicate_count_is_reported_from_repository_result(self):
        source_snapshot = {
            "success": True,
            "source": "Bihar FMISC/WRD",
            "source_url": "https://beams.fmiscwrdbihar.gov.in/Alerttotalinfo/realtimetotal.aspx",
            "fetched_at": "2026-08-11T10:00:00+00:00",
            "count": 2,
            "records": [
                {
                    "river": "Ganga",
                    "station": "Patna",
                    "district": "Patna",
                    "water_level_m": 47.2,
                    "observed_at": "11-Aug-2026 15:00",
                    "fetched_at": "2026-08-11T10:00:00+00:00",
                },
                {
                    "river": "Ganga",
                    "station": "Digha",
                    "district": "Patna",
                    "water_level_m": 46.8,
                    "observed_at": "11-Aug-2026 15:00",
                    "fetched_at": "2026-08-11T10:00:00+00:00",
                },
            ],
        }
        repository = FakeRepository(accepted_count=1)

        with patch(".persist.fetch_live_river_observations", return_value=source_snapshot):
            result = persist_live_snapshot(repository)

        self.assertEqual(result["processed_count"], 2)
        self.assertEqual(result["accepted_count"], 1)
        self.assertEqual(result["duplicate_or_ignored_count"], 1)


if __name__ == "__main__":
    unittest.main()
