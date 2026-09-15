"""Separate Flask API for VARSHAGUARD Bihar Live v0.3.0."""

from __future__ import annotations

from datetime import datetime, timezone
from threading import Lock
import time

from flask import Flask, jsonify, request
from flask_cors import CORS

try:
    from .ingest import fetch_live_river_observations
except ImportError:
    from ingest import fetch_live_river_observations


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


@app.get("/api/bihar/health")
def health():
    return jsonify(
        {
            "success": True,
            "service": "VARSHAGUARD Bihar Live API",
            "version": "0.3.0",
            "layer": "1.1",
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

    records = payload["records"]
    if district:
        records = [row for row in records if row["district"].lower() == district]

    return jsonify(
        {
            **payload,
            "records": records,
            "count": len(records),
            "district_filter": district or None,
        }
    )


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5002, debug=True)
