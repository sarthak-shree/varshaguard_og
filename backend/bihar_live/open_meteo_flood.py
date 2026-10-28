"""Open-Meteo Flood API client for Bihar Live river-discharge context.

Discharge forecasts are hydrological context only; they are not flood probabilities.
"""
from __future__ import annotations

import math
import threading
import time
from datetime import datetime, timezone

import requests

OPEN_METEO_FLOOD_URL = "https://flood-api.open-meteo.com/v1/flood"
REQUEST_TIMEOUT_SECONDS = 10
CACHE_SECONDS = 900
DAILY_VARIABLES = (
    "river_discharge",
    "river_discharge_mean",
    "river_discharge_median",
    "river_discharge_max",
    "river_discharge_p75",
    "river_discharge_p25",
    "river_discharge_min",
)
MODEL_NAMES = (
    "seamless_v4",
    "forecast_v4",
    "consolidated_v4",
    "consolidated_v3",
    "seamless_v3",
    "forecast_v3",
)
# Use the existing CWC focus-gauge coordinates, not the Oslo example in the docs.
FOCUS_POINTS = {
    "patna": {
        "name": "Patna · Gandhighat",
        "latitude": 25.623333,
        "longitude": 85.171111,
    },
    "muzaffarpur": {
        "name": "Muzaffarpur · Sikandarpur",
        "latitude": 26.142778,
        "longitude": 85.376111,
    },
}
_cache_lock = threading.Lock()
_cache: dict[str, tuple[float, dict]] = {}


def _unavailable(district: str, message: str) -> dict:
    return {
        "success": True,
        "available": False,
        "district": district,
        "source": "Open-Meteo Flood API",
        "source_url": "https://open-meteo.com/en/docs/flood-api",
        "message": message,
        "operational": False,
    }


def get_river_discharge_forecast(district: str, force_refresh: bool = False) -> dict:
    """Fetch daily river-discharge forecast and ensemble summaries for a focus point."""
    key = str(district).strip().lower()
    point = FOCUS_POINTS.get(key)
    if point is None:
        return _unavailable(key, "Choose Patna or Muzaffarpur.")

    now_monotonic = time.monotonic()
    with _cache_lock:
        cached = _cache.get(key)
        if cached and not force_refresh and now_monotonic - cached[0] < CACHE_SECONDS:
            result = dict(cached[1])
            result["cache_age_seconds"] = round(now_monotonic - cached[0])
            return result

    params = {
        "latitude": point["latitude"],
        "longitude": point["longitude"],
        "daily": ",".join(DAILY_VARIABLES),
        "models": ",".join(MODEL_NAMES),
        "ensemble": "true",
        "forecast_days": 7,
        "past_days": 3,
        "timezone": "Asia/Kolkata",
    }
    try:
        response = requests.get(
            OPEN_METEO_FLOOD_URL,
            params=params,
            headers={"User-Agent": "VarshaGuard/1.0 (Bihar flood-risk prototype)"},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError):
        result = _unavailable(key, "The river-discharge forecast is temporarily unavailable.")
    else:
        daily = payload.get("daily") if isinstance(payload, dict) else None
        times = daily.get("time") if isinstance(daily, dict) else None
        if not isinstance(times, list) or not times:
            result = _unavailable(key, "Open-Meteo returned no usable daily discharge timeline.")
        else:
            # Preserve the provider's model/ensemble output instead of averaging unlike
            # models into an invented risk score.
            daily_data = {"time": times}
            for variable, values in daily.items():
                if variable != "time" and variable.startswith("river_discharge") and isinstance(values, list):
                    daily_data[variable] = values
            result = {
                "success": True,
                "available": True,
                "district": key,
                "location": point["name"],
                "coordinates": {
                    "latitude": point["latitude"],
                    "longitude": point["longitude"],
                },
                "source": "Open-Meteo Flood API",
                "source_url": "https://open-meteo.com/en/docs/flood-api",
                "fetched_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "timezone": payload.get("timezone", "Asia/Kolkata"),
                "units": payload.get("daily_units", {}),
                "models_requested": list(MODEL_NAMES),
                "ensemble_requested": True,
                "daily": daily_data,
                "note": (
                    "River-discharge forecast in the provider's stated units. "
                    "Model/ensemble spread is context, not a flood probability, "
                    "warning threshold, or replacement for CWC/IMD official guidance."
                ),
                "operational": False,
            }
            # Mark the response usable only when at least one requested variable has
            # a finite value; a valid-looking timeline alone can contain null data.
            def contains_finite_number(value):
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    return math.isfinite(value)
                if isinstance(value, list):
                    return any(contains_finite_number(item) for item in value)
                return False

            has_values = any(
                contains_finite_number(values)
                for name, values in daily_data.items()
                if name != "time"
            )
            if not has_values:
                result = _unavailable(key, "Open-Meteo returned a timeline but no numeric discharge values.")

    with _cache_lock:
        _cache[key] = (time.monotonic(), dict(result))
    return result
