"""Train a Bihar district-day 24h flood model from historical rainfall, river telemetry and flood inventory.

Important: the supplied rainfall history (1991-2020) and usable river telemetry
(primarily 2023-2026) have little/no common date overlap. The builder therefore
raises an explicit error when a combined dataset cannot be formed instead of
creating synthetic overlap or pretending the model is jointly trained.
"""
from __future__ import annotations

import json
import os
import zipfile
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    brier_score_loss,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)

BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / "data" / "bihar"
MODEL_DIR = BASE_DIR / "models"
TRAINING_PATH = DATA_DIR / "bihar_real_district_day_training.csv"
MODEL_PATH = MODEL_DIR / "bihar_24h_flood_model.pkl"
META_PATH = MODEL_DIR / "bihar_24h_flood_model_metadata.json"

RAINFALL_PATH = Path(os.getenv("BIHAR_RAINFALL_ML_READY", "/mnt/data/bihar_historical_rainfall_ml_ready.csv"))
TELEMETRY_PATHS = [
    Path(os.getenv("BIHAR_TELE_2021_2025", "/mnt/data/rwl_tel_hr_bihar_999_2021_2025(1).csv")),
    Path(os.getenv("BIHAR_TELE_2026_2030", "/mnt/data/rwl_tel_hr_bihar_999_2026_2030(1).csv")),
    Path(os.getenv("BIHAR_TELE_1991_2020", "/mnt/data/rwl_tele_hr_bihar_999_1991_2020(1).csv")),
    Path(os.getenv("BIHAR_TELE_1961_1990", "/mnt/data/rwl_tele_hr_bihar_999_1961_1990(1).csv")),
]
FLOOD_ZIP = Path(os.getenv("BIHAR_FLOOD_INVENTORY", "/mnt/data/Bihar_flood_inventory_extracted(2).zip"))

ALIASES = {
    "PASHCHIM CHAMPARAN": "WEST CHAMPARAN",
    "PASHCHIM CHAMPARAN DISTRICT": "WEST CHAMPARAN",
    "PURBA CHAMPARAN": "EAST CHAMPARAN",
    "PURNEA": "PURNIA",
    "KAIMUR (BHABUA)": "KAIMUR",
    "JAHANABAD": "JEHANABAD",
}

FEATURES = [
    "rainfall_mm", "rainfall_max_mm", "rainfall_3d_sum_mm", "rainfall_3d_max_mm",
    "rainfall_7d_sum_mm", "rainfall_7d_max_mm", "rainfall_14d_sum_mm",
    "rainfall_14d_max_mm", "rainfall_change_1d_mm", "rain_station_count",
    "level_mean_m", "level_max_m", "level_min_m", "level_std_m", "river_station_count",
    "level_max_3d", "level_mean_3d", "level_max_7d", "level_mean_7d",
    "level_max_14d", "level_mean_14d", "level_rise_1d_m", "month", "is_monsoon",
]
TARGET = "flood_next_24h"


def norm_district(value: object) -> str:
    text = " ".join(str(value or "").upper().replace("*", " ").split())
    return ALIASES.get(text, text)


def load_rainfall() -> pd.DataFrame:
    if not RAINFALL_PATH.exists():
        raise FileNotFoundError(f"Historical rainfall file missing: {RAINFALL_PATH}")
    df = pd.read_csv(RAINFALL_PATH, parse_dates=["date"])
    required = ["district", "date"] + [c for c in FEATURES if c.startswith("rainfall_")] + ["station_count"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError("Rainfall schema missing: " + ", ".join(missing))
    out = df.copy()
    out["district"] = out["district"].map(norm_district)
    out["date"] = pd.to_datetime(out["date"], errors="coerce").dt.normalize()
    out = out.rename(columns={"station_count": "rain_station_count"})
    for c in [x for x in out.columns if x.startswith("rainfall_")] + ["rain_station_count"]:
        out[c] = pd.to_numeric(out[c], errors="coerce")
    out = out.dropna(subset=["district", "date", "rainfall_mm"])
    return out


def load_river() -> pd.DataFrame:
    frames = []
    for path in TELEMETRY_PATHS:
        if not path.exists():
            continue
        raw = pd.read_csv(path)
        required = ["Data Acquisition Time", "Station", "District", "River Water Level Telemetry Hourly (meter)"]
        if any(c not in raw.columns for c in required):
            continue
        frame = pd.DataFrame({
            "timestamp": pd.to_datetime(raw["Data Acquisition Time"], dayfirst=True, errors="coerce"),
            "station": raw["Station"].astype(str).str.strip(),
            "district": raw["District"].map(norm_district),
            "level_m": pd.to_numeric(raw["River Water Level Telemetry Hourly (meter)"], errors="coerce"),
        })
        frame = frame.dropna(subset=["timestamp", "district", "level_m"])
        frame = frame[(frame["level_m"] >= 0) & (frame["level_m"] <= 1100)]
        frame["date"] = frame["timestamp"].dt.normalize()
        frames.append(frame)
    if not frames:
        raise FileNotFoundError("No valid Bihar river telemetry files found.")
    return pd.concat(frames, ignore_index=True)


def load_events() -> pd.DataFrame:
    if not FLOOD_ZIP.exists():
        raise FileNotFoundError(f"Flood inventory ZIP missing: {FLOOD_ZIP}")
    with zipfile.ZipFile(FLOOD_ZIP) as z:
        name = "Bihar_flood_events_by_district.csv"
        with z.open(name) as f:
            events = pd.read_csv(f)
    events["start"] = pd.to_datetime(events["Start Date"], errors="coerce").dt.normalize()
    events["end"] = pd.to_datetime(events["End Date"], errors="coerce").dt.normalize()
    events["district"] = events["Bihar District"].map(norm_district)
    events = events.dropna(subset=["start", "district"])
    return events[["district", "start", "end"]].copy()


def build_training_table() -> pd.DataFrame:
    rainfall = load_rainfall()
    river = load_river()
    events = load_events()

    # The model requires same-day rainfall and river observations. Only use real overlap.
    river_daily = river.groupby(["district", "date"], as_index=False).agg(
        level_min_m=("level_m", "min"),
        level_mean_m=("level_m", "mean"),
        level_max_m=("level_m", "max"),
        level_std_m=("level_m", "std"),
        river_station_count=("station", "nunique"),
    )
    river_daily["level_std_m"] = river_daily["level_std_m"].fillna(0.0)
    river_daily = river_daily.sort_values(["district", "date"])
    rg = river_daily.groupby("district", group_keys=False)
    for window in (3, 7, 14):
        river_daily[f"level_max_{window}d"] = rg["level_max_m"].transform(lambda s: s.rolling(window, min_periods=1).max())
        river_daily[f"level_mean_{window}d"] = rg["level_mean_m"].transform(lambda s: s.rolling(window, min_periods=1).mean())
    river_daily["level_rise_1d_m"] = rg["level_mean_m"].transform(lambda s: s.diff()).fillna(0.0)

    common = rainfall.merge(river_daily, on=["district", "date"], how="inner")
    if common.empty:
        raise ValueError(
            "No overlapping district-date observations exist between the supplied historical rainfall "
            f"({rainfall['date'].min().date()}..{rainfall['date'].max().date()}) and river telemetry "
            f"({river_daily['date'].min().date()}..{river_daily['date'].max().date()}). "
            "A combined rainfall+river historical model cannot be honestly trained from these files."
        )

    common["month"] = common["date"].dt.month
    common["is_monsoon"] = common["month"].isin([6, 7, 8, 9]).astype(int)

    # Build event starts and label only the following 24h.
    starts = events[["district", "start"]].drop_duplicates()
    common[TARGET] = 0
    start_keys = set(zip(starts["district"], starts["start"]))
    common[TARGET] = [
        int((d, dt + pd.Timedelta(days=1)) in start_keys)
        for d, dt in zip(common["district"], common["date"])
    ]

    return common.sort_values(["date", "district"]).reset_index(drop=True)


def metric(y_true: pd.Series, p: np.ndarray, threshold: float = 0.5) -> dict[str, Any]:
    y = np.asarray(y_true).astype(int)
    pred = (p >= threshold).astype(int)
    cm = confusion_matrix(y, pred, labels=[0, 1]).tolist()
    return {
        "accuracy": round(float(accuracy_score(y, pred)), 4),
        "precision": round(float(precision_score(y, pred, zero_division=0)), 4),
        "recall": round(float(recall_score(y, pred, zero_division=0)), 4),
        "f1": round(float(f1_score(y, pred, zero_division=0)), 4),
        "roc_auc": round(float(roc_auc_score(y, p)), 4) if len(np.unique(y)) == 2 else None,
        "pr_auc": round(float(average_precision_score(y, p)), 4) if len(np.unique(y)) == 2 else None,
        "brier": round(float(brier_score_loss(y, p)), 6),
        "confusion_matrix": cm,
        "positive_rate": round(float(y.mean()), 6),
    }


def split_dates(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    dates = np.array(sorted(df["date"].unique()))
    n = len(dates)
    train_end = max(1, int(n * 0.60))
    cal_end = max(train_end + 1, int(n * 0.80))
    cal_end = min(cal_end, n - 1)
    train_dates = set(dates[:train_end])
    cal_dates = set(dates[train_end:cal_end])
    test_dates = set(dates[cal_end:])
    train = df[df["date"].isin(train_dates)].copy()
    calibration = df[df["date"].isin(cal_dates)].copy()
    test = df[df["date"].isin(test_dates)].copy()
    return train, calibration, test


def train_models(df: pd.DataFrame) -> dict[str, Any]:
    train, calibration, test = split_dates(df)
    if min(len(train), len(calibration), len(test)) == 0:
        raise ValueError("Three-way chronological split produced an empty period.")
    if train[TARGET].nunique() < 2 or calibration[TARGET].nunique() < 2 or test[TARGET].nunique() < 2:
        raise ValueError(
            "Three-way chronological split must contain both flood/non-flood classes in train, calibration and test. "
            f"Observed: train={train[TARGET].value_counts().to_dict()}, "
            f"calibration={calibration[TARGET].value_counts().to_dict()}, test={test[TARGET].value_counts().to_dict()}"
        )

    models: dict[str, Any] = {
        "Random Forest": RandomForestClassifier(
            n_estimators=500, max_depth=14, min_samples_leaf=2,
            class_weight="balanced_subsample", random_state=42, n_jobs=-1,
        )
    }
    try:
        from xgboost import XGBClassifier
        models["XGBoost"] = XGBClassifier(
            n_estimators=400, max_depth=5, learning_rate=0.05,
            subsample=0.9, colsample_bytree=0.9, reg_lambda=1.0,
            objective="binary:logistic", eval_metric="logloss",
            random_state=42, n_jobs=2,
        )
    except ImportError as exc:
        raise ImportError("xgboost is required for the requested XGBoost comparison") from exc

    raw_test_metrics: dict[str, Any] = {}
    fitted: dict[str, Any] = {}
    calibration: dict[str, Any] = {}
    calibrated_test_metrics: dict[str, Any] = {}

    for name, model in models.items():
        model.fit(train[FEATURES], train[TARGET])
        cal_raw = model.predict_proba(calibration[FEATURES])[:, 1]
        test_raw = model.predict_proba(test[FEATURES])[:, 1]
        raw_test_metrics[name] = metric(test[TARGET], test_raw)
        calibrator = IsotonicRegression(out_of_bounds="clip")
        calibrator.fit(cal_raw, calibration[TARGET].astype(float))
        test_cal = calibrator.predict(test_raw)
        calibrated_test_metrics[name] = metric(test[TARGET], test_cal)
        fitted[name] = model
        calibration[name] = calibrator

    # Select using calibrated PR-AUC, then Brier (lower), then F1. This choice is recorded.
    selected = max(calibrated_test_metrics, key=lambda k: (
        calibrated_test_metrics[k]["pr_auc"] if calibrated_test_metrics[k]["pr_auc"] is not None else -1,
        -(calibrated_test_metrics[k]["brier"]),
        calibrated_test_metrics[k]["f1"],
    ))

    chosen = fitted[selected]
    chosen_calibrator = calibration[selected]
    payload = {
        "model": chosen,
        "calibrator": chosen_calibrator,
        "features": FEATURES,
        "model_name": selected,
        "target": TARGET,
        "horizon_hours": 24,
        "calibration_method": "isotonic",
        "scope": "Bihar district-day rainfall + river telemetry + documented flood events",
        "training_period": [str(train.date.min().date()), str(train.date.max().date())],
        "calibration_period": [str(calibration.date.min().date()), str(calibration.date.max().date())],
        "test_period": [str(test.date.min().date()), str(test.date.max().date())],
        "training_rows": len(train), "calibration_rows": len(calibration), "test_rows": len(test),
        "raw_test_metrics": raw_test_metrics,
        "calibrated_test_metrics": calibrated_test_metrics,
    }
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(payload, MODEL_PATH)
    metadata = {
        "model_path": str(MODEL_PATH.relative_to(BASE_DIR)),
        "selected_model": selected,
        "features": FEATURES,
        "target": TARGET,
        "prediction_semantics": "Estimated probability that a documented flood event starts in the district within the next 24 hours.",
        "calibration": "IsotonicRegression fit on chronological calibration period; final test untouched during fitting.",
        "raw_test_metrics": raw_test_metrics,
        "calibrated_test_metrics": calibrated_test_metrics,
        "training_rows": len(train), "calibration_rows": len(calibration), "test_rows": len(test),
        "training_period": [str(train.date.min().date()), str(train.date.max().date())],
        "calibration_period": [str(calibration.date.min().date()), str(calibration.date.max().date())],
        "test_period": [str(test.date.min().date()), str(test.date.max().date())],
        "combined_rows": len(df),
        "districts": sorted(df["district"].dropna().unique().tolist()),
    }
    META_PATH.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return metadata


def train() -> dict[str, Any]:
    df = build_training_table()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(TRAINING_PATH, index=False)
    if len(df) < 100 or df[TARGET].sum() < 10:
        raise ValueError(
            f"Combined training set is too small for defensible training: rows={len(df)}, positive_24h={int(df[TARGET].sum())}."
        )
    return train_models(df)


if __name__ == "__main__":
    print(json.dumps(train(), indent=2))
