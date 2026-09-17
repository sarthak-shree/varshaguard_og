"""Live Bihar river-station data service.

The dashboard reads this service through Flask instead of shipping a dated
snapshot to the browser. Source timestamps stay in the backend response for
audit/debugging but are intentionally omitted from the public station table.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import requests


# India-WRIS is the authoritative national water-resources portal used by CWC
# for hydrological observations. The exact portal payload can change, so the
# normalizer below accepts the common field names seen in station feeds.
CWC_URLS = (
    "https://indiawris.gov.in/wris/cwc",
    "https://indiawris.gov.in/wris/#/RiverMonitoring",
)
REQUEST_TIMEOUT_SECONDS = 15


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number else None


def _pick(item: dict, *keys: str) -> Any:
    for key in keys:
        value = item.get(key)
        if value not in (None, ""):
            return value
    return None


def _normalize_source_row(item: dict) -> dict | None:
    station = _pick(item, "station", "Station", "stationName", "StationName", "name", "Name")
    river = _pick(item, "river", "River", "riverName", "RiverName")
    district = _pick(item, "district", "District", "districtName", "DistrictName")
    state = _pick(item, "state", "State", "stateName", "StateName")
    level = _number(_pick(item, "water_level_m", "waterLevel", "water_level", "level", "Gauge", "gauge"))
    warning = _number(_pick(item, "warning_level_m", "warningLevel", "warning_level", "Warning", "warning"))
    danger = _number(_pick(item, "danger_level_m", "dangerLevel", "danger_level", "Danger", "danger"))
    previous = _number(_pick(item, "water_level_1h_before_m", "previousLevel", "level1hBefore", "oneHourBefore"))
    latitude = _number(_pick(item, "latitude", "Latitude", "lat"))
    longitude = _number(_pick(item, "longitude", "Longitude", "lon", "lng"))
    observed = _pick(item, "observed", "Observed", "observationTime", "timestamp", "Timestamp", "time", "dateTime")

    # Only Bihar gauges belong on the Bihar Live page. Do not accidentally
    # expose another state's stations if the upstream response is nationwide.
    if state is not None and str(state).strip().lower() not in {"bihar", "बिहार"}:
        return None
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
        "rise_1h_m": round(level - previous, 4) if previous is not None else None,
        # Kept for backend auditing only; frontend intentionally ignores it.
        "observed": str(observed) if observed is not None else None,
    }


def _extract_rows(payload: Any) -> list[dict]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []

    for key in ("data", "stations", "records", "results", "items", "waterLevels", "observations"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]

    # Some feeds wrap station records one level deeper.
    for value in payload.values():
        if isinstance(value, dict):
            rows = _extract_rows(value)
            if rows:
                return rows
    return []


def _request_json(url: str) -> Any:
    response = requests.get(
        url,
        params={"format": "json", "state": "Bihar"},
        headers={
            "Accept": "application/json",
            "User-Agent": "VARSHAGUARD/1.0",
            "Cache-Control": "no-cache, no-store",
            "Pragma": "no-cache",
        },
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response.json()


def fetch_live_data() -> dict:
    """Fetch current Bihar station observations at request time.

    No repository CSV/fixture is used here. If every upstream endpoint fails,
    the function raises and the API returns an explicit 502 instead of serving
    stale data while pretending it is live.
    """
    errors: list[str] = []

    for url in CWC_URLS:
        try:
            payload = _request_json(url)
            source_rows = _extract_rows(payload)
            stations = []
            seen = set()
            for item in source_rows:
                normalized = _normalize_source_row(item)
                if normalized and normalized["station"] not in seen:
                    seen.add(normalized["station"])
                    stations.append(normalized)

            if stations:
                stations.sort(key=lambda row: row["station"].lower())
                return {
                    "success": True,
                    "source": "CWC/India-WRIS",
                    "fetched_at": _utc_now(),
                    "stations": stations,
                }

            errors.append(f"{url}: no usable Bihar station rows")
        except Exception as error:
            errors.append(f"{url}: {error}")

    raise RuntimeError("Live Bihar station feed unavailable; " + " | ".join(errors))
