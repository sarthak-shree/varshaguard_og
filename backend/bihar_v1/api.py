"""Flask blueprint for the Bihar v1 API."""
from flask import Blueprint, jsonify, request

from .config import PREDICTION_HORIZON_HOURS, SUPPORTED_DISTRICTS, district
from .prediction.flood_predictor import predict as predict_flood
from .prediction.inundation_predictor import predict as predict_inundation
from .prediction.rainfall_predictor import predict as predict_rainfall
from .services.alert_engine import build_alert
from .services.risk_fusion import fuse

bp = Blueprint("bihar_v1", __name__, url_prefix="/api/bihar/v1")


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
    return jsonify({
        "success": True,
        "district": info,
        "horizon_hours": PREDICTION_HORIZON_HOURS,
        "rainfall": rainfall.to_dict(),
        "flood": flood.to_dict(),
        "inundation": inundation.to_dict(),
        "risk": risk.to_dict(),
        "alert": build_alert(risk),
    })


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
