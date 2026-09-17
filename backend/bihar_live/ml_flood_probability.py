"""Bihar-specific 24-hour flood probability model.

This module only emits a probability when a trained, validated model artifact
exists. It never converts a heuristic score into an ML probability.

Training data contract:
    timestamp, station, district, river, water_level_m,
    warning_level_m, danger_level_m, water_level_1h_before_m,
    rainfall_1h_mm, rainfall_3h_mm, rainfall_6h_mm,
    rainfall_12h_mm, rainfall_24h_mm, flood_soon_24h

`flood_soon_24h` must be constructed from information available strictly after
the feature timestamp. Training must be chronological, not randomly split.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any
import joblib
import numpy as np

MODEL_PATH = Path(__file__).resolve().parent / "models" / "bihar_flood_probability.joblib"
FEATURES = [
    "water_level_m", "warning_level_m", "danger_level_m",
    "water_level_1h_before_m", "rise_1h_m",
    "level_vs_warning", "level_vs_danger",
    "rainfall_1h_mm", "rainfall_3h_mm", "rainfall_6h_mm",
    "rainfall_12h_mm", "rainfall_24h_mm",
]


def load_model() -> Any | None:
    if not MODEL_PATH.exists():
        return None
    return joblib.load(MODEL_PATH)


def build_features(record: dict) -> dict[str, float]:
    level = float(record.get("water_level_m") or 0.0)
    warning = float(record.get("warning_level_m") or 0.0)
    danger = float(record.get("danger_level_m") or 0.0)
    previous = record.get("water_level_1h_before_m")
    previous = float(previous) if previous is not None else level
    rise = level - previous
    return {
        "water_level_m": level,
        "warning_level_m": warning,
        "danger_level_m": danger,
        "water_level_1h_before_m": previous,
        "rise_1h_m": rise,
        "level_vs_warning": (level - warning) if warning else 0.0,
        "level_vs_danger": (level - danger) if danger else 0.0,
        "rainfall_1h_mm": float(record.get("rainfall_1h_mm") or 0.0),
        "rainfall_3h_mm": float(record.get("rainfall_3h_mm") or 0.0),
        "rainfall_6h_mm": float(record.get("rainfall_6h_mm") or 0.0),
        "rainfall_12h_mm": float(record.get("rainfall_12h_mm") or 0.0),
        "rainfall_24h_mm": float(record.get("rainfall_24h_mm") or 0.0),
    }


def predict(record: dict) -> dict:
    model = load_model()
    if model is None:
        return {
            "available": False,
            "probability": None,
            "model_status": "not_trained",
            "message": "Bihar ML flood model is not trained yet. No heuristic value is reported as an ML probability.",
        }
    features = build_features(record)
    x = np.array([[features[name] for name in FEATURES]], dtype=float)
    probability = float(model.predict_proba(x)[0, 1])
    probability = max(0.0, min(1.0, probability))
    return {
        "available": True,
        "probability": probability,
        "model_status": "validated_artifact",
        "model_version": getattr(model, "model_version", "bihar-24h-v1"),
        "features": features,
    }
