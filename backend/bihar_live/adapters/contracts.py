"""Strict provider-neutral validation contracts for Phase 2 adapters."""
from __future__ import annotations
from datetime import datetime
from typing import Any

REQUIRED_FIELDS = {"timestamp_utc", "timestamp_ist", "district", "source", "variable", "value", "unit"}

def _parse_timestamp(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError("timestamp must be an ISO-8601 string")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include timezone information")
    return parsed

def validate_observation_records(records: Any) -> None:
    if not isinstance(records, list):
        raise ValueError("adapter payload must be a list")
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            raise ValueError(f"record {index} must be an object")
        missing = REQUIRED_FIELDS - set(record)
        if missing:
            raise ValueError(f"record {index} missing fields: {sorted(missing)}")
        utc = _parse_timestamp(record["timestamp_utc"])
        ist = _parse_timestamp(record["timestamp_ist"])
        if not record["district"] or not record["source"] or not record["variable"]:
            raise ValueError(f"record {index} contains blank identity fields")
        if record["value"] is not None and not isinstance(record["value"], (int, float)):
            raise ValueError(f"record {index} value must be numeric or null")
        if utc.utcoffset() is None or ist.utcoffset() is None:
            raise ValueError(f"record {index} timestamps must be timezone-aware")
