"""CWC observation ingestion boundary with explicit provider schema validation.

The CWC service does not publish one stable schema across all downloadable feeds.
Callers must declare the verified field mapping for the feed they acquired; the
adapter rejects ambiguous/unknown mappings rather than guessing station identity,
units, timestamps, or stage/discharge semantics.
"""
from __future__ import annotations

from datetime import datetime
import math
from typing import Any


class CWCIngestionError(ValueError):
    """Raised when a CWC payload cannot safely be normalized."""


def _aware_timestamp(value: Any) -> str:
    if not isinstance(value, str):
        raise CWCIngestionError("CWC timestamp must be an ISO-8601 string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CWCIngestionError("CWC timestamp is invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CWCIngestionError("CWC timestamp must include a timezone")
    return parsed.isoformat()


def normalize_river_observation(
    payload: Any,
    *,
    field_map: dict[str, str] | None = None,
    source: str = "cwc",
    variable: str = "river_level_m",
    unit: str = "m",
) -> list[dict[str, Any]]:
    """Normalize a verified CWC list using an explicit raw-to-canonical field map.

    Required canonical keys: station_id, district, timestamp, value.
    Supported variables are stage (river_level_m, m) and discharge (discharge_m3s, m3/s).
    """
    if payload is None:
        return []
    if not isinstance(payload, list):
        raise CWCIngestionError("Expected a CWC observation payload as a list")
    if field_map is None:
        raise CWCIngestionError("A verified CWC field_map is required")
    required = {"station_id", "district", "timestamp", "value"}
    if set(field_map) != required:
        raise CWCIngestionError(f"field_map must define exactly {sorted(required)}")
    expected_unit = {"river_level_m": "m", "discharge_m3s": "m3/s"}
    if variable not in expected_unit or unit != expected_unit[variable]:
        raise CWCIngestionError("CWC variable and unit are unsupported or inconsistent")
    output = []
    for index, row in enumerate(payload):
        if not isinstance(row, dict):
            raise CWCIngestionError(f"CWC record {index} must be an object")
        canonical = {}
        for target, raw_name in field_map.items():
            if raw_name not in row:
                raise CWCIngestionError(f"CWC record {index} is missing mapped field {raw_name}")
            canonical[target] = row[raw_name]
        station = str(canonical["station_id"] or "").strip()
        district = str(canonical["district"] or "").strip().lower().replace(" ", "_")
        if not station or not district:
            raise CWCIngestionError(f"CWC record {index} has blank station/district identity")
        timestamp = _aware_timestamp(canonical["timestamp"])
        try:
            value = float(canonical["value"])
        except (TypeError, ValueError) as exc:
            raise CWCIngestionError(f"CWC record {index} has a non-numeric value") from exc
        if not math.isfinite(value):
            raise CWCIngestionError(f"CWC record {index} has a non-finite value")
        if variable == "river_level_m" and value < -20:
            raise CWCIngestionError(f"CWC record {index} has an implausible stage value")
        if variable == "discharge_m3s" and value < 0:
            raise CWCIngestionError(f"CWC record {index} has negative discharge")
        output.append({
            "station_id": station,
            "district": district,
            "timestamp": timestamp,
            "value": value,
            "variable": variable,
            "unit": unit,
            "source": source,
        })
    return output
