"""Live inference for the experimental CWC Bihar gauge model.

The upstream FFS endpoint is public but not a documented stable API. Outputs are
research signals for gauge threshold crossing, not inundation forecasts or alerts.
"""
from __future__ import annotations

import copy
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
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
REQUEST_TIMEOUT_SECONDS = 8
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
    end = now_ist.strftime("%Y-%m-%dT%H:%M:%S")
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
    except requests.RequestException as exc:
        raise LiveFeedUnavailable(f"CWC {datatype} feed is unreachable ({type(exc).__name__}).") from exc
    try:
        rows = response.json()
    except ValueError as exc:
        raise LiveFeedUnavailable(f"CWC {datatype} feed returned invalid JSON.") from exc
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
    accepted = []
    for row in frame.to_dict("records"):
        station = stations.get(row["station_code"], {})
        danger = float(station.get("danger_level_m", np.nan))
        highest = float(station.get("highest_flow_level_m", station.get("published_highest_flow_level_m", np.nan)))
        if np.isfinite(danger) and np.isfinite(highest) and danger - 25 <= row["value"] <= highest + 2:
            accepted.append(row)
    if not accepted:
        return {}
    clean = pd.DataFrame(accepted)
    clean = (
        clean.groupby(["station_code", "timestamp"], as_index=False)
        .agg(value=("value", "median"))
        .sort_values(["station_code", "timestamp"])
    )
    return {
        code: values.set_index("timestamp").sort_index()
        for code, values in clean.groupby("station_code")
    }


def _aggregate_rain(rows: list[dict], station_codes: set[str]) -> dict[str, pd.DataFrame]:
    frame = _rows_frame(rows)
    if frame.empty:
        return {}
    frame = frame[frame["station_code"].isin(station_codes) & frame["value"].between(0, 500)]
    if frame.empty:
        return {}
    hourly = (
        frame.groupby(["station_code", "timestamp"], as_index=False)
        .agg(value=("value", "sum"))
        .sort_values(["station_code", "timestamp"])
    )
    return {
        code: values.set_index("timestamp").sort_index()
        for code, values in hourly.groupby("station_code")
    }


def _latest_value(data: dict[str, pd.DataFrame], code: str, at: pd.Timestamp, max_age_hours: int = 3):
    station = data.get(code)
    if station is None or station.empty:
        return np.nan, np.nan, None
    position = int(station.index.searchsorted(at, side="right") - 1)
    if position < 0:
        return np.nan, np.nan, None
    timestamp = pd.Timestamp(station.index[position])
    age_hours = max(0.0, (at - timestamp).total_seconds() / 3600)
    if age_hours > max_age_hours:
        return np.nan, age_hours, timestamp
    return float(station.iloc[position]["value"]), age_hours, timestamp


def _rain_window(data: dict[str, pd.DataFrame], code: str, issue_time: pd.Timestamp, hours: int, minimum_observations: int) -> float:
    station = data.get(code)
    if station is None or station.empty:
        return np.nan
    window = station.loc[(station.index > issue_time - pd.Timedelta(hours=hours)) & (station.index <= issue_time), "value"]
    if len(window) < minimum_observations:
        return np.nan
    return float(window.sum())


def _make_features(code: str, issue_time: pd.Timestamp, station_codes: list[str], stages: dict, rains: dict,
                   model, metadata: dict) -> tuple[pd.DataFrame, int, int]:
    station = stages[code]
    current_level, _, _ = _latest_value(stages, code, issue_time, max_age_hours=3)
    station_meta = metadata["data_quality"]["stations"][code]
    warning = float(station_meta["warning_level_m"])
    danger = float(station_meta["danger_level_m"])
    values = {
        "target_stage_margin_warning_m": current_level - warning,
        "target_stage_margin_danger_m": current_level - danger,
        "target_stage_value_m": current_level,
        "target_hour_sin": float(np.sin(issue_time.hour / 24 * 2 * np.pi)),
        "target_hour_cos": float(np.cos(issue_time.hour / 24 * 2 * np.pi)),
        "target_month_sin": float(np.sin(issue_time.dayofyear / 365.2425 * 2 * np.pi)),
        "target_month_cos": float(np.cos(issue_time.dayofyear / 365.2425 * 2 * np.pi)),
        "target_rainfall_24h_mm": _rain_window(rains, code, issue_time, 24, 2),
        "target_rainfall_72h_mm": _rain_window(rains, code, issue_time, 72, 4),
        "target_rainfall_24h_observations": int(len(rains.get(code, pd.DataFrame()).loc[
            (rains[code].index > issue_time - pd.Timedelta(hours=24)) & (rains[code].index <= issue_time)
        ])) if code in rains else 0,
        "target_station": code,
    }
    for lag in (6, 12, 24, 48, 72):
        past_level, _, _ = _latest_value(stages, code, issue_time - pd.Timedelta(hours=lag), max_age_hours=3)
        values[f"target_stage_change_{lag}h_m"] = current_level - past_level if np.isfinite(past_level) else np.nan
    prior_day = station.loc[(station.index > issue_time - pd.Timedelta(hours=24)) & (station.index <= issue_time), "value"]
    values["target_stage_mean_24h_m"] = float(prior_day.mean()) if len(prior_day) >= 12 else np.nan
    values["target_stage_max_24h_m"] = float(prior_day.max()) if len(prior_day) >= 12 else np.nan
    for network_code in station_codes:
        network_level, age_hours, _ = _latest_value(stages, network_code, issue_time, max_age_hours=3)
        network_meta = metadata["data_quality"]["stations"][network_code]
        values[f"network_warning_margin_{network_code}_m"] = network_level - float(network_meta["warning_level_m"]) if np.isfinite(network_level) else np.nan
        values[f"network_stage_age_{network_code}_h"] = age_hours
    columns = metadata.get("features", [])
    if not columns:
        raise LiveFeedUnavailable("The CWC model feature list is missing.")
    row = pd.DataFrame([{column: values.get(column, np.nan) for column in columns}], columns=columns)
    available_features = sum(
        1 for column in columns if column != "target_station" and pd.notna(values.get(column))
    )
    numeric_feature_count = sum(1 for column in columns if column != "target_station")
    return row, available_features, numeric_feature_count


def _risk_level(probability: float, decision_threshold: float) -> str:
    """Map the estimated chance to dashboard bands, not official alert levels."""
    if probability >= 0.5:
        return "high"
    if probability >= decision_threshold:
        return "medium"
    return "low"


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
    last_observation = pd.Timestamp(stage.index.max())
    observed_day = last_observation.date()
    current_stage = float(stage.loc[last_observation, "value"])
    age_hours = max(0.0, (pd.Timestamp(now_ist.replace(tzinfo=None)) - last_observation).total_seconds() / 3600)
    today = stage.loc[stage.index.date == observed_day, "value"]
    rainfall_24h = _rain_window(rains, code, last_observation, 24, 2)
    warning_level = float(station_meta["warning_level_m"])
    danger_level = float(station_meta["danger_level_m"])
    history_start = last_observation - pd.Timedelta(hours=24)
    stage_history = stage.loc[
        (stage.index >= history_start) & (stage.index <= last_observation), "value"
    ]
    result = {
        "station_code": code,
        "station_name": station_meta["name"],
        "district": district,
        "status": "available",
        "observed_date": observed_day.isoformat(),
        "observed_at_ist": last_observation.isoformat(timespec="minutes"),
        "forecast_start_ist": last_observation.isoformat(timespec="minutes"),
        "forecast_end_ist": (last_observation + pd.Timedelta(hours=24)).isoformat(timespec="minutes"),
        "forecast_horizon_hours": 24,
        "data_age_hours": round(age_hours, 1),
        "observations_today": int(len(today)),
        "daily_summary_partial": last_observation.hour < 23,
        "current_stage_m": round(current_stage, 2),
        "daily_max_stage_m": round(float(today.max()), 2) if not today.empty else round(current_stage, 2),
        "stage_history": [
            {"timestamp_ist": timestamp.isoformat(timespec="minutes"), "stage_m": round(float(value), 2)}
            for timestamp, value in stage_history.items()
        ],
        "danger_level_m": round(danger_level, 2),
        "warning_level_m": round(warning_level, 2),
        "margin_to_warning_m": round(warning_level - current_stage, 2),
        "margin_to_danger_m": round(danger_level - current_stage, 2),
        "rainfall_24h_mm": round(float(rainfall_24h), 2) if np.isfinite(rainfall_24h) else None,
        "latitude": station_meta["lat"],
        "longitude": station_meta["lon"],
        "source": "Central Water Commission Flood Forecasting System (CWC FFS)",
    }
    if age_hours > STALE_AFTER_HOURS:
        result.update({
            "status": "stale",
            "risk_level": None,
            "risk_percentage": None,
            "risk_basis": "unavailable",
            "message": "The latest quality-checked river reading is over 24 hours old; no model signal is shown.",
        })
        return result
    if current_stage >= danger_level:
        result.update({
            "status": "danger_level_reached",
            "risk_level": "high",
            "risk_percentage": 100.0,
            "risk_basis": "observed",
            "signal": "Danger threshold reached in observed data",
            "message": "Today's observed maximum has reached or passed the published danger level. Follow official CWC and local authority updates.",
            "forecast_date": (last_observation + pd.Timedelta(hours=24)).date().isoformat(),
            "model_probability": None,
        })
        return result
    if current_stage >= warning_level:
        result.update({
            "status": "warning_level_reached",
            "risk_level": "high",
            "risk_percentage": 100.0,
            "risk_basis": "observed",
            "signal": "CWC warning threshold reached in observed data",
            "message": "The latest CWC river reading has reached the published warning level. This is an observation, not a 24-hour prediction.",
            "forecast_date": (last_observation + pd.Timedelta(hours=24)).date().isoformat(),
            "model_probability": None,
        })
        return result
    row, available, total = _make_features(code, last_observation, station_codes, stages, rains, model, metadata)
    if total and available < max(8, int(total * 0.35)):
        result.update({
            "status": "insufficient_inputs",
            "risk_level": None,
            "risk_percentage": None,
            "risk_basis": "unavailable",
            "message": "Too few recent river and rainfall inputs are available for a 24-hour estimate.",
            "feature_coverage": {"available": available, "total": total},
        })
        return result
    probability = float(model.predict_proba(row)[0][1])
    threshold = float(metadata["decision_threshold"])
    risk_level = _risk_level(probability, threshold)
    forecast_end = last_observation + pd.Timedelta(hours=24)
    focus_metrics = metadata.get("focus_gauge_test_metrics", {}).get(code, {})
    result.update({
        "status": "predicted",
        "risk_level": risk_level,
        "risk_percentage": round(probability * 100, 1),
        "risk_basis": "model_probability",
        "signal": f"{risk_level.title()} model risk",
        "model_probability": round(probability, 6),
        "decision_threshold": round(threshold, 6),
        "forecast_date": forecast_end.date().isoformat(),
        "feature_coverage": {"available": available, "total": total},
        "message": "Experimental estimate that this gauge may reach its CWC warning level in the 24 hours after the latest river reading. It is not a street or block flood probability.",
        "local_validation_note": focus_metrics.get("note"),
    })
    return result


def _build_payload() -> dict:
    model, metadata = _load_bundle()
    station_meta = metadata.get("data_quality", {}).get("stations", {})
    station_codes = list(station_meta)
    if not station_codes:
        raise LiveFeedUnavailable("CWC station metadata is missing from the research model.")
    now_ist = datetime.now(timezone.utc).astimezone(IST)
    with ThreadPoolExecutor(max_workers=2) as executor:
        stage_future = executor.submit(_fetch_type, "HHS", station_codes, now_ist)
        rain_future = executor.submit(_fetch_type, "MPS", station_codes, now_ist)
        stage_rows = stage_future.result()
        rainfall_error = None
        try:
            rain_rows = rain_future.result()
        except LiveFeedUnavailable as exc:
            # Stage is essential to this model; missing rainfall is median-imputed and disclosed.
            rainfall_error = str(exc)
            rain_rows = []
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
            latest = pd.Timestamp(frame.index.max())
            age = (now_naive - latest).total_seconds() / 3600
            if -1 <= age <= max_age_hours:
                count += 1
        return count

    stage_count = stations_updated_within(stages)
    rain_count = stations_updated_within(rains)
    latest_stage = max(
        (pd.Timestamp(frame.index.max()) for frame in stages.values() if not frame.empty),
        default=None,
    )
    latest_rain = max(
        (pd.Timestamp(frame.index.max()) for frame in rains.values() if not frame.empty),
        default=None,
    )
    available = any(item["status"] in {"predicted", "warning_level_reached", "danger_level_reached", "insufficient_inputs"} for item in predictions)
    if not available:
        raise LiveFeedUnavailable("CWC returned data, but neither target gauge has a recent quality-checked reading.")
    generated_at = now_ist.isoformat(timespec="seconds")
    return {
        "success": True,
        "available": True,
        "mode": "live_cwc_research",
        "model_name": metadata.get("model_name"),
        "model_type": metadata.get("selected_model"),
        "target_definition": "Rolling 24 hours after the latest accepted CWC stage reading: estimated chance the gauge reaches the published CWC warning level.",
        "risk_bands": {
            "low_max_exclusive_probability": float(metadata["decision_threshold"]),
            "medium_min_inclusive_probability": float(metadata["decision_threshold"]),
            "high_min_inclusive_probability": 0.5,
            "note": "Low is below the validation-selected model trigger; Medium is at or above that trigger but below 50%; High is 50% or more. An observed CWC warning or danger threshold is shown separately as observed, not forecast.",
        },
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
            "rainfall_status": "available" if rainfall_error is None else "unavailable",
            "rainfall_error": rainfall_error,
            "latest_stage_at_ist": latest_stage.isoformat(timespec="minutes") if latest_stage is not None else None,
            "latest_rainfall_at_ist": latest_rain.isoformat(timespec="minutes") if latest_rain is not None else None,
            "status": "available" if rainfall_error is None else "partial",
        },
        "validation": {
            "research_only": True,
            "operationally_approved": False,
            "test_average_precision": metadata.get("test_metrics", {}).get("average_precision"),
            "test_precision_at_threshold": metadata.get("test_metrics", {}).get("precision"),
            "test_recall_at_threshold": metadata.get("test_metrics", {}).get("recall"),
            "focus_gauge_test_metrics": metadata.get("focus_gauge_test_metrics", {}),
            "note": "Historical 2026 holdout evaluation only. The Muzaffarpur focus gauge had no positive warning crossings in the holdout, so local performance could not be estimated.",
        },
        "limitations": [
            "This estimates a gauge reaching its published CWC warning level within the next rolling 24 hours; it does not predict inundation extent or depth in a block or grid cell.",
            "It uses live CWC river-level and rainfall observations; it does not ingest IMD radar, satellite rainfall, or numerical weather forecasts.",
            "Historical hourly records cover only a few flood seasons. Muzaffarpur had no positive warning crossing in the 2026 holdout, so its local accuracy is unknown; the percentage is pooled from the Bihar gauge network.",
            "Missing model inputs are median-imputed; feature coverage is shown with each estimate.",
            "This experimental output is not an official alert. Follow CWC, IMD, and local disaster-management guidance.",
        ] + (["CWC rainfall data could not be loaded; missing rainfall inputs were median-imputed."] if rainfall_error else []),
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
        except LiveFeedUnavailable as exc:
            error_message = str(exc)
            payload = {
                "success": True,
                "available": False,
                "mode": "unavailable",
                "generated_at_ist": datetime.now(timezone.utc).astimezone(IST).isoformat(timespec="seconds"),
                "error": error_message,
                "source": {
                    "name": "Central Water Commission Flood Forecasting System",
                    "url": "https://ffs.india-water.gov.in/",
                    "status": "unavailable",
                },
                "predictions": [],
                "limitations": ["No current model signal is shown because live source data or model inputs are unavailable."],
            }
        except Exception:
            payload = {
                "success": True,
                "available": False,
                "mode": "unavailable",
                "generated_at_ist": datetime.now(timezone.utc).astimezone(IST).isoformat(timespec="seconds"),
                "error": "The live CWC model request failed. Please try again shortly.",
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
