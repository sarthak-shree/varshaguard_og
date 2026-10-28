"""Bihar Live API for gauge data, research inference, and prototype baselines."""
from flask import Blueprint, jsonify, request

from .config import DATA_MODE, PREDICTION_HORIZON_HOURS, SUPPORTED_DISTRICTS
from .adapters.sources import build_adapters
from .synthetic import generate_observations
from .fusion import fuse, weights_for_lead
from .models.training import train_evaluate

bp = Blueprint("bihar_live", __name__, url_prefix="/api/bihar-live")


@bp.get("/health")
def health():
    return jsonify({
        "success": True,
        "project": "JalDrishti",
        "mode": DATA_MODE,
        "badge": "Synthetic demo data" if DATA_MODE == "synthetic" else "Real-source mode; verify adapter configuration",
        "operational": False,
        "horizon_hours": PREDICTION_HORIZON_HOURS,
        "districts": list(SUPPORTED_DISTRICTS),
    })


@bp.get("/sources")
def sources():
    adapters = build_adapters(DATA_MODE)
    return jsonify({
        "success": True,
        "mode": DATA_MODE,
        "sources": [
            {
                "name": name,
                "status": "synthetic_ready" if DATA_MODE == "synthetic" else "not_configured",
                "description": getattr(adapter, "description", "Synthetic demo adapter"),
            }
            for name, adapter in adapters.items()
        ],
    })


@bp.get("/fusion")
def fusion():
    lead = int(request.args.get("lead", 3))
    values = {"radar": 20.0, "satellite": 18.0, "observations": 16.0, "nwp": 14.0}
    return jsonify({
        "success": True,
        "mode": "synthetic_demo",
        "badge": "Fixed demonstration values; not live radar, satellite, observations, or NWP",
        "source_status": "not_integrated",
        "operational": False,
        "lead_hours": lead,
        **fuse(values, lead),
    })


@bp.get("/model/live")
def live_model():
    # Load the CWC connection only when this live endpoint is requested.
    from .research.live_prediction import get_live_predictions

    return jsonify(get_live_predictions())


@bp.get("/probability")
def probability():
    """Return only a supported 24-hour probability summary for the frontend."""
    district = request.args.get("district", "patna").strip().lower()
    forecast_type = request.args.get("type", "flood").strip().lower()
    if district not in SUPPORTED_DISTRICTS:
        return jsonify({"success": False, "error": "Choose Patna or Muzaffarpur."}), 400
    if forecast_type not in {"flood", "heavy_rainfall"}:
        return jsonify({"success": False, "error": "Choose flood or heavy_rainfall."}), 400

    if forecast_type == "heavy_rainfall":
        response = jsonify({
            "success": True,
            "available": False,
            "type": forecast_type,
            "district": district,
            "horizon_hours": 24,
            "probability_percent": None,
            "status": "model_not_available",
            "message": "A validated heavy-rainfall probability model is not yet available.",
            "operational": False,
        })
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        return response

    from .research.live_prediction import get_live_predictions

    payload = get_live_predictions()
    prediction = next(
        (item for item in payload.get("predictions", [])
         if str(item.get("district", "")).strip().lower() == district),
        None,
    )
    if not payload.get("available") or prediction is None:
        summary = {
            "success": True, "available": False, "type": forecast_type,
            "district": district, "horizon_hours": 24,
            "probability_percent": None, "status": "unavailable",
            "message": payload.get("error", "Current CWC readings or model inputs are unavailable."),
            "operational": False,
        }
    else:
        status = prediction.get("status")
        is_model_probability = status == "predicted" and prediction.get("risk_basis") == "model_probability"
        summary = {
            "success": True,
            "available": bool(is_model_probability),
            "type": forecast_type,
            "district": district,
            "location": prediction.get("station_name"),
            "horizon_hours": 24,
            "probability_percent": prediction.get("risk_percentage") if is_model_probability else None,
            "status": status or "unavailable",
            "observed_threshold_reached": status in {"warning_level_reached", "danger_level_reached"},
            "forecast_end_ist": prediction.get("forecast_end_ist"),
            "observed_at_ist": prediction.get("observed_at_ist"),
            "source": "Central Water Commission Flood Forecasting System",
            "message": prediction.get("message", "No validated probability is available for this reading."),
            "operational": False,
            "target_definition": "Estimated chance the selected CWC gauge reaches its published warning level in the 24 hours after the latest accepted reading; not neighborhood inundation probability.",
        }
    response = jsonify(summary)
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return response


@bp.get("/weather")
def public_weather():
    """Return public forecast-rain context for a supported CWC focus gauge."""
    district = request.args.get("district", "patna").strip().lower()
    if district not in SUPPORTED_DISTRICTS:
        return jsonify({"success": False, "error": "Choose Patna or Muzaffarpur."}), 400

    from .public_weather import get_rainfall_forecast

    response = jsonify(get_rainfall_forecast(district))
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return response


@bp.get("/flood-discharge")
def flood_discharge():
    """Return Open-Meteo daily discharge context, separate from model probability."""
    district = request.args.get("district", "patna").strip().lower()
    if district not in SUPPORTED_DISTRICTS:
        return jsonify({"success": False, "error": "Choose Patna or Muzaffarpur."}), 400

    from .open_meteo_flood import get_river_discharge_forecast

    response = jsonify(get_river_discharge_forecast(district))
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return response


@bp.get("/model/evaluation")
def evaluation():
    rows = generate_observations(hours=96, seed=26071)
    model, metrics = train_evaluate(rows)
    return jsonify({
        "success": True,
        "model": "synthetic_rainfall_baseline",
        "mode": "synthetic_demo",
        "badge": "Synthetic evaluation only; not evidence for the live CWC gauge model",
        "operational": False,
        "backend": model.backend,
        **metrics,
    })
