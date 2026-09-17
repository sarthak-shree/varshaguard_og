"""Bihar Live 24-hour flood probability engine.

If a trained Bihar artifact exists, this module returns its probability that the
station will reach/exceed its danger level within the next 24 hours. Until an
artifact is trained from real historical Bihar observations, the API falls
back to the transparent operational score and never labels it as ML.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

MODEL_PATH = Path(__file__).with_name("models") / "flood_probability.joblib"
_METADATA_PATH = MODEL_PATH.with_suffix(".json")


def _number(value: Any) -> float | None:
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if value == value else None


def classify_level(water_level_m, warning_level_m, danger_level_m) -> str:
    level, warning, danger = map(_number, (water_level_m, warning_level_m, danger_level_m))
    if level is None:
        return "UNKNOWN"
    if danger is not None and level >= danger:
        return "DANGER"
    if warning is not None and level >= warning:
        return "WARNING"
    return "NORMAL"


def _feature_row(history: list[dict], record: dict) -> dict | None:
    rows = []
    for item in history:
        level = _number(item.get("water_level_m"))
        if level is None:
            continue
        stamp = item.get("observed_at")
        try:
            stamp = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            continue
        rows.append((stamp, level, _number(item.get("warning_level_m")), _number(item.get("danger_level_m"))))
    current = _number(record.get("water_level_m"))
    if current is None:
        return None
    rows.sort(key=lambda x: x[0])
    if not rows or abs(rows[-1][1] - current) > 1e-9:
        try:
            stamp = datetime.fromisoformat(str(record.get("observed_at")).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            stamp = rows[-1][0]
        rows.append((stamp, current, _number(record.get("warning_level_m")), _number(record.get("danger_level_m"))))
    values = [r[1] for r in rows]
    if len(values) < 25:
        return None
    danger = _number(record.get("danger_level_m"))
    warning = _number(record.get("warning_level_m"))
    if danger is None or danger <= 0:
        return None
    def diff(hours: int) -> float:
        return values[-1] - values[-1-hours] if len(values) > hours else 0.0
    tail = values[-24:]
    mean24 = sum(tail) / len(tail)
    variance = sum((x - mean24) ** 2 for x in tail) / len(tail)
    return {
        "level": values[-1],
        "level_ratio_warning": values[-1] / warning if warning and warning > 0 else 0.0,
        "level_ratio_danger": values[-1] / danger,
        "rise_1h": diff(1), "rise_3h": diff(3), "rise_6h": diff(6),
        "rise_12h": diff(12), "rise_24h": diff(24),
        "mean_6h": sum(values[-6:]) / min(6, len(values)),
        "mean_24h": mean24,
        "std_24h": variance ** 0.5,
        "max_6h": max(values[-6:]), "max_24h": max(tail),
        "hour": rows[-1][0].hour, "month": rows[-1][0].month,
    }


def _fallback(record: dict) -> dict:
    level = _number(record.get("water_level_m"))
    warning = _number(record.get("warning_level_m"))
    danger = _number(record.get("danger_level_m"))
    previous = _number(record.get("water_level_1h_before_m"))
    rise = level - previous if level is not None and previous is not None else None
    projected = level + rise * 24 if level is not None and rise is not None else None
    score = None if level is None else 20.0
    if level is not None and danger and warning and danger > warning:
        score = 90.0 if level >= danger else (45.0 + 45.0 * (level-warning)/(danger-warning) if level >= warning else 45.0 * level/warning)
    if rise is not None:
        score = min(100.0, max(0.0, score + max(-10.0, min(15.0, rise*20.0)))) if score is not None else None
    return {"engine":"bihar_risk_engine","status":"operational_24h_score","method":"threshold_plus_1h_trend_projection","horizon_hours":24,"risk_level":"UNKNOWN" if score is None else ("HIGH" if score >= 70 else "MEDIUM" if score >= 40 else "LOW"),"risk_score_percent":round(score,1) if score is not None else None,"probability":None,"probability_available":False,"available":score is not None,"calibrated":False,"water_level_m":level,"warning_level_m":warning,"danger_level_m":danger,"rise_1h_m":round(rise,3) if rise is not None else None,"projected_level_24h_m":round(projected,3) if projected is not None else None,"current_level_state":classify_level(level,warning,danger),"message":"No trained Bihar ML artifact is installed. This is an operational screening score, not a statistical probability."}


def build_risk_context(record: dict, history: list[dict] | None = None) -> dict:
    if not MODEL_PATH.exists() or not history:
        return _fallback(record)
    try:
        import joblib
        import json
        model = joblib.load(MODEL_PATH)
        features = _feature_row(history, record)
        if features is None:
            result = _fallback(record)
            result["message"] = "Insufficient hourly history for the trained 24-hour ML model; showing the operational screening score."
            return result
        probability = float(model.predict_proba([features])[0][1])
        metadata = json.loads(_METADATA_PATH.read_text(encoding="utf-8")) if _METADATA_PATH.exists() else {}
        risk = "HIGH" if probability >= 0.70 else "MEDIUM" if probability >= 0.40 else "LOW"
        return {"engine":"bihar_risk_engine","status":"ml_probability","method":metadata.get("model","trained_bihar_flood_probability"),"horizon_hours":24,"risk_level":risk,"probability":round(probability,4),"probability_percent":round(probability*100,1),"probability_available":True,"available":True,"calibrated":bool(metadata.get("calibrated",False)),"model_version":metadata.get("model_version"),"validation":metadata.get("validation"),"features":list(features.keys()),"water_level_m":record.get("water_level_m"),"warning_level_m":record.get("warning_level_m"),"danger_level_m":record.get("danger_level_m"),"current_level_state":classify_level(record.get("water_level_m"),record.get("warning_level_m"),record.get("danger_level_m")),"message":"Trained Bihar model probability: probability of reaching/exceeding the station danger level within the next 24 hours."}
    except Exception as exc:
        result = _fallback(record)
        result["message"] = f"ML artifact unavailable at runtime; operational screening score shown. {type(exc).__name__}."
        return result
