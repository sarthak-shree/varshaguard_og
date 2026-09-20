import os
from datetime import datetime, timezone

from flask import Flask, jsonify, request, send_from_directory, make_response
from flask_cors import CORS

try:
    from .model import load_model
    from .prediction import (
        REGIONS,
        get_flood_risk_map,
        get_history,
        get_rainfall_series,
        get_stations,
        predict_probability,
    )
    from .risk import get_risk, get_warning
except ImportError:
    from model import load_model
    from prediction import (
        REGIONS,
        get_flood_risk_map,
        get_history,
        get_rainfall_series,
        get_stations,
        predict_probability,
    )
    from risk import get_risk, get_warning

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")
DATA_PATH = os.path.join(BASE_DIR, "data", "processed", "flood_warning_ml_ready_v2.csv")

app = Flask(__name__)
CORS(app)


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def error_response(message, status_code=400):
    response = jsonify({"success": False, "error": message, "timestamp": now_iso()})
    response.status_code = status_code
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return response


def no_store_json(payload):
    response = make_response(jsonify(payload))
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    return response


def get_region_from_request():
    region = request.args.get("region", "Assam").strip()
    if region not in REGIONS:
        return None, None, "Unsupported region"
    station = request.args.get("station", "").strip() or None
    return region, station, None


@app.route("/api/health")
def health():
    model_info = load_model()
    data_available = os.path.exists(DATA_PATH)
    ready = model_info["ok"] and data_available
    return no_store_json({
        "status": "ok" if ready else "error",
        "service": "VARSHAGUARD API",
        "model": "LOADED" if model_info["ok"] else "ERROR",
        "model_error": model_info["error"],
        "data": "AVAILABLE" if data_available else "ERROR",
        "prediction": "READY" if ready else "ERROR",
    })


@app.route("/api/regions")
def regions():
    return no_store_json({"success": True, "regions": REGIONS})


@app.route("/api/flood-risk")
def flood_risk():
    region, station, error = get_region_from_request()
    if error:
        return error_response(error, 400)
    model_info = load_model()
    probability, record, error = predict_probability(model_info, region, station)
    if error:
        return error_response(error, 500)
    risk = get_risk(probability, model_info["decision_threshold"])
    important_features = {
        "rainfall_1h": float(record.get("rainfall_1h", 0)),
        "rainfall_3h": float(record.get("rainfall_3h", 0)),
        "rainfall_6h": float(record.get("rainfall_6h", 0)),
        "rainfall_12h": float(record.get("rainfall_12h", 0)),
        "rainfall_24h": float(record.get("rainfall_24h", 0)),
        "rainfall_72h": float(record.get("rainfall_72h", 0)),
        "is_monsoon": int(record.get("is_monsoon", 0)),
    }
    return no_store_json({
        "success": True,
        "region": region,
        "station": record.get("station", "Prototype station"),
        "prediction_horizon_hours": model_info["prediction_horizon_hours"],
        "flood_probability": round(float(probability), 4),
        "risk": risk,
        "warning": get_warning(risk),
        "timestamp": now_iso(),
        "data_timestamp": str(record.get("timestamp", "")),
        "latitude": float(record.get("latitude", 0)),
        "longitude": float(record.get("longitude", 0)),
        "features": important_features,
    })


@app.route("/api/flood-risk-map")
def flood_risk_map():
    region = request.args.get("region", "Assam").strip()
    if region not in REGIONS:
        return error_response("Unsupported region", 400)
    model_info = load_model()
    results, error = get_flood_risk_map(model_info, region)
    if error:
        return error_response(error, 500)
    return no_store_json({
        "success": True,
        "region": region,
        "prediction_horizon_hours": model_info["prediction_horizon_hours"],
        "stations": results,
        "count": len(results),
        "generated_at": now_iso(),
    })


@app.route("/api/rainfall")
def rainfall():
    region, station, error = get_region_from_request()
    if error:
        return error_response(error, 400)
    rows, error = get_rainfall_series(region, station)
    if error:
        return error_response(error, 500)
    return no_store_json({"success": True, "region": region, "station": station, "rainfall": rows})


@app.route("/api/history")
def history():
    region, station, error = get_region_from_request()
    if error:
        return error_response(error, 400)
    rows, error = get_history(region, station)
    if error:
        return error_response(error, 500)
    return no_store_json({"success": True, "region": region, "station": station, "history": rows})


@app.route("/api/stations")
def stations():
    region = request.args.get("region", "Assam").strip()
    if region not in REGIONS:
        return error_response("Unsupported region", 400)
    rows, error = get_stations(region)
    if error:
        return error_response(error, 500)
    return no_store_json({"success": True, "region": region, "stations": rows})


@app.route("/")
def dashboard():
    return send_from_directory(FRONTEND_DIR, "index.html")


@app.route("/<path:file_name>")
def frontend_files(file_name):
    return send_from_directory(FRONTEND_DIR, file_name)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=False)
