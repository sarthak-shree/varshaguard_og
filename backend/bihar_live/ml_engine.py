"""Live Bihar flood-risk inference using the saved Bihar-trained calibrated model.

The model artifact is trained offline from aligned historical rainfall, river
telemetry and documented flood-event starts. The live endpoint only fetches
current observations and applies the exact saved feature schema; it never
re-trains per request and never fuses a heuristic river score into the model
probability.
"""
from __future__ import annotations

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
MODEL_PATH = BASE_DIR / "models" / "bihar_24h_flood_model.pkl"
RAINFALL_API = "https://sayantan-aquacarta.github.io/rainfall-pipeline/api/by-date/{date}.json"


def _number(value: Any, default: float = 0.0) -> float:
    try:
        x = float(value)
        return x if pd.notna(x) else default
    except (TypeError, ValueError):
        return default


def _payload_rows(payload: Any) -> list[dict]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        for key in ("data", "rows", "results", "rainfall"):
            if isinstance(payload.get(key), list):
                return [x for x in payload[key] if isinstance(x, dict)]
    return []


def _normalise(value: Any) -> str:
    return " ".join(str(value or "").upper().replace("_", " ").split())


@lru_cache(maxsize=1)
def _load_artifact() -> dict:
    if not MODEL_PATH.exists():
        raise FileNotFoundError("Bihar 24h model artifact is not installed.")
    artifact = joblib.load(MODEL_PATH)
    required = {"model", "calibrator", "features", "model_name", "target", "horizon_hours"}
    missing = required.difference(artifact)
    if missing:
        raise ValueError("Bihar model artifact missing: " + ", ".join(sorted(missing)))
    return artifact


@lru_cache(maxsize=8)
def _fetch_daily_rainfall(date_text: str) -> list[dict]:
    response = requests.get(
        RAINFALL_API.format(date=date_text),
        timeout=10,
        headers={"Cache-Control": "no-cache", "User-Agent": "VARSHAGUARD/1.0"},
    )
    response.raise_for_status()
    return _payload_rows(response.json())


def _live_rainfall() -> tuple[dict[str, list[float]], dict[str, str], list[str]]:
    now = datetime.now(timezone.utc) + pd.Timedelta(hours=5, minutes=30)
    values: dict[str, list[float]] = {}
    timestamps: dict[str, str] = {}
    failures: list[str] = []
    for days_back in (2, 1, 0):
        date_text = (now - pd.Timedelta(days=days_back)).date().isoformat()
        try:
            rows = _fetch_daily_rainfall(date_text)
        except Exception as exc:
            failures.append(f"{date_text}: {exc}")
            continue
        for row in rows:
            if _normalise(row.get("state", row.get("State"))) != "BIHAR":
                continue
            district = _normalise(row.get("district", row.get("District")))
            if not district:
                continue
            rain = max(0.0, _number(row.get("day_actual_mm", row.get("Daily Actual"))))
            values.setdefault(district, []).append(rain)
            stamp = str(row.get("date", row.get("Date", date_text)))
            timestamps[district] = max(timestamps.get(district, ""), stamp)
    return values, timestamps, failures


def _district_rain_features(values: list[float], month: int) -> dict[str, float]:
    last3 = ([0.0, 0.0, 0.0] + values)[-3:]
    d1, d2, d3 = last3[-1], last3[-2], last3[-3]
    return {
        "rainfall_mm": d1,
        "rainfall_max_mm": max(last3),
        "rainfall_3d_sum_mm": d1 + d2 + d3,
        "rainfall_3d_max_mm": max(last3),
        "rainfall_7d_sum_mm": d1 + d2 + d3,
        "rainfall_7d_max_mm": max(last3),
        "rainfall_14d_sum_mm": d1 + d2 + d3,
        "rainfall_14d_max_mm": max(last3),
        "rainfall_change_1d_mm": d1 - d2,
        "rain_station_count": 1,
        "month": month,
        "is_monsoon": int(month in (6, 7, 8, 9)),
    }


def _river_features(stations: list[dict]) -> dict[str, float]:
    if not stations:
        return {
            "level_mean_m": 0.0, "level_max_m": 0.0, "level_min_m": 0.0,
            "level_std_m": 0.0, "river_station_count": 0.0,
            "level_max_3d": 0.0, "level_mean_3d": 0.0,
            "level_max_7d": 0.0, "level_mean_7d": 0.0,
            "level_max_14d": 0.0, "level_mean_14d": 0.0,
            "level_rise_1d_m": 0.0,
        }
    levels = np.array([_number(s.get("water_level_m")) for s in stations], dtype=float)
    rises = np.array([_number(s.get("rise_1h_m")) for s in stations], dtype=float)
    mean = float(levels.mean())
    return {
        "level_mean_m": mean,
        "level_max_m": float(levels.max()),
        "level_min_m": float(levels.min()),
        "level_std_m": float(levels.std()),
        "river_station_count": float(len(stations)),
        "level_max_3d": float(levels.max()),
        "level_mean_3d": mean,
        "level_max_7d": float(levels.max()),
        "level_mean_7d": mean,
        "level_max_14d": float(levels.max()),
        "level_mean_14d": mean,
        "level_rise_1d_m": float(rises.mean()) if len(rises) else 0.0,
    }


def clear_ml_cache() -> None:
    _load_artifact.cache_clear()
    _fetch_daily_rainfall.cache_clear()


def build_bihar_district_risk() -> dict:
    artifact = _load_artifact()
    rainfall, rainfall_timestamps, rainfall_failures = _live_rainfall()
    live = fetch_live_data()
    stations = live["stations"]
    by_district: dict[str, list[dict]] = {}
    for station in stations:
        district = _normalise(station.get("district"))
        if district:
            by_district.setdefault(district, []).append(station)

    now = datetime.now(timezone.utc) + pd.Timedelta(hours=5, minutes=30)
    rows = []
    for district in sorted(set(rainfall) | set(by_district)):
        rain = _district_rain_features(rainfall.get(district, [0.0]), now.month)
        river = _river_features(by_district.get(district, []))
        feature_values = {**rain, **river}
        X = pd.DataFrame([{feature: feature_values.get(feature, 0.0) for feature in artifact["features"]}], columns=artifact["features"])
        raw_probability = float(artifact["model"].predict_proba(X)[0, 1])
        probability = float(np.clip(artifact["calibrator"].predict([raw_probability])[0], 0.0, 1.0))
        risk = "HIGH" if probability >= 0.70 else "MEDIUM" if probability >= 0.40 else "LOW"
        rows.append({
            "district": district.title(),
            "flood_probability": round(probability, 4),
            "flood_probability_percent": round(probability * 100.0, 2),
            "risk": risk,
            "raw_model_probability": round(raw_probability, 4),
            "rainfall_24h_mm": round(rain["rainfall_mm"], 2),
            "rainfall_72h_mm": round(rain["rainfall_3d_sum_mm"], 2),
            "river_level_mean_m": round(river["level_mean_m"], 2),
            "river_level_max_m": round(river["level_max_m"], 2),
            "river_station_count": int(river["river_station_count"]),
            "data_timestamp": rainfall_timestamps.get(district, live.get("fetched_at", "")),
        })

    warning = (
        "Estimated probability of a documented flood event starting in this district within the next 24 hours. "
        "Prototype model: use for research/demo, not operational public warning decisions."
    )
    if rainfall_failures:
        warning += " Some rainfall dates were unavailable; affected features use only retrieved observations."

    return {
        "success": True,
        "region": "Bihar",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "prediction_horizon_hours": int(artifact["horizon_hours"]),
        "model": {
            "type": type(artifact["model"]).__name__,
            "name": artifact["model_name"],
            "scope": artifact["scope"],
            "calibrated": True,
            "calibration_method": artifact["calibration_method"],
            "target": artifact["target"],
            "features": artifact["features"],
            "historical_training_rows": artifact["training_rows"],
            "historical_test_rows": artifact["test_rows"],
            "test_metrics": artifact["calibrated_test_metrics"][artifact["model_name"]],
            "warning": warning,
        },
        "rainfall_source": RAINFALL_API,
        "river_source": live.get("source_url"),
        "river_fetched_at": live.get("fetched_at"),
        "districts": rows,
        "count": len(rows),
    }
