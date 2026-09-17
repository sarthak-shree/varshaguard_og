"""Transparent 24-hour operational flood-risk calculation for Bihar Live.

The displayed percentage is an operational risk score, not a calibrated
probability of flooding. It uses the latest observed river level, warning and
danger thresholds, and the observed one-hour level change to project the
current level 24 hours forward.
"""

from __future__ import annotations


def _number(value):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if value == value else None


def classify_level(water_level_m, warning_level_m, danger_level_m) -> str:
    level = _number(water_level_m)
    warning = _number(warning_level_m)
    danger = _number(danger_level_m)
    if level is None:
        return "UNKNOWN"
    if danger is not None and level >= danger:
        return "DANGER"
    if warning is not None and level >= warning:
        return "WARNING"
    return "NORMAL"


def _risk_score(level, warning, danger, rise_1h):
    """Return a bounded 0-100 operational score from observed inputs."""
    if level is None:
        return None

    if danger is not None and warning is not None and danger > warning:
        if level >= danger:
            base = 90.0
        elif level >= warning:
            base = 45.0 + 45.0 * ((level - warning) / (danger - warning))
        else:
            base = 45.0 * max(0.0, level / warning) if warning > 0 else 20.0
    elif danger is not None:
        base = 90.0 if level >= danger else 45.0 * max(0.0, level / danger)
    elif warning is not None:
        base = 60.0 if level >= warning else (45.0 * max(0.0, level / warning) if warning > 0 else 20.0)
    else:
        base = 20.0

    # Recent rise/fall is a short-horizon signal. Keep its influence bounded.
    if rise_1h is not None:
        base += max(-10.0, min(15.0, rise_1h * 20.0))

    return round(max(0.0, min(100.0, base)), 1)


def build_risk_context(record: dict) -> dict:
    level = _number(record.get("water_level_m"))
    warning = _number(record.get("warning_level_m"))
    danger = _number(record.get("danger_level_m"))
    previous = _number(record.get("water_level_1h_before_m"))
    rise_1h = level - previous if level is not None and previous is not None else None

    # Linear 24-hour projection from the latest observed hourly change.
    projected_24h = level + rise_1h * 24.0 if level is not None and rise_1h is not None else None
    score = _risk_score(level, warning, danger, rise_1h)

    if score is None:
        risk = "UNKNOWN"
    elif score >= 70:
        risk = "HIGH"
    elif score >= 40:
        risk = "MEDIUM"
    else:
        risk = "LOW"

    return {
        "engine": "bihar_risk_engine",
        "status": "operational_24h_score",
        "method": "threshold_plus_1h_trend_projection",
        "horizon_hours": 24,
        "risk_level": risk,
        "risk_score_percent": score,
        # Kept for the existing frontend contract. It is explicitly NOT a
        # statistical probability; probability_available remains false.
        "probability": None,
        "probability_available": False,
        "available": score is not None,
        "calibrated": False,
        "water_level_m": level,
        "warning_level_m": warning,
        "danger_level_m": danger,
        "rise_1h_m": round(rise_1h, 3) if rise_1h is not None else None,
        "projected_level_24h_m": round(projected_24h, 3) if projected_24h is not None else None,
        "current_level_state": classify_level(level, warning, danger),
        "message": "24-hour operational risk score derived from the latest river level and one-hour trend. This is not a calibrated ML flood probability.",
    }
