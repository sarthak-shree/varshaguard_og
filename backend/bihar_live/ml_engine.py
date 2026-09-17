"""Bihar live flood-risk ML engine.

The engine converts the existing hourly rainfall training table into a daily
training set, evaluates a Random Forest with chronological validation, and
applies it to live Bihar district rainfall. Live river observations are then
used as a separate hydrological signal in the final conservative fusion.

Important: the repository's current historical rainfall table documents Assam
and Uttarakhand as its study regions. Therefore the Random Forest is a
cross-region rainfall model, not a Bihar-calibrated model, until Bihar-labeled
historical flood outcomes are added.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Any

import pandas as pd
import requests
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, roc_auc_score

from .data_service import fetch_live_data

BASE_DIR = __import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.dirname(__file__)))
DATA_PATH = __import__("os").path.join(BASE_DIR, "data", "processed", "flood_warning_ml_ready_v2.csv")
RAINFALL_API = "https://sayantan-aquacarta.github.io/rainfall-pipeline/api/by-date/{date}.json"

DAILY_FEATURES = [
    "rainfall_1h",
    "rainfall_3h",
    "rainfall_6h",
    "rainfall_12h",
    "rainfall_24h",
    "rainfall_48h",
    "rainfall_72h",
    "rainfall_6h_max",
    "rainfall_24h_max",
    "month",
    "hour_of_day",
    "is_monsoon",
]


def _number(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
        return result if pd.notna(result) else default
    except (TypeError, ValueError):
        return default


def _payload_rows(payload: Any) -> list[dict]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in ("data", "rows", "results", "rainfall"):
            value = payload.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)]
    return []


def _normalise_name(value: Any) -> str:
    return " ".join(str(value or "").upper().replace("_", " ").split())


def _historical_daily_frame() -> pd.DataFrame:
    data = pd.read_csv(DATA_PATH)
    timestamp_column = "timestamp" if "timestamp" in data.columns else "hour"
    data["timestamp"] = pd.to_datetime(data[timestamp_column], errors="coerce")
    data = data.dropna(subset=["timestamp", "flood_soon"]).copy()
    data["flood_soon"] = pd.to_numeric(data["flood_soon"], errors="coerce").fillna(0).astype(int)

    for column in DAILY_FEATURES:
        if column in ("month", "hour_of_day", "is_monsoon"):
            continue
        if column not in data.columns:
            data[column] = 0.0
        data[column] = pd.to_numeric(data[column], errors="coerce").fillna(0.0).clip(lower=0, upper=5000)

    data["date"] = data["timestamp"].dt.date
    data["month"] = data["timestamp"].dt.month
    data["hour_of_day"] = data["timestamp"].dt.hour
    data["is_monsoon"] = data["month"].isin([6, 7, 8, 9]).astype(int)

    group_columns = ["region", "station", "date"] if "region" in data.columns and "station" in data.columns else ["date"]
    aggregations = {
        column: "max"
        for column in DAILY_FEATURES
        if column not in ("month", "hour_of_day", "is_monsoon")
    }
    aggregations.update({
        "month": "first",
        "hour_of_day": "first",
        "is_monsoon": "first",
        "flood_soon": "max",
    })
    daily = data.groupby(group_columns, as_index=False).agg(aggregations)
    return daily.sort_values("date").reset_index(drop=True)


def _model() -> RandomForestClassifier:
    return RandomForestClassifier(
        n_estimators=300,
        max_depth=12,
        min_samples_leaf=2,
        class_weight="balanced",
        random_state=42,
        n_jobs=-1,
    )


@lru_cache(maxsize=1)
def _train_model() -> dict:
    if not __import__("os").path.exists(DATA_PATH):
        return {"ok": False, "error": "Historical training dataset is missing."}

    try:
        daily = _historical_daily_frame()
    except Exception as error:
        return {"ok": False, "error": "Historical dataset could not be prepared: " + str(error)}

    if daily.empty or daily["flood_soon"].nunique() < 2:
        return {"ok": False, "error": "Historical dataset does not contain both flood and non-flood classes."}

    unique_dates = pd.Series(sorted(daily["date"].unique()))
    if len(unique_dates) < 8:
        return {"ok": False, "error": "Not enough distinct historical dates for chronological validation."}

    split_count = min(5, len(unique_dates) - 1)
    fold_accuracies: list[float] = []
    fold_aucs: list[float] = []

    # Chronological validation by date. No future date is used to predict an
    # earlier validation period, avoiding random train/test leakage in a time series.
    for fold in range(1, split_count):
        boundary = int(len(unique_dates) * fold / split_count)
        if boundary <= 0 or boundary >= len(unique_dates):
            continue
        train_dates = set(unique_dates.iloc[:boundary])
        test_dates = set(unique_dates.iloc[boundary:boundary + max(1, len(unique_dates) // split_count)])
        train = daily[daily["date"].isin(train_dates)]
        test = daily[daily["date"].isin(test_dates)]
        if train.empty or test.empty or train["flood_soon"].nunique() < 2 or test["flood_soon"].nunique() < 2:
            continue

        candidate = _model()
        candidate.fit(train[DAILY_FEATURES], train["flood_soon"])
        predictions = candidate.predict(test[DAILY_FEATURES])
        probabilities = candidate.predict_proba(test[DAILY_FEATURES])[:, 1]
        fold_accuracies.append(float(accuracy_score(test["flood_soon"], predictions)))
        fold_aucs.append(float(roc_auc_score(test["flood_soon"], probabilities)))

    # Final inference model is trained only after validation, using all historical rows.
    final_model = _model()
    final_model.fit(daily[DAILY_FEATURES], daily["flood_soon"])

    return {
        "ok": True,
        "model": final_model,
        "training_rows": int(len(daily)),
        "test_rows": int(sum(len(daily[daily["date"].isin(set(unique_dates.iloc[max(0, int(len(unique_dates) * fold / split_count)):max(0, int(len(unique_dates) * fold / split_count)) + max(1, len(unique_dates) // split_count)]))]) for fold in range(1, split_count))),
        "accuracy": round(sum(fold_accuracies) / len(fold_accuracies), 4) if fold_accuracies else None,
        "roc_auc": round(sum(fold_aucs) / len(fold_aucs), 4) if fold_aucs else None,
        "validation_folds": len(fold_accuracies),
        "scope": "cross_region_daily_rainfall",
        "bihar_calibrated": False,
    }


def clear_ml_cache() -> None:
    _train_model.cache_clear()
    _fetch_daily_rainfall.cache_clear()


@lru_cache(maxsize=8)
def _fetch_daily_rainfall(date_text: str) -> list[dict]:
    response = requests.get(RAINFALL_API.format(date=date_text), timeout=8)
    response.raise_for_status()
    return _payload_rows(response.json())


def _live_bihar_rainfall() -> dict[str, list[float]]:
    now = datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)
    result: dict[str, list[float]] = {}
    for days_back in (2, 1, 0):
        date_text = (now - timedelta(days=days_back)).date().isoformat()
        rows = _fetch_daily_rainfall(date_text)
        for row in rows:
            if _normalise_name(row.get("state", row.get("State"))) != "BIHAR":
                continue
            district = _normalise_name(row.get("district", row.get("District")))
            if not district:
                continue
            rainfall = _number(row.get("day_actual_mm", row.get("Daily Actual")), 0.0)
            result.setdefault(district, []).append(max(0.0, rainfall))
    return result


def _rainfall_features(values: list[float], month: int, hour: int) -> dict[str, float]:
    values = ([0.0, 0.0, 0.0] + list(values))[-3:]
    day_1, day_2, day_3 = values[-1], values[-2], values[-3]
    return {
        "rainfall_1h": day_1 / 24.0,
        "rainfall_3h": day_1 / 8.0,
        "rainfall_6h": day_1 / 4.0,
        "rainfall_12h": day_1 / 2.0,
        "rainfall_24h": day_1,
        "rainfall_48h": day_1 + day_2,
        "rainfall_72h": day_1 + day_2 + day_3,
        "rainfall_6h_max": day_1 / 4.0,
        "rainfall_24h_max": max(values),
        "month": month,
        "hour_of_day": hour,
        "is_monsoon": int(month in (6, 7, 8, 9)),
    }


def _river_signal(stations: list[dict]) -> tuple[float, dict]:
    if not stations:
        return 0.0, {"station_count": 0, "danger_stations": 0, "warning_stations": 0, "max_threshold_pressure": 0.0}

    pressures = []
    danger_count = 0
    warning_count = 0
    for station in stations:
        level = _number(station.get("water_level_m"), 0.0)
        warning = _number(station.get("warning_level_m"), 0.0)
        danger = _number(station.get("danger_level_m"), 0.0)
        if danger > warning > 0:
            pressure = max(0.0, min(1.0, (level - warning) / (danger - warning)))
            pressures.append(pressure)
            if level >= danger:
                danger_count += 1
            elif level >= warning:
                warning_count += 1
        else:
            rise = _number(station.get("rise_1h_m"), 0.0)
            pressures.append(max(0.0, min(1.0, 0.5 + rise * 5.0)))

    signal = max(pressures) if pressures else 0.0
    return signal, {
        "station_count": len(stations),
        "danger_stations": danger_count,
        "warning_stations": warning_count,
        "max_threshold_pressure": round(signal, 4),
    }


def build_bihar_district_risk() -> dict:
    model_info = _train_model()
    if not model_info.get("ok"):
        return {"success": False, "error": model_info.get("error", "ML model unavailable")}

    rainfall = _live_bihar_rainfall()
    live = fetch_live_data()
    station_rows = live.get("stations", [])
    stations_by_district: dict[str, list[dict]] = {}
    for station in station_rows:
        district = _normalise_name(station.get("district"))
        if district:
            stations_by_district.setdefault(district, []).append(station)

    now = datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)
    rows = []
    for district, values in sorted(rainfall.items()):
        features = _rainfall_features(values, now.month, now.hour)
        rainfall_probability = float(
            model_info["model"].predict_proba(pd.DataFrame([features], columns=DAILY_FEATURES))[0, 1]
        )
        river_probability, river_meta = _river_signal(stations_by_district.get(district, []))
        # Conservative fusion: an observed warning/danger river signal must not
        # be hidden by a rainfall-only model that lacks Bihar-specific calibration.
        fused_probability = max(rainfall_probability, river_probability)
        if fused_probability >= 0.70:
            risk = "HIGH"
        elif fused_probability >= 0.40:
            risk = "MEDIUM"
        else:
            risk = "LOW"
        rows.append({
            "district": district.title(),
            "flood_probability": round(fused_probability, 4),
            "risk": risk,
            "rainfall_probability": round(rainfall_probability, 4),
            "river_signal": round(river_probability, 4),
            "rainfall_24h_mm": round(features["rainfall_24h"], 2),
            "rainfall_48h_mm": round(features["rainfall_48h"], 2),
            "rainfall_72h_mm": round(features["rainfall_72h"], 2),
            **river_meta,
        })

    return {
        "success": True,
        "region": "Bihar",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "prediction_horizon_hours": 24,
        "model": {
            "type": "RandomForestClassifier",
            "scope": model_info["scope"],
            "bihar_calibrated": model_info["bihar_calibrated"],
            "historical_training_rows": model_info["training_rows"],
            "historical_test_rows": model_info["test_rows"],
            "validation_folds": model_info["validation_folds"],
            "historical_accuracy": model_info["accuracy"],
            "historical_roc_auc": model_info["roc_auc"],
            "warning": "This is not a Bihar-calibrated probability. Add Bihar historical flood outcomes and retrain before treating it as an operational probability.",
        },
        "rainfall_source": RAINFALL_API,
        "river_source": live.get("source_url"),
        "districts": rows,
        "count": len(rows),
    }
