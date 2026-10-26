from __future__ import annotations

import math
import threading
import time
from datetime import datetime, timedelta, timezone

import requests

IST = timezone(timedelta(hours=5, minutes=30))
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
CACHE_SECONDS = 600
REQUEST_TIMEOUT_SECONDS = 8

# Forecast points are colocated with the two CWC focus gauges.
FOCUS_POINTS = {
    "patna": {"name": "Patna · Gandhighat", "latitude": 25.623333, "longitude": 85.171111},
    "muzaffarpur": {"name": "Muzaffarpur · Sikandarpur", "latitude": 26.142778, "longitude": 85.376111},
}
_cache_lock = threading.Lock()
_cache: dict[str, tuple[float, dict]] = {}


def _unavailable(district: str, message: str) -> dict:
    return {
        "success": True,
        "available": False,
        "district": district,
        "source": "Open-Meteo",
        "message": message,
    }


def get_rainfall_forecast(district: str, force_refresh: bool = False) -> dict:
    """Return a live 24-hour point rainfall outlook, separate from flood probability."""
    key = str(district).strip().lower()
    point = FOCUS_POINTS.get(key)
    if point is None:
        return _unavailable(key, "Rainfall forecast is not available for this location.")

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
        "hourly": "precipitation,precipitation_probability",
        "forecast_days": 2,
        "timezone": "Asia/Kolkata",
        "timeformat": "iso8601",
    }
    try:
        response = requests.get(
            OPEN_METEO_URL,
            params=params,
            headers={"User-Agent": "VarshaGuard/1.0 (Bihar flood-risk prototype)"},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError):
        result = _unavailable(key, "The rainfall outlook is temporarily unavailable.")
    else:
        hourly = payload.get("hourly") if isinstance(payload, dict) else None
        times = hourly.get("time") if isinstance(hourly, dict) else None
        precipitation = hourly.get("precipitation") if isinstance(hourly, dict) else None
        probabilities = hourly.get("precipitation_probability") if isinstance(hourly, dict) else None
        if not isinstance(times, list) or not isinstance(precipitation, list):
            result = _unavailable(key, "The weather source returned an unexpected forecast format.")
        else:
            now = datetime.now(IST)
            start = now.replace(minute=0, second=0, microsecond=0)
            end = start + timedelta(hours=24)
            selected = []
            peak_probability = None
            for index, value in enumerate(times):
                try:
                    forecast_time = datetime.fromisoformat(str(value))
                    if forecast_time.tzinfo is None:
                        forecast_time = forecast_time.replace(tzinfo=IST)
                    if not (start <= forecast_time < end):
                        continue
                    rain = float(precipitation[index])
                    if not math.isfinite(rain) or rain < 0:
                        continue
                    selected.append((forecast_time, rain))
                    if isinstance(probabilities, list) and index < len(probabilities) and probabilities[index] is not None:
                        chance = float(probabilities[index])
                        if 0 <= chance <= 100:
                            peak_probability = chance if peak_probability is None else max(peak_probability, chance)
                except (IndexError, TypeError, ValueError, OverflowError):
                    continue

            if len(selected) < 18:
                result = _unavailable(key, "There are not enough hourly forecast values for a 24-hour outlook.")
            else:
                fetched_at = datetime.now(timezone.utc).astimezone(IST)
                result = {
                    "success": True,
                    "available": True,
                    "district": key,
                    "location": point["name"],
                    "source": "Open-Meteo",
                    "source_url": "https://open-meteo.com/en/docs",
                    "forecast_rainfall_24h_mm": round(sum(value for _, value in selected), 1),
                    "peak_hourly_rainfall_probability_pct": round(peak_probability, 0) if peak_probability is not None else None,
                    "wet_hours_forecast": sum(1 for _, value in selected if value >= 0.1),
                    "forecast_hours_available": len(selected),
                    "forecast_start_ist": selected[0][0].isoformat(timespec="minutes"),
                    "forecast_end_ist": end.isoformat(timespec="minutes"),
                    "fetched_at_ist": fetched_at.isoformat(timespec="seconds"),
                    "note": "Weather-model rainfall outlook for the CWC gauge location. It is not a flood probability and is not included in the CWC risk model percentage.",
                }

    with _cache_lock:
        _cache[key] = (time.monotonic(), dict(result))
    return result
