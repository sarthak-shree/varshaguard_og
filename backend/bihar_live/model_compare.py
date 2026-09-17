"""Evaluate Bihar flood models and write comparison metadata.

Current supported tabular candidates are Random Forest and Histogram Gradient
Boosting. The repository does not add XGBoost as a dependency until that
external library is explicitly needed.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.metrics import accuracy_score, average_precision_score, brier_score_loss, f1_score, roc_auc_score

TRAINING_PATH = Path(__file__).resolve().parents[2] / "data" / "bihar" / "bihar_district_day_training.csv"
MODEL_DIR = Path(__file__).resolve().parents[2] / "models"
FEATURES = [
    "level_mean_m", "level_max_m", "level_min_m", "level_std_m", "station_count",
    "level_max_3d", "level_mean_3d", "level_max_7d", "level_mean_7d",
    "level_max_14d", "level_mean_14d", "level_rise_1d_m", "month", "is_monsoon",
]
TARGET = "flood_next_3d"


def metric_row(y: pd.Series, p: np.ndarray) -> dict:
    pred = (p >= 0.5).astype(int)
    return {
        "accuracy": round(float(accuracy_score(y, pred)), 4),
        "f1": round(float(f1_score(y, pred, zero_division=0)), 4),
        "roc_auc": round(float(roc_auc_score(y, p)), 4) if y.nunique() == 2 else None,
        "pr_auc": round(float(average_precision_score(y, p)), 4) if y.nunique() == 2 else None,
        "brier": round(float(brier_score_loss(y, p)), 4),
    }


def compare() -> dict:
    df = pd.read_csv(TRAINING_PATH, parse_dates=["date"]).sort_values("date")
    dates = np.array(sorted(df["date"].dt.normalize().unique()))
    cut = max(1, int(len(dates) * 0.80))
    train = df[df["date"].dt.normalize().isin(set(dates[:cut]))].copy()
    test = df[df["date"].dt.normalize().isin(set(dates[cut:]))].copy()
    if train[TARGET].nunique() < 2 or test[TARGET].nunique() < 2:
        raise ValueError("Both chronological train and test periods must contain both target classes.")

    candidates: dict[str, Any] = {
        "Random Forest": RandomForestClassifier(n_estimators=400, max_depth=12, min_samples_leaf=2, class_weight="balanced", random_state=42, n_jobs=-1),
        "Gradient Boosting": HistGradientBoostingClassifier(max_iter=300, learning_rate=0.05, max_leaf_nodes=15, l2_regularization=1.0, random_state=42),
    }
    metrics = {}
    fitted = {}
    for name, model in candidates.items():
        model.fit(train[FEATURES], train[TARGET])
        probability = model.predict_proba(test[FEATURES])[:, 1]
        metrics[name] = metric_row(test[TARGET], probability)
        fitted[name] = model

    # Prefer ROC-AUC, then PR-AUC, then F1. This ranking is only for model selection;
    # operational use still requires validation and calibration checks.
    selected = max(metrics, key=lambda k: (
        metrics[k]["roc_auc"] if metrics[k]["roc_auc"] is not None else -1,
        metrics[k]["pr_auc"] if metrics[k]["pr_auc"] is not None else -1,
        metrics[k]["f1"],
    ))
    model = fitted[selected]
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump({"model": model, "features": FEATURES, "model_name": selected, "target": TARGET, "metrics": metrics[selected]}, MODEL_DIR / "bihar_flood_risk_model.pkl")
    return {"selected_model": selected, "comparison": metrics, "train_rows": len(train), "test_rows": len(test), "train_end": str(train.date.max().date()), "test_start": str(test.date.min().date())}


if __name__ == "__main__":
    print(compare())
