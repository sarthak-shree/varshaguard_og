"""Layer 1.3C: persist processed FMISC river snapshots in PostgreSQL."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

import pandas as pd

from .ingest import fetch_live_river_observations
from .postgres import PostgreSQLRiverObservationRepository
from .processing import process_river_records
from .storage import RiverObservation


def _parse_timestamp(value) -> datetime | None:
    """Parse a source timestamp into a timezone-aware UTC datetime."""
    if value is None or str(value).strip() == "":
        return None

    parsed = pd.to_datetime(value, errors="coerce", utc=True)
    if pd.isna(parsed):
        return None
    return parsed.to_pydatetime().astimezone(timezone.utc)


def _to_observation(record: dict) -> RiverObservation:
    """Convert a processed source record to the canonical storage model."""
    fetched_at = _parse_timestamp(record.get("fetched_at")) or datetime.now(timezone.utc)
    return RiverObservation(
        river=record["river"],
        station=record["station"],
        district=record["district"],
        observed_at=_parse_timestamp(record.get("observed_at")),
        water_level_m=float(record["water_level_m"]),
        warning_level_m=record.get("warning_level_m"),
        danger_level_m=record.get("danger_level_m"),
        hfl_m=record.get("hfl_m"),
        trend=record.get("trend_normalized") or record.get("trend"),
        water_level_1h_before_m=record.get("water_level_1h_before_m"),
        fetched_at=fetched_at,
    )


def persist_live_snapshot(
    repository: PostgreSQLRiverObservationRepository,
) -> dict:
    """Fetch, process, and persist one official FMISC river-data snapshot."""
    fetched = fetch_live_river_observations()
    processed = process_river_records(fetched["records"])
    observations = [_to_observation(record) for record in processed]

    accepted = repository.save_observations(observations)

    return {
        "success": True,
        "source": fetched["source"],
        "source_url": fetched["source_url"],
        "fetched_at": fetched["fetched_at"],
        "fetched_count": fetched["count"],
        "processed_count": len(processed),
        "accepted_count": accepted,
        "duplicate_or_ignored_count": max(len(observations) - accepted, 0),
    }


def persist_live_snapshot_from_env() -> dict:
    """Run one persistence cycle using DATABASE_URL."""
    repository = PostgreSQLRiverObservationRepository.from_env()
    repository.ensure_schema()
    return persist_live_snapshot(repository)
