"""Bihar 24-hour flood early-warning engine.

The calibrated ML probability predicts a documented Bihar flood-event START
in the target district on the following day, using historical Bihar rainfall
and flood-inventory labels. Live Bihar river level, threshold exceedance and
trend are fetched independently and are used as hydrologic confirmation for
the alert state. They are intentionally not injected into the calibrated
probability because the supplied historical rainfall/river observations do
not contain enough overlapping 24-hour flood labels for a defensible joint
supervised model.
"""
from __future__ import annotations

import base64
import io
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
import requests

from .data_service import fetch_live_data

BASE_DIR = Path(__file__).resolve().parents[2]
# Compact artifact is intentionally used for serverless deployment. It is a
# valid joblib pickle encoded as base64 (not zlib-compressed).
MODEL_B64_PATH = BASE_DIR / "models" / "bihar_flood_24h_rainfall_model_compact.pkl.b64"
RAINFALL_API = "https://sayantan-aquacarta.github.io/rainfall-pipeline/api/by-date/{date}.json"
MODEL_FEATURES = (
    "rainfall_mm", "rainfall_max_mm", "rainfall_min_mm", "rainfall_3d_sum_mm",
    "rainfall_3d_max_mm", "rainfall_7d_sum_mm", "rainfall_7d_max_mm",
    "rainfall_14d_sum_mm", "rainfall_14d_max_mm", "rainfall_change_1d_mm",
    "station_count", "month", "is_monsoon",
)


def _number(value: Any, default: float = 0.0) -> float:
    try:
        x = float(value)
        return x if np.isfinite(x) else default
    except (TypeError, ValueError):
        return default


def _normalise(value: Any) -> str:
    return " ".join(str(value or "").upper().replace("_", " ").split())


def _payload_rows(payload: Any) -> list[dict]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        for key in ("data", "rows", "results", "rainfall"):
            if isinstance(payload.get(key), list):
                return [x for x in payload[key] if isinstance(x, dict)]
    return []


@lru_cache(maxsize=1)
def _load_artifact() -> dict:
    if not MODEL_B64_PATH.exists():
        raise FileNotFoundError("Bihar 24h flood model artifact is not installed.")
    raw = base64.b64decode(MODEL_B64_PATH.read_text(encoding="utf-8").strip(), validate=True)
    artifact = joblib.load(io.BytesIO(raw))
    required = {"model", "calibrator", "features", "model_name", "target", "horizon_hours"}
    missing = required.difference(artifact)
    if missing:
        raise ValueError("Bihar flood model artifact missing: " + ", ".join(sorted(missing)))
    if tuple(artifact["features"]) != MODEL_FEATURES:
        raise ValueError("Bihar flood model feature schema mismatch.")
    return artifact


@lru_cache(maxsize=32)
def _fetch_daily_rainfall(date_text: str) -> list[dict]:
    response = requests.get(
        RAINFALL_API.format(date=date_text),
        timeout=12,
        headers={"Cache-Control": "no-cache", "User-Agent": "VARSHAGUARD/1.0"},
    )
    response.raise_for_status()
    return _payload_rows(response.json())


def _live_rainfall(days: int = 14):
    now = datetime.now(timezone.utc) + pd.Timedelta(hours=5, minutes=30)
    daily: dict[str, dict[str, float]] = {}
    timestamps: dict[str, str] = {}
    station_counts: dict[str, dict[str, int]] = {}
    failures: list[str] = []
    for days_back in range(days - 1, -1, -1):
        date_text = (now - pd.Timedelta(days=days_back)).date().isoformat()
        try:
            rows = _fetch_daily_rainfall(date_text)
        except Exception as exc:
            failures.append(f"{date_text}: {exc}")
            continue
        district_values: dict[str, list[float]] = {}
        for row in rows:
            if _normalise(row.get("state", row.get("State"))) != "BIHAR":
                continue
            district = _normalise(row.get("district", row.get("District")))
            if not district:
                continue
            value = max(0.0, _number(row.get("day_actual_mm", row.get("Daily Actual"))))
            district_values.setdefault(district, []).append(value)
        for district, values in district_values.items():
            daily.setdefault(district, {})[date_text] = float(np.mean(values))
            station_counts.setdefault(district, {})[date_text] = len(values)
            timestamps[district] = date_text
    return daily, timestamps, station_counts, failures


def _rain_features(series: dict[str, float], month: int) -> dict[str, float]:
    ordered = [series[d] for d in sorted(series)] or [0.0]
    last = ordered[-1]
    prev = ordered[-2] if len(ordered) > 1 else last
    last3, last7, last14 = ordered[-3:], ordered[-7:], ordered[-14:]
    return {
        "rainfall_mm": last,
        "rainfall_max_mm": max(last3),
        "rainfall_min_mm": min(last3),
        "rainfall_3d_sum_mm": sum(last3),
        "rainfall_3d_max_mm": max(last3),
        "rainfall_7d_sum_mm": sum(last7),
        "rainfall_7d_max_mm": max(last7),
        "rainfall_14d_sum_mm": sum(last14),
        "rainfall_14d_max_mm": max(last14),
        "rainfall_change_1d_mm": last - prev,
        "station_count": 1.0,
        "month": float(month),
        "is_monsoon": float(month in (6, 7, 8, 9)),
    }


def _river_summary(stations: list[dict]) -> dict:
    levels, rises = [], []
    warning_count = danger_count = 0
    for station in stations:
        level = _number(station.get("water_level_m"), np.nan)
        warning = _number(station.get("warning_level_m"), np.nan)
        danger = _number(station.get("danger_level_m"), np.nan)
        rise = _number(station.get("rise_1h_m"), np.nan)
        if np.isfinite(level): levels.append(level)
        if np.isfinite(rise): rises.append(rise)
        if np.isfinite(danger) and np.isfinite(level) and level >= danger:
            danger_count += 1
        elif np.isfinite(warning) and np.isfinite(level) and level >= warning:
            warning_count += 1
    return {
        "count": len(stations),
        "mean": float(np.mean(levels)) if levels else None,
        "max": float(np.max(levels)) if levels else None,
        "warning_count": warning_count,
        "danger_count": danger_count,
        "rise": float(np.mean(rises)) if rises else None,
        "stations": stations,
    }


def _alert_state(probability: float, river: dict) -> str:
    if probability >= 0.70 or river["danger_count"] > 0:
        return "HIGH"
    if probability >= 0.40 or river["warning_count"] > 0:
        return "MEDIUM"
    return "LOW"


def _river_confirmation(river: dict) -> str:
    if river["danger_count"] > 0:
        return "DANGER"
    if river["warning_count"] > 0:
        return "WARNING"
    if river["rise"] is not None and river["rise"] > 0:
        return "RISING"
    return "NORMAL"


def _inundation_proxy(probability: float, river: dict) -> dict:
    if river["max"] is None or not river["stations"]:
        return {"available": False, "extent_percent": None, "depth_m": None, "method": "insufficient_live_hydrology"}
    exceedance = 0.0
    for station in river["stations"]:
        level = _number(station.get("water_level_m"), np.nan)
        warning = _number(station.get("warning_level_m"), np.nan)
        danger = _number(station.get("danger_level_m"), np.nan)
        if np.isfinite(level) and np.isfinite(warning) and np.isfinite(danger) and danger > warning:
            exceedance = max(exceedance, max(0.0, min(1.5, (level - warning) / (danger - warning))))
    return {
        "available": True,
        "extent_percent": round(max(0.0, min(100.0, 8 + 52 * min(exceedance, 1) + 30 * probability)), 1),
        "depth_m": round(max(0.0, min(2.5, 0.05 + 0.65 * min(exceedance, 1) + 0.7 * probability)), 2),
        "confidence": None,
        "method": "hydrology_spatial_proxy",
        "physical_model": False,
        "message": "Proxy only: no DEM, floodplain geometry or hydraulic simulation is used.",
    }


def clear_ml_cache() -> None:
    _load_artifact.cache_clear()
    _fetch_daily_rainfall.cache_clear()


def build_bihar_district_risk() -> dict:
    artifact = _load_artifact()
    daily_rain, rain_timestamps, station_counts, rain_failures = _live_rainfall(14)
    live = fetch_live_data()
    by_district: dict[str, list[dict]] = {}
    for station in live.get("stations", []):
        district = _normalise(station.get("district"))
        if district:
            by_district.setdefault(district, []).append(station)

    now = datetime.now(timezone.utc) + pd.Timedelta(hours=5, minutes=30)
    rows = []
    for district in sorted(set(daily_rain) | set(by_district)):
        rain = _rain_features(daily_rain.get(district, {}), now.month)
        if district in station_counts:
            rain["station_count"] = float(station_counts[district].get(rain_timestamps.get(district, ""), 1))
        X = pd.DataFrame([{feature: rain.get(feature, 0.0) for feature in artifact["features"]}], columns=artifact["features"])
        raw = float(artifact["model"].predict_proba(X)[0, 1])
        probability = float(np.clip(artifact["calibrator"].predict([raw])[0], 0.0, 1.0))
        river = _river_summary(by_district.get(district, []))
        rows.append({
            "district": district.title(),
            "flood_probability": round(probability, 4),
            "flood_probability_percent": round(probability * 100.0, 2),
            "risk": _alert_state(probability, river),
            "river_confirmation": _river_confirmation(river),
            "raw_model_probability": round(raw, 4),
            "rainfall_24h_mm": round(rain["rainfall_mm"], 2),
            "rainfall_72h_mm": round(rain["rainfall_3d_sum_mm"], 2),
            "rainfall_7d_mm": round(rain["rainfall_7d_sum_mm"], 2),
            "rainfall_14d_mm": round(rain["rainfall_14d_sum_mm"], 2),
            "rainfall_station_count": int(rain["station_count"]),
            "river_level_mean_m": round(river["mean"], 2) if river["mean"] is not None else None,
            "river_level_max_m": round(river["max"], 2) if river["max"] is not None else None,
            "river_station_count": river["count"],
            "river_warning_count": river["warning_count"],
            "river_danger_count": river["danger_count"],
            "river_mean_rise_1h_m": round(river["rise"], 4) if river["rise"] is not None else None,
            "inundation": _inundation_proxy(probability, river),
            "data_timestamp": rain_timestamps.get(district, live.get("fetched_at", "")),
        })

    return {
        "success": True,
        "region": "Bihar",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "prediction_horizon_hours": int(artifact["horizon_hours"]),
        "model": {
            "name": artifact["model_name"],
            "type": type(artifact["model"]).__name__,
            "target": artifact["target"],
            "calibrated": True,
            "calibration_method": artifact["calibration_method"],
            "scope": artifact["scope"],
            "training_period": artifact["training_period"],
            "calibration_period": artifact["calibration_period"],
            "test_period": artifact["test_period"],
            "test_metrics": artifact["test_metrics"],
            "features": list(artifact["features"]),
            "warning": artifact["river_note"],
        },
        "rainfall_source": RAINFALL_API,
        "river_source": live.get("source_url"),
        "river_fetched_at": live.get("fetched_at"),
        "rainfall_failures": rain_failures,
        "districts": rows,
        "count": len(rows),
    }
