"""Operational 24-hour Bihar river risk baseline.

This is deliberately NOT presented as a trained/calibrated ML model. It converts
live water level and one-hour change into a transparent forward-risk estimate
until sufficient Bihar historical rainfall, river-level and flood-event labels
are available for supervised training and calibration.
"""

from __future__ import annotations

import math


def classify_level(water_level_m: float | None, warning_level_m: float | None, danger_level_m: float | None) -> str:
    if water_level_m is None:
        return "UNKNOWN"
    if danger_level_m is not None and water_level_m >= danger_level_m:
        return "HIGH"
    if warning_level_m is not None and water_level_m >= warning_level_m:
        return "MEDIUM"
    return "LOW"


def _number(value):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def _sigmoid(value: float) -> float:
    value = max(-8.0, min(8.0, value))
    return 1.0 / (1.0 + math.exp(-value))


def build_risk_context(record: dict) -> dict:
    level = _number(record.get("water_level_m"))
    warning = _number(record.get("warning_level_m"))
    danger = _number(record.get("danger_level_m"))
    previous = _number(record.get("water_level_1h_before_m"))

    if level is None or warning is None or danger is None or danger <= warning:
        return {
            "engine": "bihar_risk_engine",
            "status": "insufficient_live_inputs",
            "available": False,
            "probability": None,
            "probability_available": False,
            "calibrated": False,
            "method": "live_observation_baseline",
            "risk_level": "UNKNOWN",
            "message": "A 24-hour baseline needs current, warning and danger water levels.",
        }

    rise_1h = (level - previous) if previous is not None else 0.0
    projected_24h = level + (rise_1h * 24.0)
    gap = max(danger - warning, 0.001)

    # Two observable signals: where the river is now and where a simple
    # 24-hour persistence projection puts it. This is a transparent baseline,
    # not a learned probability and not calibrated to flood-event frequency.
    current_signal = (level - warning) / gap
    projected_signal = (projected_24h - danger) / gap
    score = 0.35 * current_signal + 0.65 * projected_signal
    probability = max(0.01, min(0.99, _sigmoid(3.0 * score)))

    if probability >= 0.70:
        risk = "HIGH"
    elif probability >= 0.40:
        risk = "MEDIUM"
    else:
        risk = "LOW"

    return {
        "engine": "bihar_risk_engine",
        "status": "operational_baseline",
        "available": True,
        "probability": round(probability, 4),
        "probability_available": True,
        "calibrated": False,
        "method": "live_observation_baseline",
        "risk_level": risk,
        "horizon_hours": 24,
        "water_level_m": level,
        "warning_level_m": warning,
        "danger_level_m": danger,
        "rise_1h_m": round(rise_1h, 4),
        "projected_level_24h_m": round(projected_24h, 4),
        "trend": record.get("trend"),
        "message": "24-hour operational risk estimate from live river level and 1-hour change. It is not a calibrated ML probability; train and validate the Bihar model before using it as an official forecast.",
    }
