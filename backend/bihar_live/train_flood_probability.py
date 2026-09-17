"""Train the Bihar 24-hour flood-probability model.

Target: a station reaches/exceeds its danger level at least once in the next
24 hourly observations. This is a station-level early-warning probability,
not a claim of spatial inundation.

Usage:
  python -m backend.bihar_live.train_flood_probability --input data.csv

The input CSV must contain timestamp, station and water-level columns. River,
district, warning-level and danger-level columns are strongly recommended.
The trainer accepts common column-name variants and writes the model plus
metadata under backend/bihar_live/models/.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, f1_score, precision_score, recall_score, roc_auc_score
from sklearn.model_selection import TimeSeriesSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "models"
FEATURES = ["level","level_ratio_warning","level_ratio_danger","rise_1h","rise_3h","rise_6h","rise_12h","rise_24h","mean_6h","mean_24h","std_24h","max_6h","max_24h","hour","month"]


def _pick(df, names, required=True):
    normalized = {str(c).strip().lower().replace(" ", "_"): c for c in df.columns}
    for name in names:
        key = name.lower().replace(" ", "_")
        if key in normalized:
            return normalized[key]
    if required:
        raise ValueError(f"Missing required column; tried: {names}")
    return None


def _load(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    ts = _pick(df, ["timestamp","datetime","date_time","observed_at","date"])
    station = _pick(df, ["station","station_name","station_id"])
    level = _pick(df, ["water_level_m","water_level","river_water_level","level"])
    warning = _pick(df, ["warning_level_m","warning_level","warning"], False)
    danger = _pick(df, ["danger_level_m","danger_level","danger"], False)
    river = _pick(df, ["river","river_name"], False)
    district = _pick(df, ["district","district_name"], False)
    out = pd.DataFrame({"timestamp": pd.to_datetime(df[ts], errors="coerce", utc=True),"station":df[station].astype(str).str.strip(),"level":pd.to_numeric(df[level],errors="coerce")})
    out["warning"] = pd.to_numeric(df[warning],errors="coerce") if warning else np.nan
    out["danger"] = pd.to_numeric(df[danger],errors="coerce") if danger else np.nan
    out["river"] = df[river].astype(str).str.strip() if river else ""
    out["district"] = df[district].astype(str).str.strip() if district else ""
    out = out.dropna(subset=["timestamp","station","level"]).sort_values(["station","timestamp"])
    out = out.drop_duplicates(["station","timestamp"], keep="last")
    return out


def _features(group: pd.DataFrame) -> pd.DataFrame:
    g = group.sort_values("timestamp").copy()
    s = g["level"]
    g["level_ratio_warning"] = g["level"] / g["warning"].where(g["warning"] > 0)
    g["level_ratio_danger"] = g["level"] / g["danger"].where(g["danger"] > 0)
    for h in (1,3,6,12,24): g[f"rise_{h}h"] = s - s.shift(h)
    g["mean_6h"] = s.rolling(6,min_periods=6).mean()
    g["mean_24h"] = s.rolling(24,min_periods=24).mean()
    g["std_24h"] = s.rolling(24,min_periods=24).std().fillna(0)
    g["max_6h"] = s.rolling(6,min_periods=6).max()
    g["max_24h"] = s.rolling(24,min_periods=24).max()
    g["hour"] = g["timestamp"].dt.hour
    g["month"] = g["timestamp"].dt.month
    # Positive means the station will reach danger in the following 24 hourly observations.
    future = s.shift(-1)[::-1].rolling(24,min_periods=24).max()[::-1]
    g["target"] = ((future >= g["danger"]) & g["danger".notna()]).astype(float)
    g.loc[future.isna() | g["danger"].isna(), "target"] = np.nan
    return g


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="CSV containing Bihar hourly river levels")
    args = ap.parse_args()
    df = _load(Path(args.input))
    pieces = [_features(g) for _,g in df.groupby("station", sort=False)]
    data = pd.concat(pieces, ignore_index=True).dropna(subset=FEATURES+["target"])
    if len(data) < 500 or data["target"].nunique() < 2 or data["target"].sum() < 20:
        raise SystemExit(f"Not enough usable labelled history: rows={len(data)}, positives={int(data.target.sum())}")
    data = data.sort_values("timestamp")
    split = int(len(data)*0.8)
    train, test = data.iloc[:split], data.iloc[split:]
    X_train, y_train = train[FEATURES], train.target.astype(int)
    X_test, y_test = test[FEATURES], test.target.astype(int)
    candidates = {
        "random_forest": RandomForestClassifier(n_estimators=500,max_depth=12,min_samples_leaf=3,class_weight="balanced_subsample",random_state=42,n_jobs=-1),
        "logistic_regression": Pipeline([("scale",StandardScaler()),("model",LogisticRegression(max_iter=2000,class_weight="balanced"))]),
    }
    results = {}
    best_name = None; best_score = -1; best_model = None
    for name, base in candidates.items():
        model = CalibratedClassifierCV(base, method="sigmoid", cv=TimeSeriesSplit(n_splits=3))
        model.fit(X_train,y_train)
        p=model.predict_proba(X_test)[:,1]; pred=(p>=0.5).astype(int)
        metrics={"pr_auc":float(average_precision_score(y_test,p)),"roc_auc":float(roc_auc_score(y_test,p)),"brier":float(brier_score_loss(y_test,p)),"precision":float(precision_score(y_test,p,zero_division=0)),"recall":float(recall_score(y_test,p,zero_division=0)),"f1":float(f1_score(y_test,p,zero_division=0))}
        results[name]=metrics
        if metrics["pr_auc"] > best_score: best_score=metrics["pr_auc"]; best_name=name; best_model=model
    OUT.mkdir(parents=True,exist_ok=True)
    joblib.dump(best_model,OUT/"flood_probability.joblib")
    metadata={"model_version":"bihar-flood-probability-v1","model":best_name,"target":"danger_level_reached_within_next_24_hours","horizon_hours":24,"features":FEATURES,"training_rows":len(train),"test_rows":len(test),"positive_train":int(y_train.sum()),"positive_test":int(y_test.sum()),"training_start":train.timestamp.min().isoformat(),"training_end":train.timestamp.max().isoformat(),"test_start":test.timestamp.min().isoformat(),"test_end":test.timestamp.max().isoformat(),"calibrated":True,"validation":"chronological 80/20 holdout; sigmoid calibration with TimeSeriesSplit on training data","metrics":results,"selected_metrics":results[best_name],"limitations":["Station-level danger-threshold event, not spatial inundation","Requires sufficient continuous hourly history","Does not model upstream rainfall or forecast rainfall unless those features are added"]}
    (OUT/"flood_probability.json").write_text(json.dumps(metadata,indent=2),encoding="utf-8")
    print(json.dumps(metadata,indent=2))

if __name__ == "__main__": main()
