"""Live inference for the experimental CWC Bihar gauge model.

The upstream FFS endpoint is public but not a documented stable API. Outputs are
research signals for gauge threshold crossing, not inundation forecasts or alerts.
"""
from __future__ import annotations

import copy
import json
import threading
import time
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[3]
MODEL_STEM = "cwc_bihar_gauge_24h_stage_research"
MODEL_PATH = ROOT / "models" / "research" / f"{MODEL_STEM}.joblib"
METADATA_PATH = ROOT / "models" / "research" / f"{MODEL_STEM}.metadata.json"
CWC_ENDPOINT = "https://ffs.india-water.gov.in/iam/api/new-entry-data/specification/sorted"
IST = timezone(timedelta(hours=5, minutes=30))
CACHE_SECONDS = 300
FAILURE_CACHE_SECONDS = 30
REQUEST_TIMEOUT_SECONDS = 14
STALE_AFTER_HOURS = 24

FOCUS_STATIONS = {
    "003-MGD5PTN": "Patna",
    "004-MGD4PTN": "Muzaffarpur",
}

_cache_lock = threading.Lock()
_cache_value: dict | None = None
_cache_at = 0.0
_cache_ttl = CACHE_SECONDS


class LiveFeedUnavailable(RuntimeError):
    """Raised when CWC input or the model artifact cannot be used safely."""


@lru_cache(maxsize=1)
def _load_bundle() -> tuple[object, dict]:
    if not MODEL_PATH.is_file() or not METADATA_PATH.is_file():
        raise LiveFeedUnavailable("The CWC research model is not included in this deployment.")
    try:
        metadata = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
        model = joblib.load(MODEL_PATH)
    except Exception as exc:
        raise LiveFeedUnavailable(f"The CWC research model could not be loaded: {exc}") from exc
    return model, metadata


def _expression(field: str, operator: str, value: str) -> dict:
    return {
        "expression": {
            "valueIsRelationField": False,
            "fieldName": field,
            "operator": operator,
            "value": value,
        }
    }


def _parse_local_timestamp(value) -> pd.Timestamp:
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return pd.NaT
    if parsed.tzinfo is not None:
        return parsed.tz_convert(IST).tz_localize(None)
    # CWC FFS dataTime values are returned as local India timestamps without an offset.
    return parsed


def _fetch_type(datatype: str, station_codes: list[str], now_ist: datetime) -> list[dict]:
    start = (now_ist - timedelta(days=9)).strftime("%Y-%m-%dT%H:%M:%S")
    end = (now_ist + timedelta(hours=6)).strftime("%Y-%m-%dT%H:%M:%S")
    specification = {
        "where": {
            "where": _expression("id.stationCode", "in", ",".join(station_codes)),
            "and": _expression("id.datatypeCode", "eq", datatype),
        },
        "and": _expression("id.dataTime", "btn", f"{start},{end}"),
    }
    params = {
        "sort-criteria": json.dumps({"sortOrderDtos": [{"fieldName": "id.dataTime", "sortOrder": "ASC"}]}),
        "specification": json.dumps(specification),
    }
    try:
        response = requests.get(
            CWC_ENDPOINT,
            params=params,
            headers={"User-Agent": "VarshaGuard/1.0 (Bihar CWC gauge research dashboard)"},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        rows = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise LiveFeedUnavailable(f"CWC {datatype} observations could not be fetched: {exc}") from exc
    if not isinstance(rows, list):
        raise LiveFeedUnavailable(f"CWC {datatype} response had an unexpected format.")
    return rows


def _rows_frame(rows: list[dict]) -> pd.DataFrame:
    parsed = []
    for row in rows:
        identifier = row.get("id") if isinstance(row.get("id"), dict) else {}
        code = str(row.get("stationCode") or identifier.get("stationCode") or "").strip().upper()
        timestamp = _parse_local_timestamp(identifier.get("dataTime"))
        value = pd.to_numeric(row.get("dataValue"), errors="coerce")
        if code and not pd.isna(timestamp) and not pd.isna(value):
            parsed.append({"station_code": code, "timestamp": timestamp, "value": float(value)})
    frame = pd.DataFrame(parsed, columns=["station_code", "timestamp", "value"])
    if not frame.empty:
        frame["date"] = frame["timestamp"].dt.date
    return frame


def _aggregate_stage(rows: list[dict], stations: dict) -> dict[str, pd.DataFrame]:
    frame = _rows_frame(rows)
    if frame.empty:
        return {}
    frame = frame[frame["station_code"].isin(stations)]
    frame = frame[frame["value"].between(-20, 100, inclusive="both")]
    daily = (
        frame.groupby(["station_code", "date"], as_index=False)
        .agg(
            minimum=("value", "min"),
            mean=("value", "mean"),
            maximum=("value", "max"),
            n_obs=("value", "size"),
            latest_timestamp=("timestamp", "max"),
        )
    )
    latest = (
        frame.sort_values("timestamp")
        .groupby(["station_code", "date"], as_index=False)
        .tail(1)[["station_code", "date", "value"]]
        .rename(columns={"value": "latest_value"})
    )
    daily = daily.merge(latest, on=["station_code", "date"], how="left")
    accepted = []
    for row in daily.to_dict("records"):
        station = stations.get(row["station_code"], {})
        danger = float(station.get("danger_level_m", np.nan))
        highest = float(station.get("published_highest_flow_level_m", np.nan))
        good = (
            row["n_obs"] >= 3
            and np.isfinite(danger)
            and np.isfinite(highest)
            and row["minimum"] >= danger - 25
            and danger - 20 <= row["mean"] <= highest + 2
            and danger - 20 <= row["maximum"] <= highest + 2
            and row["maximum"] >= row["mean"] >= row["minimum"]
        )
        if good:
            row["danger_level_m"] = danger
            row["stage_mean_margin_m"] = row["mean"] - danger
            row["stage_max_margin_m"] = row["maximum"] - danger
            accepted.append(row)
    if not accepted:
        return {}
    clean = pd.DataFrame(accepted)
    return {
        code: values.set_index("date").sort_index()
        for code, values in clean.groupby("station_code")
    }


def _aggregate_rain(rows: list[dict], station_codes: set[str]) -> dict[str, pd.DataFrame]:
    frame = _rows_frame(rows)
    if frame.empty:
        return {}
    frame = frame[frame["station_code"].isin(station_codes) & frame["value"].between(0, 500)]
    if frame.empty:
        return {}
    daily = (
        frame.groupby(["station_code", "date"], as_index=False)
        .agg(total_mm=("value", "sum"), n_obs=("value", "size"), latest_timestamp=("timestamp", "max"))
    )
    daily = daily[daily["total_mm"].between(0, 500) & daily["n_obs"].ge(1)]
    return {
        code: values.set_index("date").sort_index()
        for code, values in daily.groupby("station_code")
    }


def _at(data: dict[str, pd.DataFrame], code: str, day: date, column: str):
    station = data.get(code)
    if station is None or day not in station.index:
        return np.nan
    return station.at[day, column]


def _window_sum(data: dict[str, pd.DataFrame], code: str, end_day: date, days: int) -> float:
    values = [_at(data, code, end_day - timedelta(days=offset), "total_mm") for offset in reversed(range(days))]
    return float(np.sum(values)) if all(np.isfinite(value) for value in values) else np.nan


def _make_features(code: str, day: date, station_codes: list[str], stages: dict, rains: dict) -> tuple[pd.DataFrame, int, int]:
    station = stages[code]
    current = station.loc[day]
    level = float(current["maximum"])
    danger = float(current["danger_level_m"])
    d1 = _at(stages, code, day - timedelta(days=1), "maximum")
    d3 = _at(stages, code, day - timedelta(days=3), "maximum")
    d7 = _at(stages, code, day - timedelta(days=7), "maximum")
    recent_levels = [_at(stages, code, day - timedelta(days=offset), "maximum") for offset in (2, 1, 0)]
    rain_3d = _window_sum(rains, code, day, 3)
    rain_7d = _window_sum(rains, code, day, 7)
    target_day = day + timedelta(days=1)
    annual_phase = target_day.timetuple().tm_yday / 365.2425 * 2 * np.pi
    values = {
        "target_stage_mean_margin_m": float(current["stage_mean_margin_m"]),
        "target_stage_max_margin_m": float(current["stage_max_margin_m"]),
        "target_stage_change_24h_m": level - float(d1) if np.isfinite(d1) else np.nan,
        "target_stage_change_72h_m": level - float(d3) if np.isfinite(d3) else np.nan,
        "target_stage_change_168h_m": level - float(d7) if np.isfinite(d7) else np.nan,
        "target_stage_3day_mean_margin_m": float(np.mean(recent_levels) - danger) if all(np.isfinite(v) for v in recent_levels) else np.nan,
        "target_stage_n_obs": int(current["n_obs"]),
        "target_rainfall_24h_mm": _at(rains, code, day, "total_mm"),
        "target_rainfall_72h_mm": rain_3d,
        "target_rainfall_168h_mm": rain_7d,
        "target_month_sin": float(np.sin(annual_phase)),
        "target_month_cos": float(np.cos(annual_phase)),
        "target_station": code,
    }
    for network_code in station_codes:
        values[f"network_stage_margin_{network_code}"] = _at(stages, network_code, day, "stage_mean_margin_m")
        values[f"network_rainfall_mm_{network_code}"] = _at(rains, network_code, day, "total_mm")
    model, metadata = _load_bundle()
    columns = metadata.get("features", [])
    if not columns:
        raise LiveFeedUnavailable("The CWC model feature list is missing.")
    row = pd.DataFrame([{column: values.get(column, np.nan) for column in columns}], columns=columns)
    available_features = sum(
        1 for column in columns if column != "target_station" and pd.notna(values.get(column))
    )
    numeric_feature_count = sum(1 for column in columns if column != "target_station")
    return row, available_features, numeric_feature_count


def _make_prediction(code: str, district: str, stages: dict, rains: dict, station_codes: list[str], model, metadata: dict, now_ist: datetime) -> dict:
    stage = stages.get(code)
    station_meta = metadata["data_quality"]["stations"][code]
    if stage is None or stage.empty:
        return {
            "station_code": code,
            "station_name": station_meta["name"],
            "district": district,
            "status": "unavailable",
            "message": "No recent quality-checked CWC river readings were returned for this gauge.",
            "latitude": station_meta["lat"],
            "longitude": station_meta["lon"],
        }
    observed_day = max(stage.index)
    current = stage.loc[observed_day]
    last_observation = pd.Timestamp(current["latest_timestamp"])
    age_hours = max(0.0, (pd.Timestamp(now_ist.replace(tzinfo=None)) - last_observation).total_seconds() / 3600)
    rainfall_today = _at(rains, code, observed_day, "total_mm")
    result = {
        "station_code": code,
        "station_name": station_meta["name"],
        "district": district,
        "status": "available",
        "observed_date": observed_day.isoformat(),
        "observed_at_ist": last_observation.isoformat(timespec="minutes"),
        "data_age_hours": round(age_hours, 1),
        "observations_today": int(current["n_obs"]),
        "daily_summary_partial": last_observation.hour < 23,
        "current_stage_m": round(float(current["latest_value"]), 2),
        "daily_max_stage_m": round(float(current["maximum"]), 2),
        "danger_level_m": round(float(current["danger_level_m"]), 2),
        "warning_level_m": round(float(station_meta["warning_level_m"]), 2),
        "margin_to_danger_m": round(float(current["danger_level_m"] - current["latest_value"]), 2),
        "rainfall_today_mm": round(float(rainfall_today), 2) if np.isfinite(rainfall_today) else None,
        "latitude": station_meta["lat"],
        "longitude": station_meta["lon"],
        "source": "Central Water Commission Flood Forecasting System (CWC FFS)",
    }
    if age_hours > STALE_AFTER_HOURS:
        result.update({"status": "stale", "message": "The latest quality-checked river reading is over 24 hours old; no model signal is shown."})
        return result
    if float(current["maximum"]) >= float(current["danger_level_m"]):
        result.update({
            "status": "danger_level_reached",
            "signal": "Danger threshold reached in observed data",
            "message": "Today's observed maximum has reached or passed the published danger level. Follow official CWC and local authority updates.",
            "forecast_date": (observed_day + timedelta(days=1)).isoformat(),
            "model_probability": None,
        })
        return result
    row, available, total = _make_features(code, observed_day, station_codes, stages, rains)
    probability = float(model.predict_proba(row)[0][1])
    threshold = float(metadata["decision_threshold"])
    result.update({
        "status": "predicted",
        "signal": "Elevated model signal" if probability >= threshold else "Lower model signal",
        "model_probability": round(probability, 6),
        "decision_threshold": round(threshold, 6),
        "forecast_date": (observed_day + timedelta(days=1)).isoformat(),
        "feature_coverage": {"available": available, "total": total},
        "message": "Experimental model estimate for the gauge reaching CWC danger stage on the next calendar day. It is not a flood or inundation probability.",
    })
    return result


def _build_payload() -> dict:
    model, metadata = _load_bundle()
    station_meta = metadata.get("data_quality", {}).get("stations", {})
    station_codes = list(station_meta)
    if not station_codes:
        raise LiveFeedUnavailable("CWC station metadata is missing from the research model.")
    now_ist = datetime.now(timezone.utc).astimezone(IST)
    stage_rows = _fetch_type("HHS", station_codes, now_ist)
    rain_rows = _fetch_type("MPS", station_codes, now_ist)
    stages = _aggregate_stage(stage_rows, station_meta)
    rains = _aggregate_rain(rain_rows, set(station_codes))
    predictions = [
        _make_prediction(code, district, stages, rains, station_codes, model, metadata, now_ist)
        for code, district in FOCUS_STATIONS.items()
    ]
    now_naive = pd.Timestamp(now_ist.replace(tzinfo=None))

    def stations_updated_within(data: dict[str, pd.DataFrame], max_age_hours: int = 24) -> int:
        count = 0
        for frame in data.values():
            if frame.empty:
                continue
            latest = pd.Timestamp(frame["latest_timestamp"].max())
            age = (now_naive - latest).total_seconds() / 3600
            if -1 <= age <= max_age_hours:
                count += 1
        return count

    stage_count = stations_updated_within(stages)
    rain_count = stations_updated_within(rains)
    latest_stage = max(
        (pd.Timestamp(row["latest_timestamp"]) for frame in stages.values() for _, row in frame.iterrows()),
        default=None,
    )
    latest_rain = max(
        (pd.Timestamp(row["latest_timestamp"]) for frame in rains.values() for _, row in frame.iterrows()),
        default=None,
    )
    available = any(item["status"] in {"predicted", "danger_level_reached"} for item in predictions)
    if not available:
        raise LiveFeedUnavailable("CWC returned data, but neither target gauge has a recent quality-checked reading.")
    generated_at = now_ist.isoformat(timespec="seconds")
    return {
        "success": True,
        "available": True,
        "mode": "live_cwc_research",
        "model_name": metadata.get("model_name"),
        "model_type": metadata.get("selected_model"),
        "target_definition": "Next calendar day: whether the gauge's daily maximum stage reaches the published CWC danger level.",
        "generated_at_ist": generated_at,
        "source": {
            "name": "Central Water Commission Flood Forecasting System",
            "url": "https://ffs.india-water.gov.in/",
            "stage_datatype": "HHS",
            "rainfall_datatype": "MPS",
            "stage_rows_received": len(stage_rows),
            "rainfall_rows_received": len(rain_rows),
            "stations_with_recent_stage": stage_count,
            "stations_with_recent_rainfall": rain_count,
            "stations_in_model": len(station_codes),
            "latest_stage_at_ist": latest_stage.isoformat(timespec="minutes") if latest_stage is not None else None,
            "latest_rainfall_at_ist": latest_rain.isoformat(timespec="minutes") if latest_rain is not None else None,
            "status": "available",
        },
        "validation": {
            "research_only": True,
            "operationally_approved": False,
            "test_average_precision": metadata.get("test_metrics", {}).get("average_precision"),
            "test_precision_at_threshold": metadata.get("test_metrics", {}).get("precision"),
            "test_recall_at_threshold": metadata.get("test_metrics", {}).get("recall"),
            "note": "Historical evaluation only. Live feature coverage and calibration have not been operationally validated.",
        },
        "limitations": [
            "This predicts a gauge danger-stage crossing by the next calendar day, not flooding, inundation extent, or depth in a block or grid cell.",
            "It uses live CWC stage and rainfall observations; it does not ingest IMD radar, satellite rainfall, or numerical weather predictions.",
            "The current calendar day's live aggregates can be incomplete. Missing model inputs are median-imputed, so feature coverage is shown.",
            "This experimental output is not an official alert. Follow CWC, IMD, and local disaster-management guidance.",
        ],
        "predictions": predictions,
    }


def get_live_predictions(force_refresh: bool = False) -> dict:
    """Return a short-lived in-process cache so a dashboard refresh does not fan out to CWC."""
    global _cache_value, _cache_at, _cache_ttl
    with _cache_lock:
        age = time.monotonic() - _cache_at
        if _cache_value is not None and not force_refresh and age < _cache_ttl:
            cached = copy.deepcopy(_cache_value)
            cached["cache_age_seconds"] = round(age)
            return cached
        try:
            payload = _build_payload()
        except Exception as exc:
            payload = {
                "success": True,
                "available": False,
                "mode": "unavailable",
                "generated_at_ist": datetime.now(timezone.utc).astimezone(IST).isoformat(timespec="seconds"),
                "error": str(exc),
                "source": {
                    "name": "Central Water Commission Flood Forecasting System",
                    "url": "https://ffs.india-water.gov.in/",
                    "status": "unavailable",
                },
                "predictions": [],
                "limitations": ["No current model signal is shown because live source data or model inputs are unavailable."],
            }
        _cache_value = copy.deepcopy(payload)
        _cache_at = time.monotonic()
        _cache_ttl = CACHE_SECONDS if payload.get("available") else FAILURE_CACHE_SECONDS
        return payload
