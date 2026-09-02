import os
from datetime import datetime

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

try:
    from .model import load_model
    from .prediction import REGIONS, get_history, get_rainfall_series, get_stations, predict_probability
    from .risk import get_risk, get_warning
except ImportError:
    from model import load_model
    from prediction import REGIONS, get_history, get_rainfall_series, get_stations, predict_probability
    from risk import get_risk, get_warning


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")

app = Flask(__name__)
CORS(app)


def error_response(message, status_code=400):
    """Return errors as JSON, not ugly Python tracebacks."""
    return jsonify({
        "success": False,
        "error": message,
        "timestamp": datetime.now().isoformat(),
    }), status_code


def get_region_from_request():
    region = request.args.get("region", "Assam").strip()

    if region not in REGIONS:
        return None, None, "Unsupported region"

    station = request.args.get("station", "").strip()

    return region, station or None, None


@app.route("/api/health")
def health():
    model_info = load_model()

    return jsonify({
        "status": "ok",
        "service": "VARSHAGUARD API",
        "model": "LOADED" if model_info["ok"] else "ERROR",
        "model_error": model_info["error"],
        "data": "AVAILABLE",
        "prediction": "READY" if model_info["ok"] else "ERROR",
    })


@app.route("/api/regions")
def regions():
    return jsonify({
        "success": True,
        "regions": REGIONS,
    })


@app.route("/api/flood-risk")
@app.route("/api/flood-risk")
def flood_risk():
    region, station, error = get_region_from_request()

    if error:
        return error_response(error, 400)

    model_info = load_model()

    probability, record, error = predict_probability(
        model_info,
        region,
        station
    )

    if error:
        return error_response(error, 500)
    risk = get_risk(
    probability,
    model_info["decision_threshold"]
)

    important_features = {
        "rainfall_1h": float(record.get("rainfall_1h", 0)),
        "rainfall_3h": float(record.get("rainfall_3h", 0)),
        "rainfall_6h": float(record.get("rainfall_6h", 0)),
        "rainfall_12h": float(record.get("rainfall_12h", 0)),
        "rainfall_24h": float(record.get("rainfall_24h", 0)),
        "rainfall_72h": float(record.get("rainfall_72h", 0)),
        "is_monsoon": int(record.get("is_monsoon", 0)),
    }

    return jsonify({
        "success": True,
        "region": region,
        "station": record.get("station", "Prototype station"),
        "prediction_horizon_hours": model_info["prediction_horizon_hours"],
        "flood_probability": round(probability, 4),
        "risk": risk,
        "warning": get_warning(risk),
        "timestamp": datetime.now().isoformat(),
        "data_timestamp": str(record.get("timestamp", "")),
        "latitude": float(record.get("latitude", 0)),
        "longitude": float(record.get("longitude", 0)),
        "features": important_features,
    })


@app.route("/api/rainfall")
def rainfall():
    region, station, error = get_region_from_request()
    if error:
        return error_response(error, 400)

    rows, error = get_rainfall_series(region)
    if error:
        return error_response(error, 500)

    return jsonify({
        "success": True,
        "region": region,
        "rainfall": rows,
    })


@app.route("/api/history")
def history():
    region, station, error = get_region_from_request()
    if error:
        return error_response(error, 400)

    rows, error = get_history(region)
    if error:
        return error_response(error, 500)

    return jsonify({
        "success": True,
        "region": region,
        "history": rows,
    })


@app.route("/api/stations")
def stations():
    region, station, error = get_region_from_request()
    if error:
        return error_response(error, 400)

    rows, error = get_stations(region)
    if error:
        return error_response(error, 500)

    return jsonify({
        "success": True,
        "region": region,
        "stations": rows,
    })


@app.route("/")
def dashboard():
    """Show the dashboard when someone opens the Vercel site."""
    return send_from_directory(FRONTEND_DIR, "index.html")


@app.route("/<path:file_name>")
def frontend_files(file_name):
    """Serve CSS, JavaScript, and other frontend files."""
    file_path = os.path.join(FRONTEND_DIR, file_name)

    if os.path.exists(file_path):
        return send_from_directory(FRONTEND_DIR, file_name)

    return send_from_directory(FRONTEND_DIR, "index.html")


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5001, debug=True)
