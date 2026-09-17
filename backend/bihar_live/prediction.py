"""Transparent live Bihar prediction fallbacks.

This module uses live hydrology plus optional live satellite precipitation when
available. It deliberately separates an ML probability from deterministic
risk context and marks heuristic output as such.
"""
from __future__ import annotations

from math import exp
from typing import Any


def _num(value: Any) -> float | None:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return v


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + exp(-max(-30.0, min(30.0, x))))


def compute_live_risk(record: dict, rainfall_24h_mm: float | None = None) -> dict:
    """Return a calibrated-input-shaped live risk estimate.

    When no validated Bihar ML artifact is installed, this is explicitly a
    heuristic operational estimate, not an ML probability. It combines level
    position, level rise and optional satellite rainfall into a bounded score.
    """
    level = _num(record.get("water_level_m"))
    warning = _num(record.get("warning_level_m"))
    danger = _num(record.get("danger_level_m"))
    rise = _num(record.get("water_level_1h_before_m"))
    rise_1h = (level - rise) if level is not None and rise is not None else 0.0

    normalized_level = 0.0
    if level is not None:
        ref = danger if danger and danger > 0 else warning
        if ref:
            normalized_level = max(0.0, min(1.5, level / ref))
    level_component = max(0.0, min(1.0, (normalized_level - 0.75) / 0.25))
    rise_component = max(0.0, min(1.0, rise_1h / 0.30))
    rain_component = max(0.0, min(1.0, (rainfall_24h_mm or 0.0) / 150.0))

    score = _sigmoid(-2.0 + 3.0 * level_component + 1.2 * rise_component + 1.0 * rain_component)
    label = "HIGH" if score >= 0.70 else "MEDIUM" if score >= 0.40 else "LOW"
    return {
        "engine": "bihar_live_risk",
        "status": "operational_heuristic",
        "probability": round(score, 4),
        "probability_type": "heuristic_operational_estimate",
        "horizon_hours": 24,
        "risk_level": label,
        "inputs": {
            "water_level_m": level,
            "warning_level_m": warning,
            "danger_level_m": danger,
            "rise_1h_m": round(rise_1h, 3),
            "rainfall_24h_mm": rainfall_24h_mm,
        },
        "message": "24-hour operational estimate from live river conditions. Replace with a temporally validated Bihar ML model before treating this value as a trained probability.",
    }


def estimate_inundation(record: dict, risk_probability: float | None) -> dict:
    """Provide a deterministic screening estimate, not a flood-depth model."""
    level = _num(record.get("water_level_m"))
    danger = _num(record.get("danger_level_m"))
    if level is None or not danger or danger <= 0:
        exceedance = 0.0
    else:
        exceedance = max(0.0, level / danger - 0.85)
    rp = max(0.0, min(1.0, risk_probability or 0.0))
    extent = max(0.0, min(100.0, (exceedance * 180.0) + rp * 20.0))
    depth = max(0.0, min(3.0, exceedance * 2.0))
    return {
        "engine": "bihar_inundation_screening",
        "status": "screening_estimate",
        "horizon_hours": 24,
        "extent_percent": round(extent, 1),
        "depth_m": round(depth, 2),
        "confidence": None,
        "probability_type": "derived_screening_estimate",
        "message": "Screening estimate only. True inundation requires DEM, river geometry, hydraulics and/or historical spatial flood labels; this output is not a validated flood extent prediction.",
    }
