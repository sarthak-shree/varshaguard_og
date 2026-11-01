import json

from flask import Blueprint, jsonify, request

from .config import BIHAR_V1_DATA_ROOT, PREDICTION_HORIZON_HOURS, SUPPORTED_DISTRICTS, district
from .prediction.flood_predictor import (
    LIVE_CWC_SOURCE,
    LIVE_CWC_TARGET,
    model_path,
    predict as predict_flood,
    uses_live_cwc,
)
from .prediction.inundation_predictor import predict as predict_inundation
from .prediction.rainfall_predictor import predict as predict_rainfall
from .services.alert_engine import build_alert
from .services.risk_fusion import fuse

bp = Blueprint("bihar_v1", __name__, url_prefix="/api/bihar/v1")

def _load_model_readiness(slug: str) -> dict:
    path = BIHAR_V1_DATA_ROOT / "processed" / "dataset_audit.json"
    if not path.exists():
        return {"status": "audit_unavailable", "models": {}}
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
        readiness = report.get("districts", {}).get(slug, {}).get("model_readiness")
        if not isinstance(readiness, dict):
            return {"status": "audit_missing_model_readiness", "models": {}}
        return readiness
    except (OSError, ValueError, TypeError):
        return {"status": "audit_unavailable", "models": {}}


def _district_or_404(slug: str):
    try:
        return district(slug), None
    except ValueError as exc:
        return None, (jsonify({"success": False, "error": str(exc)}), 404)


@bp.get("/health")
def health():
    return jsonify({
        "success": True,
        "service": "VarshaGuard Bihar v1",
        "status": "scaffold",
        "supported_districts": list(SUPPORTED_DISTRICTS),
        "prediction_horizon_hours": PREDICTION_HORIZON_HOURS,
    })


@bp.get("/districts")
def districts():
    return jsonify({"success": True, "districts": list(SUPPORTED_DISTRICTS.values())})


@bp.get("/<slug>/status")
def status(slug: str):
    info, error = _district_or_404(slug)
    if error:
        return error

    flood_model = model_path(info["slug"])
    manifest_path = flood_model.with_name(
        f"{flood_model.stem.replace('_xgboost', '')}_model_manifest.json"
    )
    calibration_status = "not_calibrated"
    operational_threshold = None
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            calibration_status = manifest.get(
                "operational_threshold_status", "not_calibrated"
            )
            operational_threshold = manifest.get("operational_threshold")
        except (OSError, ValueError):
            calibration_status = "manifest_unavailable"

    model_readiness = _load_model_readiness(info["slug"])

    # Same decision the forecast endpoint makes, so the two cannot disagree.
    live_flood = uses_live_cwc(info["slug"])
    if flood_model.exists():
        flood_status = "trained_artifact_available"
    elif live_flood:
        flood_status = "live_cwc_research_model"
    else:
        flood_status = "model_not_trained"

    return jsonify({
        "success": True,
        "district": info,
        "horizon_hours": PREDICTION_HORIZON_HOURS,
        "model_readiness": model_readiness,
        "models": {
            "rainfall": {"status": "model_not_trained"},
            "flood": {
                "status": flood_status,
                "artifact_available": flood_model.exists(),
                "source": LIVE_CWC_SOURCE if live_flood else None,
                "target": LIVE_CWC_TARGET if live_flood else None,
                "operational_threshold": operational_threshold,
                "operational_threshold_status": calibration_status,
            },
            "inundation": {"status": "model_not_trained"},
        },
        "data_feeds": {
            "live_observations": "cwc_ffs_research_feed" if live_flood else "not_connected",
            "status": "not_ready",
        },
        "operational_risk": "not_ready",
    })


@bp.get("/<slug>/forecast")
def forecast(slug: str):
    info, error = _district_or_404(slug)
    if error:
        return error
    features = request.args.to_dict(flat=True)
    rainfall = predict_rainfall(info["slug"], features)
    flood = predict_flood(info["slug"], features)
    inundation = predict_inundation(info["slug"], features)
    risk = fuse(info["slug"], rainfall.probability, flood.probability, inundation.probability)
    response = jsonify({
        "success": True,
        "district": info,
        "horizon_hours": PREDICTION_HORIZON_HOURS,
        "rainfall": rainfall.to_dict(),
        "flood": flood.to_dict(),
        "inundation": inundation.to_dict(),
        "risk": risk.to_dict(),
        "alert": build_alert(risk),
    })
    # Live flood data must never be served from a browser or proxy cache.
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return response


@bp.get("/<slug>/current")
def current(slug: str):
    info, error = _district_or_404(slug)
    if error:
        return error
    return jsonify({
        "success": True,
        "district": info,
        "status": "data_pipeline_not_connected",
        "message": "Connect verified IMD/CWC/IMERG feeds before exposing live observations.",
    })


@bp.get("/<slug>/inundation")
def inundation(slug: str):
    info, error = _district_or_404(slug)
    if error:
        return error
    return jsonify({
        "success": True,
        "district": info,
        "status": "model_not_trained",
        "horizon_hours": PREDICTION_HORIZON_HOURS,
    })


@bp.get("/alerts")
def alerts():
    return jsonify({"success": True, "alerts": [], "status": "not_ready"})
