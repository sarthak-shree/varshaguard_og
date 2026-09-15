"""Separate Flask API for VARSHAGUARD Bihar Live v0.3.0."""

from __future__ import annotations

from datetime import datetime, timezone
from threading import Lock
import time

from flask import Flask, jsonify, request
from flask_cors import CORS

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


@app.get("/api/bihar/health")
def health():
    return jsonify(
        {
            "success": True,
            "service": "VARSHAGUARD Bihar Live API",
            "version": "0.3.0",
            "layer": "1.2",
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
            "layer": "1.2",
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


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5002, debug=True)
