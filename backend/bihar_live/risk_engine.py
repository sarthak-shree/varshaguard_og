"""Transparent 24-hour operational flood-risk calculation for Bihar Live.

This is an observation-derived risk score, not a calibrated probability. It
projects the latest river level forward using the observed one-hour change and
combines that projection with warning/danger thresholds.
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
    """Return a 0-100 operational score using only observed river inputs."""
    if level is None:
        return None

    # Absolute threshold position is the strongest signal.
    if danger is not None and danger > warning if warning is not None else danger is not None:
        if level >= danger:
            base = 90.0
        elif warning is not None and warning < danger:
            base = 45.0 + 45.0 * max(0.0, (level - warning) / (danger - warning))
        else:
            base = 45.0
    elif warning is not None and level >= warning:
        base = 60.0
    elif warning is not None and warning > 0:
        base = 45.0 * max(0.0, level / warning)
    else:
        base = 20.0

    # Rising water increases short-horizon operational risk; falling water
    # reduces it slightly. The adjustment is deliberately bounded.
    if rise_1h is not None:
        base += max(-10.0, min(15.0, rise_1h * 20.0))
    return round(max(0.0, min(100.0, base)), 1)


def build_risk_context(record: dict) -> dict:
    level = _number(record.get("water_level_m"))
    warning = _number(record.get("warning_level_m"))
    danger = _number(record.get("danger_level_m"))
    previous = _number(record.get("water_level_1h_before_m"))
    rise_1h = level - previous if level is not None and previous is not None else None

    # A simple 24-hour projection: repeat the latest observed hourly change.
    # This is intentionally labelled as a projection, not a forecast model.
    projected_24h = level + (rise_1h * 24.0) if level is not None and rise_1h is not None else None
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
        "probability": None,
        "probability_available": False,
        "calibrated": False,
        "water_level_m": level,
        "warning_level_m": warning,
        "danger_level_m": danger,
        "rise_1h_m": round(rise_1h, 3) if rise_1h is not None else None,
        "projected_level_24h_m": round(projected_24h, 3) if projected_24h is not None else None,
        "current_level_state": classify_level(level, warning, danger),
        "message": "24-hour operational risk score derived from the latest river level and one-hour trend. This is not a calibrated ML flood probability.",
    }
