"""Layer 1.3C: persist processed FMISC river snapshots in PostgreSQL."""

from __future__ import annotations

from datetime import datetime, timezone
import re
from zoneinfo import ZoneInfo

import pandas as pd

from .ingest import fetch_live_river_observations
from .processing import process_river_records
from .storage import RiverObservation, RiverObservationRepository

SOURCE_TIMEZONE = ZoneInfo("Asia/Kolkata")


def _parse_timestamp(value) -> datetime | None:
    """Parse an FMISC source timestamp into a timezone-aware UTC datetime."""
    if value is None or str(value).strip() == "":
        return None

    text = " ".join(str(value).split())
    text = re.sub(r"\s+HRS?\.?$", "", text, flags=re.IGNORECASE)

    for fmt in ("%d-%b-%Y %H:%M", "%d-%b-%Y %H"):
        try:
            local_dt = datetime.strptime(text, fmt).replace(tzinfo=SOURCE_TIMEZONE)
            return local_dt.astimezone(timezone.utc)
        except ValueError:
            pass

    parsed = pd.to_datetime(text, errors="coerce")
    if pd.isna(parsed):
        return None

    if parsed.tzinfo is None:
        parsed = parsed.tz_localize(SOURCE_TIMEZONE)
    else:
        parsed = parsed.tz_convert(SOURCE_TIMEZONE)
    return parsed.to_pydatetime().astimezone(timezone.utc)


def _to_observation(record: dict) -> RiverObservation:
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


def persist_records(records: list[dict], repository: RiverObservationRepository) -> int:
    """Process source records and persist them through the repository."""
    processed = process_river_records(records)
    observations = [_to_observation(record) for record in processed]
    return repository.save_observations(observations)


def persist_live_snapshot(repository: RiverObservationRepository) -> dict:
    """Fetch, process, and persist one official FMISC river-data snapshot."""
    fetched = fetch_live_river_observations()
    if not fetched.get("live") or fetched.get("source_mode") != "fmisc_live":
        raise RuntimeError("FMISC live source was unavailable; refusing to persist fallback as live data")

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
    """Run one persistence cycle using the configured PostgreSQL repository."""
    from .postgres import PostgreSQLRiverObservationRepository

    repository = PostgreSQLRiverObservationRepository.from_env()
    repository.ensure_schema()
    return persist_live_snapshot(repository)
