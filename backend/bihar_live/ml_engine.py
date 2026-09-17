"""Live Bihar rainfall, river-alert and inundation-proxy engine.

The embedded calibrated model predicts the probability of a heavy-rain event
in the next 24 hours from recent district rainfall. It is deliberately NOT
labelled as a calibrated flood probability because the supplied overlapping
rainfall+river flood-event data contain too few positive events for a valid
joint flood model. River status and inundation are reported separately.
"""
from __future__ import annotations
import base64, io
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any
import joblib, numpy as np, pandas as pd, requests
from .data_service import fetch_live_data

BASE_DIR = Path(__file__).resolve().parents[2]
MODEL_B64_PATH = BASE_DIR / "models" / "bihar_heavy_rain_24h_model.pkl.b64"
RAINFALL_API = "https://sayantan-aquacarta.github.io/rainfall-pipeline/api/by-date/{date}.json"
IMD_HEAVY_MM = 64.5

def _number(value: Any, default: float = 0.0) -> float:
    try:
        x = float(value); return x if np.isfinite(x) else default
    except (TypeError, ValueError): return default

def _normalise(value: Any) -> str:
    return " ".join(str(value or "").upper().replace("_", " ").split())

def _payload_rows(payload: Any) -> list[dict]:
    if isinstance(payload, list): return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        for key in ("data", "rows", "results", "rainfall"):
            if isinstance(payload.get(key), list): return [x for x in payload[key] if isinstance(x, dict)]
    return []

@lru_cache(maxsize=1)
def _load_artifact() -> dict:
    if not MODEL_B64_PATH.exists(): raise FileNotFoundError("Bihar heavy-rain 24h model artifact is not installed.")
    artifact = joblib.load(io.BytesIO(base64.b64decode(MODEL_B64_PATH.read_text(encoding="utf-8").strip())))
    required = {"model", "calibrator", "features", "model_name", "target", "horizon_hours"}
    missing = required.difference(artifact)
    if missing: raise ValueError("Bihar rainfall model artifact missing: " + ", ".join(sorted(missing)))
    return artifact

@lru_cache(maxsize=32)
def _fetch_daily_rainfall(date_text: str) -> list[dict]:
    response = requests.get(RAINFALL_API.format(date=date_text), timeout=12, headers={"Cache-Control":"no-cache","User-Agent":"VARSHAGUARD/1.0"})
    response.raise_for_status(); return _payload_rows(response.json())

def _live_rainfall(days: int = 14):
    now = datetime.now(timezone.utc) + pd.Timedelta(hours=5, minutes=30)
    daily: dict[str, dict[str, float]] = {}; timestamps: dict[str, str] = {}; failures=[]
    for days_back in range(days-1, -1, -1):
        date_text=(now-pd.Timedelta(days=days_back)).date().isoformat()
        try: rows=_fetch_daily_rainfall(date_text)
        except Exception as exc: failures.append(f"{date_text}: {exc}"); continue
        district_values: dict[str,list[float]]={}
        for row in rows:
            if _normalise(row.get("state",row.get("State"))) != "BIHAR": continue
            district=_normalise(row.get("district",row.get("District")))
            if not district: continue
            district_values.setdefault(district,[]).append(max(0.0,_number(row.get("day_actual_mm",row.get("Daily Actual")))))
        for district, values in district_values.items():
            daily.setdefault(district,{})[date_text]=max(values) if values else 0.0; timestamps[district]=date_text
    return daily,timestamps,failures

def _rain_features(series: dict[str,float], month: int) -> dict[str,float]:
    values=[series[d] for d in sorted(series)] or [0.0]; last=values[-1]; prev=values[-2] if len(values)>1 else 0.0
    return {"rainfall_mm":last,"rainfall_max_mm":max(values),"rainfall_min_mm":min(values),"rainfall_3d_sum_mm":sum(values[-3:]),"rainfall_3d_max_mm":max(values[-3:]),"rainfall_7d_sum_mm":sum(values[-7:]),"rainfall_7d_max_mm":max(values[-7:]),"rainfall_14d_sum_mm":sum(values[-14:]),"rainfall_14d_max_mm":max(values[-14:]),"rainfall_change_1d_mm":last-prev,"station_count":1.0,"month":float(month),"is_monsoon":float(month in (6,7,8,9))}

def _river_summary(stations):
    levels=[]; rises=[]; warning_count=danger_count=0
    for s in stations:
        level=_number(s.get("water_level_m"),np.nan); warning=_number(s.get("warning_level_m"),np.nan); danger=_number(s.get("danger_level_m"),np.nan); rise=_number(s.get("rise_1h_m"),np.nan)
        if np.isfinite(level): levels.append(level)
        if np.isfinite(rise): rises.append(rise)
        if np.isfinite(danger) and np.isfinite(level) and level>=danger: danger_count+=1
        elif np.isfinite(warning) and np.isfinite(level) and level>=warning: warning_count+=1
    return {"count":len(stations),"mean":float(np.mean(levels)) if levels else None,"max":float(np.max(levels)) if levels else None,"warning_count":warning_count,"danger_count":danger_count,"rise":float(np.mean(rises)) if rises else None,"stations":stations}

def _risk_level(heavy_probability, river):
    if river["danger_count"]>0 or heavy_probability>=.70: return "HIGH"
    if river["warning_count"]>0 or heavy_probability>=.40: return "MEDIUM"
    return "LOW"

def _inundation_proxy(heavy_probability, river):
    if river["max"] is None or not river["stations"]: return {"available":False,"extent_percent":None,"depth_m":None,"method":"insufficient_live_hydrology"}
    exceedance=0.0
    for s in river["stations"]:
        level=_number(s.get("water_level_m"),np.nan); warning=_number(s.get("warning_level_m"),np.nan); danger=_number(s.get("danger_level_m"),np.nan)
        if np.isfinite(level) and np.isfinite(warning) and np.isfinite(danger) and danger>warning: exceedance=max(exceedance,max(0.0,min(1.5,(level-warning)/(danger-warning))))
    return {"available":True,"extent_percent":round(max(0.0,min(100.0,8+52*min(exceedance,1)+30*heavy_probability)),1),"depth_m":round(max(0.0,min(2.5,.05+.65*min(exceedance,1)+.7*heavy_probability)),2),"confidence":None,"method":"hydrology_spatial_proxy","physical_model":False,"message":"Proxy only: no DEM, floodplain geometry or hydraulic simulation is used."}

def clear_ml_cache(): _load_artifact.cache_clear(); _fetch_daily_rainfall.cache_clear()

def build_bihar_district_risk() -> dict:
    artifact=_load_artifact(); daily_rain,rain_timestamps,rain_failures=_live_rainfall(14); live=fetch_live_data(); stations=live.get("stations",[])
    by_district: dict[str,list[dict]]={}
    for station in stations:
        district=_normalise(station.get("district"));
        if district: by_district.setdefault(district,[]).append(station)
    now=datetime.now(timezone.utc)+pd.Timedelta(hours=5,minutes=30); rows=[]
    for district in sorted(set(daily_rain)|set(by_district)):
        rain=_rain_features(daily_rain.get(district,{}),now.month); X=pd.DataFrame([{f:rain.get(f,0.0) for f in artifact["features"]}],columns=artifact["features"])
        raw=float(artifact["model"].predict_proba(X)[0,1]); heavy=float(np.clip(artifact["calibrator"].predict([raw])[0],0,1)); river=_river_summary(by_district.get(district,[]))
        rows.append({"district":district.title(),"risk":_risk_level(heavy,river),"heavy_rain_probability":round(heavy,4),"heavy_rain_probability_percent":round(heavy*100,2),"heavy_rain_threshold_mm":IMD_HEAVY_MM,"rainfall_24h_mm":round(rain["rainfall_mm"],2),"rainfall_72h_mm":round(rain["rainfall_3d_sum_mm"],2),"rainfall_7d_mm":round(rain["rainfall_7d_sum_mm"],2),"river_level_mean_m":round(river["mean"],2) if river["mean"] is not None else None,"river_level_max_m":round(river["max"],2) if river["max"] is not None else None,"river_station_count":river["count"],"river_warning_count":river["warning_count"],"river_danger_count":river["danger_count"],"river_mean_rise_1h_m":round(river["rise"],4) if river["rise"] is not None else None,"inundation":_inundation_proxy(heavy,river),"data_timestamp":rain_timestamps.get(district,live.get("fetched_at",""))})
    return {"success":True,"region":"Bihar","generated_at":datetime.now(timezone.utc).isoformat(),"prediction_horizon_hours":24,"model":{"name":artifact["model_name"],"type":type(artifact["model"]).__name__,"target":artifact["target"],"calibrated":True,"calibration_method":artifact["calibration_method"],"scope":artifact["scope"],"test_metrics":artifact["test_metrics"],"training_period":artifact["training_period"],"test_period":artifact["test_period"],"warning":"This probability is for heavy rainfall in the next 24 hours, not a calibrated flood probability."},"rainfall_source":RAINFALL_API,"river_source":live.get("source_url"),"river_fetched_at":live.get("fetched_at"),"rainfall_failures":rain_failures,"districts":rows,"count":len(rows)}
