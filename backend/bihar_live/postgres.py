"""Layer 1.3B: PostgreSQL implementation for Bihar river observations."""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Sequence

import psycopg
from psycopg.rows import tuple_row

from .storage import RiverObservation, RiverObservationRepository

SCHEMA_PATH = Path(__file__).with_name("schema.sql")


class PostgreSQLRiverObservationRepository(RiverObservationRepository):
    """Persist canonical river observations in PostgreSQL."""

    def __init__(self, database_url: str):
        database_url = database_url.strip()
        if not database_url:
            raise ValueError("DATABASE_URL cannot be empty.")
        self.database_url = database_url

    @classmethod
    def from_env(cls) -> "PostgreSQLRiverObservationRepository":
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            raise RuntimeError(
                "DATABASE_URL is not configured. "
                "Set it before using the Bihar Live PostgreSQL repository."
            )
        return cls(database_url)

    def _connect(self):
        return psycopg.connect(self.database_url, row_factory=tuple_row)

    def ensure_schema(self) -> None:
        """Create the observation table and indexes when they do not exist."""
        schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(schema_sql)

    def save_observations(self, observations: Sequence[RiverObservation]) -> int:
        """Insert observations, ignoring source duplicates."""
        if not observations:
            return 0

        query = """
            INSERT INTO river_observations (
                river,
                station,
                district,
                observed_at,
                water_level_m,
                warning_level_m,
                danger_level_m,
                hfl_m,
                trend,
                water_level_1h_before_m,
                fetched_at
            )
            VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            ON CONFLICT (river, station, observed_at)
            DO NOTHING
        """

        rows = [
            (
                item.river,
                item.station,
                item.district,
                item.observed_at,
                item.water_level_m,
                item.warning_level_m,
                item.danger_level_m,
                item.hfl_m,
                item.trend,
                item.water_level_1h_before_m,
                item.fetched_at,
            )
            for item in observations
        ]

        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.executemany(query, rows)
                return cursor.rowcount

    def get_history(
        self,
        *,
        station: str | None = None,
        district: str | None = None,
        since: datetime | None = None,
        limit: int = 500,
    ) -> list[RiverObservation]:
        """Return recent history using parameterized filters."""
        limit = max(1, min(int(limit), 1000))

        clauses: list[str] = []
        params: list[object] = []

        if station:
            clauses.append("station = %s")
            params.append(station)
        if district:
            clauses.append("district = %s")
            params.append(district)
        if since is not None:
            clauses.append("observed_at >= %s")
            params.append(since)

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        query = f"""
            SELECT
                river,
                station,
                district,
                observed_at,
                water_level_m,
                warning_level_m,
                danger_level_m,
                hfl_m,
                trend,
                water_level_1h_before_m,
                fetched_at
            FROM river_observations
            {where}
            ORDER BY observed_at DESC NULLS LAST, id DESC
            LIMIT %s
        """
        params.append(limit)

        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, params)
                rows = cursor.fetchall()

        return [
            RiverObservation(
                river=row[0],
                station=row[1],
                district=row[2],
                observed_at=row[3],
                water_level_m=row[4],
                warning_level_m=row[5],
                danger_level_m=row[6],
                hfl_m=row[7],
                trend=row[8],
                water_level_1h_before_m=row[9],
                fetched_at=row[10],
            )
            for row in rows
        ]


def get_configured_repository() -> PostgreSQLRiverObservationRepository:
    """Build the repository from the environment."""
    return PostgreSQLRiverObservationRepository.from_env()
