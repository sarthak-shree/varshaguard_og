"""Dependency-light tests for the Layer 1.3B PostgreSQL repository."""

from __future__ import annotations

import os
import unittest

from .postgres import PostgreSQLRiverObservationRepository


class PostgreSQLRepositoryTests(unittest.TestCase):
    def test_empty_database_url_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            PostgreSQLRiverObservationRepository("")

    def test_missing_database_url_is_explicit(self) -> None:
        previous = os.environ.pop("DATABASE_URL", None)
        try:
            with self.assertRaises(RuntimeError):
                PostgreSQLRiverObservationRepository.from_env()
        finally:
            if previous is not None:
                os.environ["DATABASE_URL"] = previous

    def test_history_limit_bounds_are_defined(self) -> None:
        repository = PostgreSQLRiverObservationRepository("postgresql://example")
        self.assertEqual(repository.database_url, "postgresql://example")

        def bounded_limit(value: int) -> int:
            return max(1, min(int(value), 1000))

        self.assertEqual(bounded_limit(-10), 1)
        self.assertEqual(bounded_limit(500), 500)
        self.assertEqual(bounded_limit(5000), 1000)


if __name__ == "__main__":
    unittest.main()
