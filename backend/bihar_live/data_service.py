"""Live Bihar river-station data service.

The dashboard reads this service through Flask instead of shipping a dated
snapshot to the browser. The service keeps source timestamps in the backend
response for audit/debugging, while the public station UI can omit them.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import requests


CWC_URL = "https://indiawris.gov.in/wris/cwc"
REQUEST_TIMEOUT_SECONDS = 15


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _pick(item: dict, *keys: str) -> Any:
    for key in keys:
        if key in item and item[key] not in (None, ""):
            return item[key]
    return None


def _normalize_source_row(item: dict) -> dict | None:
    station = _pick(item, "station", "Station", "stationName", "StationName", "name", "Name")
    river = _pick(item, "river", "River", "riverName", "RiverName")
    district = _pick(item, "district", "District", "districtName", "DistrictName")
    level = _number(_pick(item, "water_level_m", "waterLevel", "water_level", "level", "Gauge", "gauge"))
    warning = _number(_pick(item, "warning_level_m", "warningLevel", "warning_level", "Warning", "warning"))
    danger = _number(_pick(item, "danger_level_m", "dangerLevel", "danger_level", "Danger", "danger"))
    previous = _number(_pick(item, "water_level_1h_before_m", "previousLevel", "level1hBefore", "oneHourBefore"))
    latitude = _number(_pick(item, "latitude", "Latitude", "lat"))
    longitude = _number(_pick(item, "longitude", "Longitude", "lon", "lng"))
    observed = _pick(item, "observed", "Observed", "observationTime", "timestamp", "Timestamp", "time", "dateTime")

    if station is None or level is None:
        return None

    return {
        "station": str(station).strip(),
        "river": str(river).strip() if river is not None else "",
        "district": str(district).strip() if district is not None else "",
        "water_level_m": level,
        "warning_level_m": warning,
        "danger_level_m": danger,
        "water_level_1h_before_m": previous,
        "latitude": latitude,
        "longitude": longitude,
        "observed": str(observed) if observed is not None else None,
    }


def _extract_rows(payload: Any) -> list[dict]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []

    for key in ("data", "stations", "records", "results", "items", "waterLevels"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def fetch_live_data() -> dict:
    """Fetch the freshest station feed available from the configured CWC endpoint."""
    params = {"format": "json"}
    headers = {
        "Accept": "application/json",
        "User-Agent": "VARSHAGUARD/1.0 (+https://github.com/sarthak-shree/varshaguard_og)",
        "Cache-Control": "no-cache",
    }

    response = requests.get(
        CWC_URL,
        params=params,
        headers=headers,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    payload = response.json()
    source_rows = _extract_rows(payload)

    stations: list[dict] = []
    for item in source_rows:
        normalized = _normalize_source_row(item)
        if normalized:
            stations.append(normalized)

    if not stations:
        raise ValueError("Live CWC response contained no usable Bihar station rows.")

    return {
        "success": True,
        "source": "CWC/India-WRIS",
        "fetched_at": _utc_now(),
        "stations": stations,
    }
