"""Inference wrapper for the trained Bihar v1 river-flood model."""
from __future__ import annotations

import hashlib
import math
import os
from pathlib import Path
from typing import Any

import joblib
import pandas as pd

from ..config import BIHAR_V1_DATA_ROOT
from ..schemas import PredictionOutput, utc_now

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


def _validate_manifest(manifest: dict[str, Any], district: str, model_features: list[str]) -> None:
    if manifest.get("district") != district:
        raise ValueError("Model manifest district does not match requested district")
    if manifest.get("model_type") != "xgboost_binary_classifier":
        raise ValueError("Unsupported model manifest type")
    if manifest.get("target") != "flood_event_start_next_24h":
        raise ValueError("Model manifest target is incompatible with Bihar v1 flood inference")
    if manifest.get("horizon_hours") != 24:
        raise ValueError("Model manifest horizon is not 24 hours")
    manifest_features = manifest.get("feature_columns")
    if manifest_features is not None and [str(x) for x in manifest_features] != model_features:
        raise ValueError("Model manifest feature schema does not match model artifact")


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


LIVE_CWC_SOURCE = "cwc_gauge_24h_research_model"
LIVE_CWC_TARGET = (
    "Estimated chance that the district's CWC river gauge reaches its published "
    "warning level in the 24 hours after the latest accepted stage reading. This is "
    "a gauge threshold-crossing estimate, not a flood-event, neighbourhood "
    "inundation, or flood-depth probability."
)
# Live CWC statuses that carry no model probability, mapped to the v1 status
# vocabulary. Anything not listed here is reported as "unavailable".
_LIVE_STATUS_MAP = {
    "predicted": "ok",
    "warning_level_reached": "observed_threshold_reached",
    "danger_level_reached": "observed_threshold_reached",
    "stale": "stale",
    "insufficient_inputs": "insufficient_inputs",
    "model_error": "model_error",
}
_LIVE_DETAIL_KEYS = (
    "station_code",
    "station_name",
    "observed_at_ist",
    "forecast_end_ist",
    "data_age_hours",
    "current_stage_m",
    "warning_level_m",
    "danger_level_m",
    "margin_to_warning_m",
    "margin_to_danger_m",
    "rainfall_24h_mm",
    "decision_threshold",
    "feature_coverage",
    "local_validation_note",
    "message",
)


def _live_cwc_module():
    """Import the live CWC inference module under either package layout."""
    try:
        from backend.bihar_live.research import live_prediction
    except ImportError:  # `python backend/app.py` puts backend/ itself on sys.path
        from bihar_live.research import live_prediction
    return live_prediction


def live_cwc_model_available() -> bool:
    """True when the checked-in CWC research model files are present (no network)."""
    try:
        module = _live_cwc_module()
    except ImportError:
        return False
    return module.MODEL_PATH.is_file() and module.METADATA_PATH.is_file()


def uses_live_cwc(district: str, model_file: str | Path | None = None) -> bool:
    """Whether a flood forecast for this district is served by the live CWC model.

    The single decision used by both ``predict`` and the v1 ``/status`` endpoint so
    they cannot disagree. A v1 artifact always wins, and a deployment that
    configured a v1 model path never silently falls back to another model.
    """
    if model_file is not None:
        return False
    district_key = district.strip().lower()
    if model_path(district_key).exists():
        return False
    if os.getenv(f"VARSHAGUARD_{district_key.upper()}_FLOOD_MODEL"):
        return False
    return live_cwc_model_available()


def _live_unavailable(district_key: str, status: str, message: str) -> PredictionOutput:
    return PredictionOutput(
        district=district_key,
        probability=None,
        status=status,
        source=LIVE_CWC_SOURCE,
        details={
            "target_definition": LIVE_CWC_TARGET,
            "message": message,
            "research_only": True,
            "operational": False,
        },
    )


def predict_live_cwc(district: str) -> PredictionOutput:
    """Flood estimate from the live CWC gauge model, failing closed on any gap.

    A probability is returned only when the live model actually produced one for
    this district's gauge. An already-observed warning/danger crossing, stale or
    incomplete inputs, and any feed or model failure yield ``probability=None``.
    """
    district_key = district.strip().lower()
    try:
        payload = _live_cwc_module().get_live_predictions()
    except Exception:  # the live path must never break the forecast endpoint
        return _live_unavailable(
            district_key, "unavailable", "The live CWC flood model could not be run."
        )

    prediction = next(
        (
            item
            for item in payload.get("predictions", [])
            if str(item.get("district", "")).strip().lower() == district_key
        ),
        None,
    )
    if not payload.get("available") or prediction is None:
        return _live_unavailable(
            district_key,
            "unavailable",
            payload.get("error") or "Current CWC readings or model inputs are unavailable.",
        )

    live_status = prediction.get("status")
    status = _LIVE_STATUS_MAP.get(live_status, "unavailable")
    probability = None
    if status == "ok":
        raw = prediction.get("model_probability")
        if (
            prediction.get("risk_basis") == "model_probability"
            and isinstance(raw, (int, float))
            and not isinstance(raw, bool)
            and math.isfinite(raw)
            and 0.0 <= raw <= 1.0
        ):
            probability = float(raw)
        else:
            status = "model_error"

    details: dict[str, Any] = {
        key: prediction[key] for key in _LIVE_DETAIL_KEYS if prediction.get(key) is not None
    }
    details.update(
        {
            "target_definition": LIVE_CWC_TARGET,
            "live_status": live_status,
            "dashboard_band": prediction.get("risk_level") if status == "ok" else None,
            "model_name": payload.get("model_name"),
            "model_type": payload.get("model_type"),
            "validation": payload.get("validation"),
            "limitations": payload.get("limitations", []),
            "research_only": True,
            "operational": False,
            "operational_threshold_status": "not_calibrated",
        }
    )
    return PredictionOutput(
        district=district_key,
        probability=probability,
        status=status,
        source=LIVE_CWC_SOURCE,
        generated_at=payload.get("generated_at_ist") or utc_now(),
        details=details,
    )


def predict(
    district: str,
    features: dict[str, Any],
    *,
    model_file: str | Path | None = None,
) -> PredictionOutput:
    district_key = district.strip().lower()
    path = Path(model_file) if model_file else model_path(district_key)

    if not path.exists():
        # No v1 river-flood artifact is checked in; use the live CWC gauge model
        # unless a deployment explicitly configured a v1 model path.
        if uses_live_cwc(district_key, model_file):
            return predict_live_cwc(district_key)
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
        expected_sha256 = manifest.get("model_sha256") if manifest else None
        if expected_sha256:
            actual_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
            if actual_sha256 != expected_sha256:
                raise ValueError("Model artifact checksum does not match manifest")
        model = joblib.load(path)
        model_features = _model_features(model)
        if manifest is not None:
            _validate_manifest(manifest, district_key, model_features or [])
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
