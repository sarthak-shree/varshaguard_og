"""Separate Flask API for VARSHAGUARD Bihar Live v0.3.0."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
import time

from dotenv import load_dotenv
from flask import Flask, jsonify, request
from flask_cors import CORS


# Local development keeps Neon credentials in the ignored .env.local file.
# Deployed environments should provide DATABASE_URL through their environment.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env.local")

try:
    from .ingest import fetch_live_river_observations
    from .processing import process_river_records
except ImportError:
    from ingest import fetch_live_river_observations
    from processing import process_river_records


app = Flask(__name__)
CORS(app)

CACHE_TTL_SECONDS = 300
_cache = {"payload": None, "expires_at": 0.0}
_cache_lock = Lock()


def _error_response(message: str, status_code: int = 500):
    return jsonify(
        {
            "success": False,
            "error": message,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    ), status_code


def _get_live_payload(force_refresh: bool = False) -> dict:
    now = time.monotonic()
    with _cache_lock:
        if not force_refresh and _cache["payload"] is not None and now < _cache["expires_at"]:
            payload = dict(_cache["payload"])
            payload["cached"] = True
            return payload

    payload = fetch_live_river_observations()
    with _cache_lock:
        _cache["payload"] = payload
        _cache["expires_at"] = time.monotonic() + CACHE_TTL_SECONDS

    payload = dict(payload)
    payload["cached"] = False
    return payload


def _filter_district(records: list[dict], district: str) -> list[dict]:
    if not district:
        return records
    target = district.strip().casefold()
    return [row for row in records if str(row.get("district") or "").strip().casefold() == target]


def _repository():
    from .postgres import PostgreSQLRiverObservationRepository
    return PostgreSQLRiverObservationRepository.from_env()


def _serialize_observation(item) -> dict:
    return {
        "river": item.river,
        "station": item.station,
        "district": item.district,
        "observed_at": item.observed_at.isoformat() if item.observed_at else None,
        "water_level_m": item.water_level_m,
        "warning_level_m": item.warning_level_m,
        "danger_level_m": item.danger_level_m,
        "hfl_m": item.hfl_m,
        "trend": item.trend,
        "water_level_1h_before_m": item.water_level_1h_before_m,
        "fetched_at": item.fetched_at.isoformat() if item.fetched_at else None,
    }


@app.get("/api/bihar/health")
def health():
    return jsonify(
        {
            "success": True,
            "service": "VARSHAGUARD Bihar Live API",
            "version": "0.3.0",
            "layer": "1.4",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    )


@app.get("/api/bihar/live-rivers")
def live_rivers():
    force_refresh = request.args.get("refresh", "false").lower() == "true"
    district = request.args.get("district", "").strip().lower()

    try:
        payload = _get_live_payload(force_refresh=force_refresh)
    except Exception as exc:
        return _error_response(f"Live Bihar river data fetch failed: {exc}", 502)

    records = _filter_district(payload["records"], district)

    return jsonify(
        {
            **payload,
            "records": records,
            "count": len(records),
            "district_filter": district or None,
        }
    )


@app.get("/api/bihar/processed-rivers")
def processed_rivers():
    force_refresh = request.args.get("refresh", "false").lower() == "true"
    district = request.args.get("district", "").strip().lower()

    try:
        payload = _get_live_payload(force_refresh=force_refresh)
        records = process_river_records(payload["records"])
        records = _filter_district(records, district)
    except Exception as exc:
        return _error_response(f"Bihar river processing failed: {exc}", 502)

    return jsonify(
        {
            "success": True,
            "source": payload["source"],
            "source_url": payload["source_url"],
            "fetched_at": payload["fetched_at"],
            "cached": payload.get("cached", False),
            "layer": "1.4",
            "count": len(records),
            "district_filter": district or None,
            "records": records,
            "derived_fields": [
                "trend_normalized",
                "trend_valid",
                "rise_1h_m",
                "rise_rate_m_per_hour",
                "distance_to_warning_m",
                "distance_to_danger_m",
                "warning_level_pct",
                "danger_level_pct",
                "hfl_level_pct",
                "level_state",
                "has_previous_hour",
                "processing_valid",
            ],
        }
    )


@app.get("/api/bihar/history")
def history():
    station = request.args.get("station", "").strip() or None
    district = request.args.get("district", "").strip() or None
    since_raw = request.args.get("since", "").strip() or None
    limit_raw = request.args.get("limit", "500").strip()

    try:
        limit = max(1, min(int(limit_raw), 1000))
    except ValueError:
        return _error_response("limit must be an integer between 1 and 1000", 400)

    since = None
    if since_raw:
        try:
            since = datetime.fromisoformat(since_raw.replace("Z", "+00:00"))
        except ValueError:
            return _error_response("since must be an ISO-8601 timestamp", 400)
        if since.tzinfo is None:
            since = since.replace(tzinfo=timezone.utc)

    try:
        repository = _repository()
        records = repository.get_history(
            station=station,
            district=district,
            since=since,
            limit=limit,
        )
    except Exception as exc:
        return _error_response(f"Historical Bihar river data query failed: {exc}", 503)

    return jsonify(
        {
            "success": True,
            "source": "Neon PostgreSQL",
            "layer": "1.4",
            "count": len(records),
            "filters": {
                "station": station,
                "district": district,
                "since": since.isoformat() if since else None,
                "limit": limit,
            },
            "records": [_serialize_observation(item) for item in records],
        }
    )


@app.get("/api/bihar/stations")
def stations():
    district = request.args.get("district", "").strip() or None

    try:
        repository = _repository()
        records = repository.get_history(district=district, limit=1000)
    except Exception as exc:
        return _error_response(f"Bihar station lookup failed: {exc}", 503)

    stations_by_key = {}
    for item in records:
        key = (item.river, item.station, item.district)
        if key not in stations_by_key:
            stations_by_key[key] = {
                "river": item.river,
                "station": item.station,
                "district": item.district,
                "latest_observed_at": item.observed_at.isoformat() if item.observed_at else None,
                "latest_water_level_m": item.water_level_m,
                "trend": item.trend,
            }

    result = sorted(
        stations_by_key.values(),
        key=lambda item: (item["district"], item["station"]),
    )

    return jsonify(
        {
            "success": True,
            "source": "Neon PostgreSQL",
            "layer": "1.4",
            "count": len(result),
            "district_filter": district,
            "stations": result,
        }
    )


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5002, debug=True)
