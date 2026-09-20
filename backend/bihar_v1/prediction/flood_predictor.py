"""Inference wrapper for the trained Bihar v1 river-flood model."""
from __future__ import annotations

import math
import os
from pathlib import Path
from typing import Any

import joblib
import pandas as pd

from ..config import BIHAR_V1_DATA_ROOT
from ..schemas import PredictionOutput

DEFAULT_MODEL_DIR = BIHAR_V1_DATA_ROOT / "models"


def model_path(district: str) -> Path:
    district_key = district.strip().lower()
    configured = os.getenv(f"VARSHAGUARD_{district_key.upper()}_FLOOD_MODEL")
    return Path(configured) if configured else DEFAULT_MODEL_DIR / f"{district_key}_flood_xgboost.joblib"


def _model_features(model: Any) -> list[str] | None:
    names = getattr(model, "feature_names_in_", None)
    if names is None:
        return None
    return [str(name) for name in names]


def _prepare_features(model: Any, features: dict[str, Any]) -> pd.DataFrame:
    columns = _model_features(model)
    if not columns:
        raise ValueError("Trained model does not expose feature_names_in_")

    missing = [name for name in columns if name not in features]
    if missing:
        raise ValueError(f"Missing model features: {missing}")

    values = {}
    for name in columns:
        value = features[name]
        try:
            numeric = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Feature {name!r} is not numeric") from exc
        if not math.isfinite(numeric):
            raise ValueError(f"Feature {name!r} must be finite")
        values[name] = numeric

    return pd.DataFrame([values], columns=columns)


def predict(
    district: str,
    features: dict[str, Any],
    *,
    model_file: str | Path | None = None,
) -> PredictionOutput:
    district_key = district.strip().lower()
    path = Path(model_file) if model_file else model_path(district_key)

    if not path.exists():
        return PredictionOutput(
            district=district_key,
            probability=None,
            status="model_not_trained",
            details={
                "model_path": str(path),
                "required": "trained river-flood model",
                "feature_count": len(features),
            },
        )

    manifest_path = path.with_name(f"{path.stem.replace('_xgboost', '')}_model_manifest.json")
    manifest = None
    if manifest_path.exists():
        try:
            import json
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            manifest = None

    try:
        model = joblib.load(path)
        matrix = _prepare_features(model, features)
        probability = float(model.predict_proba(matrix)[0, 1])
    except (OSError, ValueError, TypeError, KeyError, IndexError) as exc:
        return PredictionOutput(
            district=district_key,
            probability=None,
            status="model_error",
            details={
                "model_path": str(path),
                "error": str(exc),
            },
        )

    return PredictionOutput(
        district=district_key,
        probability=probability,
        status="ok",
        details={
            "model_path": str(path),
            "feature_count": len(matrix.columns),
            "features": list(matrix.columns),
            "manifest": manifest,
            "operational_threshold": manifest.get("operational_threshold") if manifest else None,
            "operational_threshold_status": manifest.get("operational_threshold_status") if manifest else "manifest_unavailable",
        },
    )
