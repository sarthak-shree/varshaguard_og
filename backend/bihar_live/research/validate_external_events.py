"""Validate provenance and temporal fields in the external flood-event ledger."""
from __future__ import annotations

import argparse
import csv
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_LEDGER = ROOT / "data" / "bihar_live" / "research" / "independent_flood_events.csv"
REQUIRED_COLUMNS = {
    "event_id",
    "source_org",
    "source_document_id",
    "source_url",
    "source_observation_time_ist",
    "event_start_time_ist",
    "event_end_time_ist",
    "geography_type",
    "geography_name",
    "evidence_type",
    "event_claim",
    "independent_of_model_gauge_inputs",
    "ground_verified",
    "station_level_match_ready",
    "matching_status",
    "notes",
}
BOOLEAN_COLUMNS = (
    "independent_of_model_gauge_inputs",
    "ground_verified",
    "station_level_match_ready",
)
MATCHING_STATUSES = {
    "not_spatiotemporally_matched",
    "matched",
    "rejected",
    "needs_review",
}


def _parse_iso_datetime(value: str, field: str, event_id: str) -> datetime | None:
    if not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"{event_id}: {field} must be ISO-8601: {value!r}") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{event_id}: {field} must include a timezone offset")
    return parsed


def validate_ledger(path: Path = DEFAULT_LEDGER) -> list[dict[str, str]]:
    """Return rows after validating schema, provenance, booleans, and time ordering."""
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        columns = set(reader.fieldnames or [])
        missing = sorted(REQUIRED_COLUMNS - columns)
        if missing:
            raise ValueError("Missing event ledger columns: " + ", ".join(missing))
        rows = list(reader)

    if not rows:
        raise ValueError("External event ledger has no records")

    seen_ids: set[str] = set()
    for row in rows:
        event_id = row["event_id"].strip()
        if not event_id:
            raise ValueError("Every row must have an event_id")
        if event_id in seen_ids:
            raise ValueError(f"Duplicate event_id: {event_id}")
        seen_ids.add(event_id)

        for field in ("source_org", "source_document_id", "source_url", "geography_name",
                      "evidence_type", "event_claim", "notes"):
            if not row[field].strip():
                raise ValueError(f"{event_id}: {field} must not be empty")

        parsed_url = urlparse(row["source_url"])
        if parsed_url.scheme != "https" or not parsed_url.netloc:
            raise ValueError(f"{event_id}: source_url must be an HTTPS URL")

        observed = _parse_iso_datetime(
            row["source_observation_time_ist"], "source_observation_time_ist", event_id
        )
        start = _parse_iso_datetime(row["event_start_time_ist"], "event_start_time_ist", event_id)
        end = _parse_iso_datetime(row["event_end_time_ist"], "event_end_time_ist", event_id)
        if observed is None:
            raise ValueError(f"{event_id}: source_observation_time_ist is required")
        if start is not None and end is not None and end < start:
            raise ValueError(f"{event_id}: event_end_time_ist precedes event_start_time_ist")

        for field in BOOLEAN_COLUMNS:
            if row[field].strip().lower() not in {"true", "false"}:
                raise ValueError(f"{event_id}: {field} must be true or false")

        if row["matching_status"] not in MATCHING_STATUSES:
            raise ValueError(f"{event_id}: unsupported matching_status {row['matching_status']!r}")
        if row["station_level_match_ready"].strip().lower() == "true" and row["matching_status"] != "matched":
            raise ValueError(f"{event_id}: station_level_match_ready requires matching_status=matched")
        if row["matching_status"] == "matched" and not (start or end):
            raise ValueError(f"{event_id}: matched rows need an event start or end timestamp")

    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    args = parser.parse_args()
    rows = validate_ledger(args.ledger.expanduser().resolve())
    print(f"Validated {len(rows)} external flood-event ledger records: {args.ledger}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
