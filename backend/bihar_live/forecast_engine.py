"""Operational 24-hour Bihar flood-risk and inundation forecasting helpers.

These functions provide a conservative, transparent baseline using live river
observations until trained Bihar-specific models and richer forecast inputs are
available. They never present a heuristic score as a calibrated ML probability.
"""

from __future__ import annotations

from math import exp
from typing import Any


def _safe_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number


def _sigmoid(x: float) -> float:
    if x >= 0:
        z = exp(-x)
        return 1.0 / (1.0 + z)
    z = exp(x)
    return z / (1.0 + z)


def build_24h_flood_forecast(record: dict) -> dict:
    level = _safe_float(record.get("water_level_m"))
    warning = _safe_float(record.get("warning_level_m"))
    danger = _safe_float(record.get("danger_level_m"))
    one_hour = _safe_float(record.get("water_level_1h_before_m"))

    if level is None or warning is None or danger is None or danger <= warning:
        return {
            "available": False,
            "probability": None,
            "risk_level": "UNKNOWN",
            "horizon_hours": 24,
            "method": "insufficient_inputs",
            "message": "24-hour flood probability requires valid river thresholds and current observations.",
        }

    rise = (level - one_hour) if one_hour is not None else 0.0
    threshold_position = (level - warning) / (danger - warning)
    rise_pressure = max(min(rise / max((danger - warning) * 0.25, 0.05), 2.0), -2.0)
    score = 2.4 * (threshold_position - 0.5) + 1.2 * rise_pressure
    probability = _sigmoid(score)

    if probability >= 0.70 or level >= danger:
        risk = "HIGH"
    elif probability >= 0.40 or level >= warning:
        risk = "MEDIUM"
    else:
        risk = "LOW"

    return {
        "available": True,
        "probability": round(probability, 4),
        "risk_level": risk,
        "horizon_hours": 24,
        "method": "live_observation_baseline",
        "calibrated": False,
        "inputs": {
            "water_level_m": level,
            "warning_level_m": warning,
            "danger_level_m": danger,
            "rise_1h_m": round(rise, 4),
        },
        "message": "Live 24-hour baseline estimate from observed river level and 1-hour change. Replace with a validated Bihar ML model when historical training data are available.",
    }


def build_24h_inundation_forecast(record: dict, risk_probability: float | None = None) -> dict:
    level = _safe_float(record.get("water_level_m"))
    warning = _safe_float(record.get("warning_level_m"))
    danger = _safe_float(record.get("danger_level_m"))

    if level is None or warning is None or danger is None or danger <= warning:
        return {
            "available": False,
            "extent_percent": None,
            "depth_m": None,
            "confidence": None,
            "horizon_hours": 24,
            "method": "insufficient_inputs",
            "message": "Inundation forecasting requires valid hydrology plus terrain and spatial floodplain inputs.",
        }

    exceedance = max(0.0, (level - warning) / max(danger - warning, 0.01))
    probability = max(0.0, min(1.0, float(risk_probability))) if risk_probability is not None else 0.0

    # This is a spatial proxy, not a physical inundation depth/extent model.
    # It is explicitly labelled as such in the API so it is not mistaken for
    # Sentinel-1/DEM/hydraulic output.
    extent_proxy = max(0.0, min(100.0, 10.0 + 45.0 * exceedance + 35.0 * probability))
    depth_proxy = max(0.0, min(2.5, 0.10 + 0.60 * exceedance + 0.80 * probability))

    return {
        "available": True,
        "extent_percent": round(extent_proxy, 1),
        "depth_m": round(depth_proxy, 2),
        "confidence": None,
        "horizon_hours": 24,
        "method": "hydrology_spatial_proxy",
        "calibrated": False,
        "physical_model": False,
        "message": "24-hour spatial proxy only. Not a validated inundation map; connect DEM, river geometry, flood-extent labels and a spatial model for true extent/depth prediction.",
    }
