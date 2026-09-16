"""Separate Flask API for VARSHAGUARD Bihar Live v0.3.0."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
import os
import time

from dotenv import load_dotenv
from flask import Flask, jsonify, request
from flask_cors import CORS

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env.local")

try:
    from .processing import process_river_records
except ImportError:
    from processing import process_river_records

app = Flask(__name__)
CORS(app)

CACHE_TTL_SECONDS = 300
STALE_AFTER_MINUTES = 60
_cache = {}
_cache_lock = Lock()


def _error_response(message: str, status_code: int = 500):
    return jsonify({
        "success": False,
        "error": message,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }), status_code


def _repository():
    from .postgres import PostgreSQLRiverObservationRepository
    return PostgreSQLRiverObservationRepository.from_env()


def _freshness(observed_at: str | None, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    if not observed_at:
        return {"status": "unknown", "fresh": False, "age_minutes": None}
    try:
        dt = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return {"status": "unknown", "fresh": False, "age_minutes": None}
    age = max((now - dt.astimezone(timezone.utc)).total_seconds() / 60.0, 0.0)
    return {
        "status": "fresh" if age <= STALE_AFTER_MINUTES else "stale",
        "fresh": age <= STALE_AFTER_MINUTES,
        "age_minutes": round(age, 2),
    }


def _get_latest_neon_payload(district: str | None = None) -> dict:
    repository = _repository()
    records = repository.get_history(district=district or None, limit=1000)
    latest = {}
    for item in records:
        key = (item.river, item.station, item.district)
        if key not in latest:
            latest[key] = item

    serialized = []
    for item in latest.values():
        observed_at = item.observed_at.isoformat() if item.observed_at else None
        fetched_at = item.fetched_at.isoformat() if item.fetched_at else None
        fresh = _freshness(observed_at)
        serialized.append({
            "river": item.river,
            "station": item.station,
            "district": item.district,
            "water_level_m": item.water_level_m,
            "warning_level_m": item.warning_level_m,
            "danger_level_m": item.danger_level_m,
            "hfl_m": item.hfl_m,
            "trend": item.trend,
            "water_level_1h_before_m": item.water_level_1h_before_m,
            "observed_at": observed_at,
            "fetched_at": fetched_at,
            "freshness": fresh,
            "quality_status": "good" if fresh["fresh"] else "stale",
        })

    newest = max((x.get("fetched_at") for x in serialized if x.get("fetched_at")), default=None)
    return {
        "success": True,
        "source": "Bihar FMISC/WRD via Neon PostgreSQL",
        "source_url": "https://beams.fmiscwrdbihar.gov.in/Alerttotalinfo/realtimetotal.aspx",
        "fetched_at": newest or datetime.now(timezone.utc).isoformat(),
        "count": len(serialized),
        "records": serialized,
        "fields": [
            "river", "station", "district", "water_level_m",
            "warning_level_m", "danger_level_m", "hfl_m",
            "trend", "status", "observed_at", "freshness", "quality_status",
        ],
        "live": True,
        "source_mode": "neon_live_snapshot",
        "cached": False,
    }


def _get_live_payload(force_refresh: bool = False, district: str | None = None) -> dict:
    now = time.monotonic()
    cache_key = district or "__all__"
    with _cache_lock:
        cached = _cache.get(cache_key)
        if not force_refresh and cached and now < cached["expires_at"]:
            payload = dict(cached["payload"])
            payload["cached"] = True
            return payload

    payload = _get_latest_neon_payload(district)
    with _cache_lock:
        _cache[cache_key] = {
            "payload": payload,
            "expires_at": time.monotonic() + CACHE_TTL_SECONDS,
        }
    return payload


def _filter_district(records: list[dict], district: str) -> list[dict]:
    if not district:
        return records
    target = district.strip().casefold()
    return [row for row in records if str(row.get("district") or "").strip().casefold() == target]


@app.get("/api/bihar/health")
def health():
    configured = bool(os.getenv("DATABASE_URL"))
    return jsonify({
        "success": True,
        "service": "VARSHAGUARD Bihar Live API",
        "version": "0.3.0",
        "layer": "1.5+",
        "storage_configured": configured,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


@app.get("/api/bihar/data-health")
def data_health():
    try:
        repository = _repository()
        records = repository.get_history(limit=1000)
    except Exception as exc:
        return _error_response(f"Bihar data-health query failed: {exc}", 503)

    latest = None
    for item in records:
        if item.fetched_at and (latest is None or item.fetched_at > latest):
            latest = item.fetched_at

    latest_iso = latest.isoformat() if latest else None
    fresh = _freshness(latest_iso)
    return jsonify({
        "success": True,
        "sources": [{
            "source": "Bihar FMISC/WRD",
            "source_url": "https://beams.fmiscwrdbihar.gov.in/Alerttotalinfo/realtimetotal.aspx",
            "status": "healthy" if fresh["fresh"] else "stale",
            "last_success": latest_iso,
            "last_observation": latest_iso,
            "record_count": len(records),
            "stale": not fresh["fresh"],
            "quality": fresh["status"],
            "error": None,
        }],
        "checked_at": datetime.now(timezone.utc).isoformat(),
    })


@app.get("/api/bihar/live-rivers")
def live_rivers():
    force_refresh = request.args.get("refresh", "false").lower() == "true"
    district = request.args.get("district", "").strip().lower()
    try:
        payload = _get_live_payload(force_refresh=force_refresh, district=district)
    except Exception as exc:
        return _error_response(f"Live Bihar river data unavailable from Neon: {exc}", 503)

    records = _filter_district(payload["records"], district)
    stale_records = sum(1 for row in records if not row.get("freshness", {}).get("fresh", False))
    return jsonify({
        **payload,
        "records": records,
        "count": len(records),
        "district_filter": district or None,
        "stale_count": stale_records,
        "warning": "These values are live from the latest successful FMISC sync; the Vercel API does not scrape FMISC directly.",
    })


@app.get("/api/bihar/processed-rivers")
def processed_rivers():
    force_refresh = request.args.get("refresh", "false").lower() == "true"
    district = request.args.get("district", "").strip().lower()
    try:
        payload = _get_live_payload(force_refresh=force_refresh, district=district)
        records = process_river_records(payload["records"])
    except Exception as exc:
        return _error_response(f"Bihar river processing failed: {exc}", 503)
    return jsonify({
        "success": True,
        "source": payload["source"],
        "source_url": payload["source_url"],
        "fetched_at": payload["fetched_at"],
        "cached": payload.get("cached", False),
        "layer": "1.5+",
        "count": len(records),
        "district_filter": district or None,
        "records": records,
    })


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
        records = _repository().get_history(
            station=station, district=district, since=since, limit=limit
        )
    except Exception as exc:
        return _error_response(f"Historical Bihar river data query failed: {exc}", 503)

    return jsonify({
        "success": True,
        "source": "Neon PostgreSQL",
        "layer": "1.5+",
        "count": len(records),
        "filters": {"station": station, "district": district, "since": since.isoformat() if since else None, "limit": limit},
        "records": [{
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
        } for item in records],
    })


@app.get("/api/bihar/stations")
def stations():
    district = request.args.get("district", "").strip() or None
    try:
        records = _repository().get_history(district=district, limit=1000)
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

    result = sorted(stations_by_key.values(), key=lambda item: (item["district"], item["station"]))
    return jsonify({
        "success": True,
        "source": "Neon PostgreSQL",
        "layer": "1.5+",
        "count": len(result),
        "district_filter": district,
        "stations": result,
    })


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5002, debug=True)
