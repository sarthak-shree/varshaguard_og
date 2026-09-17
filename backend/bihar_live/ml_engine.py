"""Live Bihar flood-risk engine for the prototype dashboard.

The current deployed model is a cross-region Random Forest trained on the
repository's existing rainfall table. It is NOT a Bihar-calibrated probability
model. Live Bihar rainfall and government river observations are fused into a
24-hour risk signal. This keeps the limitation explicit while making the live
prototype useful and resilient.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Any
import os

import pandas as pd
import requests
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, roc_auc_score

from .data_service import fetch_live_data

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
DATA_PATH = os.path.join(BASE_DIR, "data", "processed", "flood_warning_ml_ready_v2.csv")
RAINFALL_API = "https://sayantan-aquacarta.github.io/rainfall-pipeline/api/by-date/{date}.json"
DAILY_FEATURES = ["rainfall_1h","rainfall_3h","rainfall_6h","rainfall_12h","rainfall_24h","rainfall_48h","rainfall_72h","rainfall_6h_max","rainfall_24h_max","month","hour_of_day","is_monsoon"]


def _number(value: Any, default: float = 0.0) -> float:
    try:
        x = float(value)
        return x if pd.notna(x) else default
    except (TypeError, ValueError):
        return default


def _payload_rows(payload: Any) -> list[dict]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        for key in ("data", "rows", "results", "rainfall"):
            value = payload.get(key)
            if isinstance(value, list):
                return [x for x in value if isinstance(x, dict)]
    return []


def _normalise_name(value: Any) -> str:
    return " ".join(str(value or "").upper().replace("_", " ").split())


def _historical_daily_frame() -> pd.DataFrame:
    data = pd.read_csv(DATA_PATH)
    timestamp_column = "timestamp" if "timestamp" in data.columns else "hour"
    data["timestamp"] = pd.to_datetime(data[timestamp_column], errors="coerce")
    data["flood_soon"] = pd.to_numeric(data.get("flood_soon", 0), errors="coerce").fillna(0).astype(int)
    data = data.dropna(subset=["timestamp"]).copy()
    for column in DAILY_FEATURES:
        if column not in ("month", "hour_of_day", "is_monsoon"):
            data[column] = pd.to_numeric(data.get(column, 0), errors="coerce").fillna(0).clip(0, 5000)
    data["date"] = data["timestamp"].dt.date
    data["month"] = data["timestamp"].dt.month
    data["hour_of_day"] = data["timestamp"].dt.hour
    data["is_monsoon"] = data["month"].isin([6,7,8,9]).astype(int)
    groups = ["region", "station", "date"] if {"region","station"}.issubset(data.columns) else ["date"]
    agg = {c:"max" for c in DAILY_FEATURES if c not in ("month","hour_of_day","is_monsoon")}
    agg.update({"month":"first","hour_of_day":"first","is_monsoon":"first","flood_soon":"max"})
    return data.groupby(groups, as_index=False).agg(agg).sort_values("date").reset_index(drop=True)


def _model() -> RandomForestClassifier:
    return RandomForestClassifier(n_estimators=300,max_depth=12,min_samples_leaf=2,class_weight="balanced",random_state=42,n_jobs=-1)


@lru_cache(maxsize=1)
def _train_model() -> dict:
    if not os.path.exists(DATA_PATH):
        return {"ok":False,"error":"Historical training dataset is missing."}
    try:
        daily = _historical_daily_frame()
    except Exception as exc:
        return {"ok":False,"error":"Historical dataset could not be prepared: " + str(exc)}
    if daily.empty or daily["flood_soon"].nunique() < 2:
        return {"ok":False,"error":"Historical dataset does not contain both flood and non-flood classes."}
    dates = pd.Series(sorted(daily["date"].unique()))
    fold_acc=[]; fold_auc=[]
    # Expanding-window chronological validation.
    for fold in range(1, min(5, len(dates)-1)):
        boundary = int(len(dates)*fold/min(5,len(dates)-1))
        test_end = min(len(dates), boundary + max(1, len(dates)//min(5,len(dates)-1)))
        train_dates=set(dates.iloc[:boundary]); test_dates=set(dates.iloc[boundary:test_end])
        train=daily[daily.date.isin(train_dates)]; test=daily[daily.date.isin(test_dates)]
        if train.empty or test.empty or train.flood_soon.nunique()<2 or test.flood_soon.nunique()<2:
            continue
        candidate=_model(); candidate.fit(train[DAILY_FEATURES],train.flood_soon)
        pred=candidate.predict(test[DAILY_FEATURES]); proba=candidate.predict_proba(test[DAILY_FEATURES])[:,1]
        fold_acc.append(float(accuracy_score(test.flood_soon,pred))); fold_auc.append(float(roc_auc_score(test.flood_soon,proba)))
    final=_model(); final.fit(daily[DAILY_FEATURES],daily.flood_soon)
    return {"ok":True,"model":final,"training_rows":int(len(daily)),"accuracy":round(sum(fold_acc)/len(fold_acc),4) if fold_acc else None,"roc_auc":round(sum(fold_auc)/len(fold_auc),4) if fold_auc else None,"validation_folds":len(fold_acc),"scope":"cross_region_daily_rainfall","bihar_calibrated":False}


def clear_ml_cache() -> None:
    _train_model.cache_clear(); _fetch_daily_rainfall.cache_clear()


@lru_cache(maxsize=8)
def _fetch_daily_rainfall(date_text: str) -> list[dict]:
    response=requests.get(RAINFALL_API.format(date=date_text),timeout=8)
    response.raise_for_status()
    return _payload_rows(response.json())


def _live_bihar_rainfall() -> tuple[dict[str,list[float]], list[str]]:
    now=datetime.now(timezone.utc)+timedelta(hours=5,minutes=30)
    result:dict[str,list[float]]={}; failures=[]
    for days_back in (2,1,0):
        date_text=(now-timedelta(days=days_back)).date().isoformat()
        try:
            rows=_fetch_daily_rainfall(date_text)
        except Exception as exc:
            failures.append(f"{date_text}: {exc}"); continue
        for row in rows:
            if _normalise_name(row.get("state",row.get("State")))!="BIHAR": continue
            district=_normalise_name(row.get("district",row.get("District")))
            if not district: continue
            rain=max(0.0,_number(row.get("day_actual_mm",row.get("Daily Actual"))))
            result.setdefault(district,[]).append(rain)
    return result, failures


def _rainfall_features(values:list[float],month:int,hour:int)->dict[str,float]:
    values=([0.0,0.0,0.0]+values)[-3:]
    d1,d2,d3=values[-1],values[-2],values[-3]
    return {"rainfall_1h":d1/24,"rainfall_3h":d1/8,"rainfall_6h":d1/4,"rainfall_12h":d1/2,"rainfall_24h":d1,"rainfall_48h":d1+d2,"rainfall_72h":d1+d2+d3,"rainfall_6h_max":d1/4,"rainfall_24h_max":max(values),"month":month,"hour_of_day":hour,"is_monsoon":int(month in (6,7,8,9))}


def _river_signal(stations:list[dict])->tuple[float,dict]:
    if not stations: return 0.0,{"station_count":0,"danger_stations":0,"warning_stations":0,"max_threshold_pressure":0.0}
    pressures=[]; danger_count=warning_count=0
    for s in stations:
        level=_number(s.get("water_level_m")); warning=_number(s.get("warning_level_m")); danger=_number(s.get("danger_level_m"))
        if danger>warning>0:
            pressure=max(0.0,min(1.0,(level-warning)/(danger-warning)))
            if level>=danger: danger_count+=1
            elif level>=warning: warning_count+=1
        else:
            rise=_number(s.get("rise_1h_m")); pressure=max(0.0,min(1.0,0.5+rise*5.0))
        pressures.append(pressure)
    signal=max(pressures) if pressures else 0.0
    return signal,{"station_count":len(stations),"danger_stations":danger_count,"warning_stations":warning_count,"max_threshold_pressure":round(signal,4)}


def build_bihar_district_risk()->dict:
    model_info=_train_model()
    if not model_info.get("ok"): return {"success":False,"error":model_info.get("error","ML model unavailable")}
    rainfall,rain_failures=_live_bihar_rainfall()
    try: live=fetch_live_data()
    except Exception as exc: live={"stations":[],"source_url":None,"error":str(exc)}
    station_rows=live.get("stations",[])
    by_district:dict[str,list[dict]]={}
    for s in station_rows:
        d=_normalise_name(s.get("district"));
        if d: by_district.setdefault(d,[]).append(s)
    now=datetime.now(timezone.utc)+timedelta(hours=5,minutes=30)
    rows=[]
    for district,values in sorted(rainfall.items()):
        features=_rainfall_features(values,now.month,now.hour)
        rain_probability=float(model_info["model"].predict_proba(pd.DataFrame([features],columns=DAILY_FEATURES))[0,1])
        river_signal,river_meta=_river_signal(by_district.get(district,[]))
        # This is a prototype fusion score, not a calibrated statistical probability.
        fused=1.0-(1.0-rain_probability)*(1.0-river_signal)
        risk="HIGH" if fused>=0.70 else "MEDIUM" if fused>=0.40 else "LOW"
        rows.append({"district":district.title(),"flood_probability":round(fused,4),"risk":risk,"rainfall_probability":round(rain_probability,4),"river_signal":round(river_signal,4),"rainfall_24h_mm":round(features["rainfall_24h"],2),"rainfall_48h_mm":round(features["rainfall_48h"],2),"rainfall_72h_mm":round(features["rainfall_72h"],2),**river_meta})
    warning="Prototype 24-hour risk signal. The Random Forest is cross-region and not Bihar-calibrated; the displayed value is not an operational probability."
    if rain_failures: warning += " Some rainfall dates were unavailable; the latest available rainfall was used."
    return {"success":True,"region":"Bihar","generated_at":datetime.now(timezone.utc).isoformat(),"prediction_horizon_hours":24,"model":{"type":"RandomForestClassifier","scope":model_info["scope"],"bihar_calibrated":False,"historical_training_rows":model_info["training_rows"],"validation_folds":model_info["validation_folds"],"historical_accuracy":model_info["accuracy"],"historical_roc_auc":model_info["roc_auc"],"probability_method":"RF rainfall likelihood fused with live river-threshold pressure","warning":warning},"rainfall_source":RAINFALL_API,"river_source":live.get("source_url"),"districts":rows,"count":len(rows)}
