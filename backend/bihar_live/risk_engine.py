"""Bihar Live risk interpretation layer.

The engine deliberately distinguishes observed threshold status from an ML
probability. Until a validated Bihar flood-probability model is connected,
this module returns transparent observation-derived context only.
"""

from __future__ import annotations


def classify_level(water_level_m: float | None, warning_level_m: float | None, danger_level_m: float | None) -> str:
    if water_level_m is None:
        return "UNKNOWN"
    if danger_level_m is not None and water_level_m >= danger_level_m:
        return "DANGER"
    if warning_level_m is not None and water_level_m >= warning_level_m:
        return "WARNING"
    return "NORMAL"


def build_risk_context(record: dict) -> dict:
    level = classify_level(
        record.get("water_level_m"),
        record.get("warning_level_m"),
        record.get("danger_level_m"),
    )
    return {
        "engine": "bihar_risk_engine",
        "status": "observation_context",
        "risk_level": level,
        "probability": None,
        "probability_available": False,
        "water_level_m": record.get("water_level_m"),
        "warning_level_m": record.get("warning_level_m"),
        "danger_level_m": record.get("danger_level_m"),
        "trend": record.get("trend"),
        "message": "Threshold-based river condition. ML flood probability is not reported until a validated Bihar predictive model is connected.",
    }
