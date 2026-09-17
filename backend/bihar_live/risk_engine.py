"""Bihar Live 24-hour river-flood probability engine."""
from __future__ import annotations

from datetime import datetime
import json
import math
from pathlib import Path
from typing import Any

MODEL_PATH = Path(__file__).with_name("models") / "flood_probability.json"


def _number(value: Any) -> float | None:
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def _time(value: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def classify_level(water_level_m, warning_level_m, danger_level_m) -> str:
    level, warning, danger = map(_number, (water_level_m, warning_level_m, danger_level_m))
    if level is None:
        return "UNKNOWN"
    if danger is not None and level >= danger:
        return "DANGER"
    if warning is not None and level >= warning:
        return "WARNING"
    return "NORMAL"


def _feature_row(history: list[dict], record: dict) -> dict[str, float] | None:
    rows = []
    for item in history:
        level, stamp = _number(item.get("water_level_m")), _time(item.get("observed_at"))
        if level is not None and stamp is not None:
            rows.append((stamp, level))
    current, current_stamp = _number(record.get("water_level_m")), _time(record.get("observed_at"))
    if current is None or current_stamp is None:
        return None
    rows = [(stamp, level) for stamp, level in rows if stamp != current_stamp]
    rows.append((current_stamp, current))
    rows.sort(key=lambda x: x[0])
    if len(rows) < 25:
        return None
    values = [x[1] for x in rows]
    diff = lambda n: values[-1] - values[-1 - n]
    tail6, tail24 = values[-6:], values[-24:]
    mean24 = sum(tail24) / 24.0
    variance24 = sum((x - mean24) ** 2 for x in tail24) / 24.0
    return {
        "level": values[-1], "rise_1h": diff(1), "rise_3h": diff(3),
        "rise_6h": diff(6), "rise_12h": diff(12), "rise_24h": diff(24),
        "mean_6h": sum(tail6) / 6.0, "mean_24h": mean24,
        "std_24h": math.sqrt(variance24), "max_24h": max(tail24),
        "level_minus_mean24": values[-1] - mean24,
        "level_over_mean24": values[-1] / mean24 if abs(mean24) > 1e-9 else 1.0,
        "hour_sin": math.sin(2 * math.pi * rows[-1][0].hour / 24),
        "hour_cos": math.cos(2 * math.pi * rows[-1][0].hour / 24),
        "month_sin": math.sin(2 * math.pi * (rows[-1][0].month - 1) / 12),
        "month_cos": math.cos(2 * math.pi * (rows[-1][0].month - 1) / 12),
    }


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-max(-60.0, min(60.0, x))))


def _predict(features: dict[str, float], model: dict) -> float:
    z = float(model["intercept"])
    for name, mean, scale, coef in zip(model["feature_names"], model["scaler_mean"], model["scaler_scale"], model["coef"]):
        scale = float(scale) if abs(float(scale)) > 1e-12 else 1.0
        z += float(coef) * ((features[name] - float(mean)) / scale)
    return _sigmoid(z)


def _fallback(record: dict) -> dict:
    level, warning, danger = map(_number, (record.get("water_level_m"), record.get("warning_level_m"), record.get("danger_level_m")))
    previous = _number(record.get("water_level_1h_before_m"))
    rise = level - previous if level is not None and previous is not None else None
    score = None if level is None else 20.0
    if level is not None and warning and danger and danger > warning:
        score = 90.0 if level >= danger else (45.0 + 45.0 * (level-warning)/(danger-warning) if level >= warning else 45.0 * level/warning)
    if rise is not None and score is not None:
        score = min(100.0, max(0.0, score + max(-10.0, min(15.0, rise * 20.0))))
    return {"engine":"bihar_risk_engine","status":"operational_24h_score","method":"threshold_plus_1h_trend_projection","horizon_hours":24,"risk_level":"UNKNOWN" if score is None else ("HIGH" if score >= 70 else "MEDIUM" if score >= 40 else "LOW"),"risk_score_percent":round(score,1) if score is not None else None,"probability":None,"probability_available":False,"available":score is not None,"calibrated":False,"water_level_m":level,"warning_level_m":warning,"danger_level_m":danger,"rise_1h_m":round(rise,3) if rise is not None else None,"current_level_state":classify_level(level,warning,danger),"message":"Insufficient model inputs; this is an operational screening score, not a statistical probability."}


def build_risk_context(record: dict, history: list[dict] | None = None) -> dict:
    if not history or not MODEL_PATH.exists():
        return _fallback(record)
    try:
        model = json.loads(MODEL_PATH.read_text(encoding="utf-8"))
        features = _feature_row(history, record)
        if features is None:
            result = _fallback(record)
            result["message"] = "At least 25 usable hourly observations are required for the trained Bihar 24-hour model; showing the screening score."
            return result
        probability = _predict(features, model)
        medium = float(model.get("thresholds", {}).get("medium", 0.40))
        high = float(model.get("thresholds", {}).get("high", 0.70))
        risk = "HIGH" if probability >= high else "MEDIUM" if probability >= medium else "LOW"
        return {"engine":"bihar_risk_engine","status":"ml_probability","method":model.get("model_type","logistic_regression"),"horizon_hours":24,"risk_level":risk,"probability":round(probability,6),"probability_percent":round(probability*100,2),"probability_available":True,"available":True,"calibrated":bool(model.get("calibrated",False)),"model_version":model.get("model_version"),"validation":{"period":model.get("validation_period"),"rows":model.get("validation_rows"),"positive_rows":model.get("validation_positive_rows"),"average_precision":model.get("validation_average_precision"),"roc_auc":model.get("validation_roc_auc")},"features":features,"water_level_m":record.get("water_level_m"),"warning_level_m":record.get("warning_level_m"),"danger_level_m":record.get("danger_level_m"),"current_level_state":classify_level(record.get("water_level_m"),record.get("warning_level_m"),record.get("danger_level_m")),"message":"Model score for the supplied Bihar flood-event definition: score for a district flood event beginning within the next 24 hours. It is not calibrated as an absolute real-world probability."}
    except Exception as exc:
        result = _fallback(record)
        result["message"] = f"Trained Bihar model could not be evaluated; screening score shown. {type(exc).__name__}."
        return result
