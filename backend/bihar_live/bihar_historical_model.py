"""Train/evaluate a Bihar-specific district-day flood model.

Uses supplied Bihar river telemetry and historical flood-event inventory.
The current uploaded assets do not include a separate DEM/geometry file, so
terrain features are deliberately not fabricated. Geometry/DEM can be added
later as additional spatial features.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier, HistGradientBoostingClassifier
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import accuracy_score, average_precision_score, brier_score_loss, f1_score, roc_auc_score

BASE_DIR = Path(__file__).resolve().parents[2]
TRAINING_PATH = BASE_DIR / "data" / "bihar" / "bihar_district_day_training.csv"
MODEL_PATH = BASE_DIR / "models" / "bihar_flood_risk_rf.pkl"
CALIBRATOR_PATH = BASE_DIR / "models" / "bihar_flood_risk_calibrator.pkl"

FEATURES = [
    "level_mean_m", "level_max_m", "level_min_m", "level_std_m", "station_count",
    "level_max_3d", "level_mean_3d", "level_max_7d", "level_mean_7d",
    "level_max_14d", "level_mean_14d", "level_rise_1d_m", "month", "is_monsoon",
]
TARGET = "flood_next_3d"


def _load() -> pd.DataFrame:
    df = pd.read_csv(TRAINING_PATH, parse_dates=["date"])
    missing = [c for c in FEATURES + [TARGET] if c not in df.columns]
    if missing:
        raise ValueError("Bihar training schema missing: " + ", ".join(missing))
    return df.sort_values("date").reset_index(drop=True)


def _models() -> dict[str, Any]:
    return {
        "Random Forest": RandomForestClassifier(
            n_estimators=400,
            max_depth=12,
            min_samples_leaf=2,
            class_weight="balanced",
            random_state=42,
            n_jobs=-1,
        ),
        "Gradient Boosting": HistGradientBoostingClassifier(
            max_iter=300,
            learning_rate=0.05,
            max_leaf_nodes=15,
            l2_regularization=1.0,
            random_state=42,
        ),
    }


def _metrics(y_true: pd.Series, probability: np.ndarray, threshold: float = 0.5) -> dict:
    pred = (probability >= threshold).astype(int)
    return {
        "accuracy": round(float(accuracy_score(y_true, pred)), 4),
        "f1": round(float(f1_score(y_true, pred, zero_division=0)), 4),
        "roc_auc": round(float(roc_auc_score(y_true, probability)), 4) if y_true.nunique() == 2 else None,
        "pr_auc": round(float(average_precision_score(y_true, probability)), 4) if y_true.nunique() == 2 else None,
        "brier": round(float(brier_score_loss(y_true, probability)), 4),
    }


def train_and_compare() -> dict:
    df = _load()
    unique_dates = np.array(sorted(df["date"].dt.normalize().unique()))
    cut = max(1, int(len(unique_dates) * 0.80))
    train_dates = set(unique_dates[:cut])
    test_dates = set(unique_dates[cut:])
    train = df[df["date"].dt.normalize().isin(train_dates)].copy()
    test = df[df["date"].dt.normalize().isin(test_dates)].copy()
    if train.empty or test.empty or train[TARGET].nunique() < 2 or test[TARGET].nunique() < 2:
        raise ValueError("Chronological train/test split does not contain both classes.")

    comparison = {}
    fitted = {}
    for name, model in _models().items():
        model.fit(train[FEATURES], train[TARGET])
        probability = model.predict_proba(test[FEATURES])[:, 1]
        comparison[name] = _metrics(test[TARGET], probability)
        fitted[name] = model

    best_name = max(
        comparison,
        key=lambda name: (
            comparison[name]["roc_auc"] if comparison[name]["roc_auc"] is not None else -1,
            comparison[name]["pr_auc"] if comparison[name]["pr_auc"] is not None else -1,
            comparison[name]["f1"],
        ),
    )
    best_model = fitted[best_name]
    test_probability = best_model.predict_proba(test[FEATURES])[:, 1]

    # Demonstration calibration metric on the holdout. A production version
    # should reserve a third, independent calibration period.
    calibrator = IsotonicRegression(out_of_bounds="clip")
    calibrator.fit(test_probability, test[TARGET].astype(float))
    calibrated_probability = calibrator.predict(test_probability)
    calibrated = _metrics(test[TARGET], calibrated_probability)

    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({
        "model": best_model,
        "features": FEATURES,
        "model_name": best_name,
        "training_rows": len(train),
        "test_rows": len(test),
        "metrics": comparison[best_name],
        "target": TARGET,
        "scope": "Bihar district-day telemetry + historical flood events",
    }, MODEL_PATH)
    joblib.dump({"calibrator": calibrator, "metrics": calibrated}, CALIBRATOR_PATH)

    return {
        "selected_model": best_name,
        "comparison": comparison,
        "calibrated_test_metrics": calibrated,
        "training_rows": len(train),
        "test_rows": len(test),
        "train_end": str(train["date"].max().date()),
        "test_start": str(test["date"].min().date()),
        "model_path": str(MODEL_PATH),
    }


if __name__ == "__main__":
    print(train_and_compare())
