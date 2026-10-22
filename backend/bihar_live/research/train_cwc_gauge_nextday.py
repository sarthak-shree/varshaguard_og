"""Train a research model for first CWC danger-level crossing the next day."""
from __future__ import annotations
import argparse, hashlib, json, sys
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CSV = ROOT / "data/bihar_live/research/cwc_bihar_gauge_history.csv"
MODEL_DIR = ROOT / "models/research"
OUT_DIR = ROOT / "data/bihar_live/research"
STEM = "cwc_bihar_gauge_24h_stage_research"
TARGET = "first_danger_crossing_next_day"
PREDICTIONS = OUT_DIR / f"{STEM}_holdout_predictions.csv"
FOCUS_GAUGES = {
    "003-MGD5PTN": "Patna: Gandhighat",
    "004-MGD4PTN": "Muzaffarpur: Sikandarpur",
}

def sha256_file(path):
    h=hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""):
            h.update(chunk)
    return h.hexdigest()

def f2_threshold(y,p):
    from sklearn.metrics import precision_recall_curve
    precision,recall,thresholds=precision_recall_curve(y.astype(int),p)
    if not len(thresholds): return 0.5
    denom=4*precision[:-1]+recall[:-1]
    f2=np.divide(5*precision[:-1]*recall[:-1],denom,
        out=np.zeros_like(denom),where=denom>0)
    return float(thresholds[int(np.argmax(f2))])

def evaluate(y,p,threshold,baseline):
    from sklearn.metrics import accuracy_score,average_precision_score,brier_score_loss,confusion_matrix,precision_score,recall_score,roc_auc_score
    actual=y.astype(int).to_numpy()
    predicted=(p>=threshold).astype(int)
    def metric(fn,*args,**kwargs):
        try: return round(float(fn(*args,**kwargs)),6)
        except (ValueError,ZeroDivisionError): return None
    return {
        "rows":int(len(actual)),"positive_rows":int(actual.sum()),
        "positive_fraction":round(float(actual.mean()),6),"threshold":round(float(threshold),6),
        "accuracy":metric(accuracy_score,actual,predicted),
        "precision":metric(precision_score,actual,predicted,zero_division=0),
        "recall":metric(recall_score,actual,predicted,zero_division=0),
        "average_precision":metric(average_precision_score,actual,p),
        "prevalence_baseline_average_precision":round(float(actual.mean()),6),
        "roc_auc":metric(roc_auc_score,actual,p),
        "brier_score":metric(brier_score_loss,actual,p),
        "train_prevalence_baseline_brier":metric(brier_score_loss,actual,np.full(len(actual),baseline)),
        "confusion_matrix_labels_0_1":confusion_matrix(actual,predicted,labels=[0,1]).tolist(),
    }

def build_rows(raw):
    required={"station_code","datatype_code","date_ist","min","mean","max","sum","n_obs","name","lat","lon","warning_level","danger_level","highest_flow_level"}
    missing=sorted(required-set(raw.columns))
    if missing: raise ValueError("Missing CSV columns: "+", ".join(missing))
    d=raw.copy()
    d["station_code"]=d.station_code.astype("string").str.strip().str.upper()
    d["date_ist"]=pd.to_datetime(d.date_ist,errors="coerce").dt.normalize()
    for col in ["min","mean","max","sum","n_obs","warning_level","danger_level","highest_flow_level"]:
        d[col]=pd.to_numeric(d[col],errors="coerce")
    d=d.dropna(subset=["station_code","date_ist"])
    sr=d[d.datatype_code.eq("HHS")].copy()
    good=(sr.n_obs.ge(3)&sr.danger_level.notna()&sr.highest_flow_level.notna()
        &sr["min"].ge(sr.danger_level-25)
        &sr["mean"].between(sr.danger_level-20,sr.highest_flow_level+2)
        &sr["max"].between(sr.danger_level-20,sr.highest_flow_level+2)
        &sr["max"].ge(sr["mean"])&sr["max"].ge(sr["min"]))
    stage=sr.loc[good].copy()
    if stage.duplicated(["station_code","date_ist"]).any():
        raise ValueError("Duplicate daily stage rows need source review.")
    stage["stage_mean_margin_m"]=stage["mean"]-stage.danger_level
    stage["stage_max_margin_m"]=stage["max"]-stage.danger_level
    rr=d[d.datatype_code.eq("MPS")].copy()
    rain=rr.loc[rr["sum"].between(0,500)&rr.n_obs.ge(1)].copy()
    if rain.duplicated(["station_code","date_ist"]).any():
        raise ValueError("Duplicate daily rainfall rows need source review.")
    sc=stage.pivot(index="date_ist",columns="station_code",values="stage_mean_margin_m").add_prefix("network_stage_margin_")
    rc=rain.pivot(index="date_ist",columns="station_code",values="sum").add_prefix("network_rainfall_mm_")
    context=sc.join(rc,how="outer").sort_index()

    rows=[]; gauges={}
    for code in sorted(stage.station_code.unique()):
        g=stage[stage.station_code.eq(code)].copy()
        danger=float(g.danger_level.iloc[0])
        g=g.set_index("date_ist").sort_index()
        dates=pd.date_range(g.index.min(),g.index.max(),freq="D",name="date_ist")
        daily=g.reindex(dates)
        r=rain[rain.station_code.eq(code)].set_index("date_ist")["sum"].reindex(dates)
        level=daily["max"]; next_level=level.shift(-1)
        at_risk=level.notna()&next_level.notna()&level.lt(danger)
        x=pd.DataFrame(index=dates)
        x["target_station"]=code
        x["target_stage_mean_margin_m"]=daily.stage_mean_margin_m
        x["target_stage_max_margin_m"]=daily.stage_max_margin_m
        x["target_stage_change_24h_m"]=level-level.shift(1)
        x["target_stage_change_72h_m"]=level-level.shift(3)
        x["target_stage_change_168h_m"]=level-level.shift(7)
        x["target_stage_3day_mean_margin_m"]=level.rolling(3,min_periods=3).mean()-danger
        x["target_stage_n_obs"]=daily.n_obs
        x["target_rainfall_24h_mm"]=r
        x["target_rainfall_72h_mm"]=r.rolling(3,min_periods=3).sum()
        x["target_rainfall_168h_mm"]=r.rolling(7,min_periods=7).sum()
        target_dates=dates+pd.Timedelta(days=1)
        phase=target_dates.dayofyear/365.2425*2*np.pi
        x["target_month_sin"],x["target_month_cos"]=np.sin(phase),np.cos(phase)
        x=x.join(context,how="left")
        x["prediction_date"],x["target_date"]=dates,target_dates
        x[TARGET]=(next_level.ge(danger)).astype("Int64")
        x=x.loc[at_risk].copy()
        x[TARGET]=x[TARGET].astype(int)
        rows.append(x)
        gauges[code]={
            "name":str(g.name.iloc[0]),"lat":float(g.lat.iloc[0]),"lon":float(g.lon.iloc[0]),
            "warning_level_m":round(float(g.warning_level.iloc[0]),3),
            "danger_level_m":round(danger,3),
            "published_highest_flow_level_m":round(float(g.highest_flow_level.iloc[0]),3),
            "quality_screened_stage_days":int(len(g)),"at_risk_observed_day_pairs":int(at_risk.sum()),
        }
    frame=pd.concat(rows,ignore_index=True)
    numeric=[c for c in frame.columns if c not in {"target_station","prediction_date","target_date",TARGET}]
    for col in numeric: frame[col]=pd.to_numeric(frame[col],errors="coerce")
    quality={
        "stage_code":"HHS","rainfall_code":"MPS",
        "raw_stage_rows":int(len(sr)),"quality_stage_rows":int(len(stage)),
        "rejected_stage_rows":int(len(sr)-len(stage)),
        "raw_rainfall_rows":int(len(rr)),"quality_rainfall_rows":int(len(rain)),
        "rejected_rainfall_rows":int(len(rr)-len(rain)),
        "stage_filter":"At least 3 readings/day; daily min >= danger-25m; mean and max in [danger-20m, published highest+2m]; max >= mean and min.",
        "rainfall_filter":"MPS daily sum 0-500mm and at least one reported reading.",
        "target_rule":"Only days still below danger are eligible; positive if the next observed calendar day's maximum reaches danger. Days already at/above danger are excluded.",
        "missing_days_are_not_filled_or_labeled_negative":True,
        "stations_used_as_targets":int(len(gauges)),
        "neighbor_gauges_used_as_same_day_context":int(len(sc.columns)),
    }
    return frame,{"quality":quality,"stations":gauges},numeric

def make_model(name,numeric):
    from sklearn.compose import ColumnTransformer
    from sklearn.ensemble import HistGradientBoostingClassifier,RandomForestClassifier
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import OneHotEncoder,StandardScaler
    steps=[("imputer",SimpleImputer(strategy="median",add_indicator=True))]
    if name=="logistic_regression": steps.append(("scaler",StandardScaler()))
    prep=ColumnTransformer([
        ("numeric",Pipeline(steps),numeric),
        ("station",OneHotEncoder(handle_unknown="ignore",sparse_output=False),["target_station"]),
    ],sparse_threshold=0.0)
    if name=="logistic_regression":
        clf=LogisticRegression(C=0.5,max_iter=2000,solver="lbfgs")
    elif name=="random_forest":
        clf=RandomForestClassifier(n_estimators=250,max_features="sqrt",min_samples_leaf=12,random_state=26071,n_jobs=-1)
    else:
        clf=HistGradientBoostingClassifier(max_iter=160,learning_rate=0.06,max_leaf_nodes=15,min_samples_leaf=40,l2_regularization=1.5,random_state=26071)
    return Pipeline([("preprocess",prep),("classifier",clf)])

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv",type=Path,default=DEFAULT_CSV)
    args=parser.parse_args(); path=args.csv.expanduser().resolve()
    if not path.is_file(): parser.error(f"CWC input CSV not found: {path}")
    try:
        import joblib
        import sklearn
        from sklearn.metrics import average_precision_score,brier_score_loss
    except ImportError as e:
        print("Install backend/requirements.txt first.",file=sys.stderr); raise SystemExit(2) from e
    frame,source_meta,numeric=build_rows(pd.read_csv(path,low_memory=False))
    frame["target_year"]=pd.to_datetime(frame.target_date).dt.year
    train=frame[frame.target_year.le(2015)].copy()
    val=frame[frame.target_year.between(2016,2019)].copy()
    test=frame[frame.target_year.ge(2020)].copy()
    for label,part in [("training",train),("validation",val),("test",test)]:
        if part.empty or part[TARGET].nunique()!=2: parser.error(f"{label} split lacks positive/negative labels.")
    cols=numeric+["target_station"]; prevalence=float(train[TARGET].mean())
    models={}; val_metrics={}
    for name in ["logistic_regression","random_forest","hist_gradient_boosting"]:
        model=make_model(name,numeric); model.fit(train[cols],train[TARGET].astype(int))
        p=model.predict_proba(val[cols])[:,1]
        val_metrics[name]={
            "average_precision":round(float(average_precision_score(val[TARGET],p)),6),
            "validation_prevalence":round(float(val[TARGET].mean()),6),
            "brier_score":round(float(brier_score_loss(val[TARGET],p)),6),
            "train_prevalence_baseline_brier":round(float(brier_score_loss(val[TARGET],np.full(len(val),prevalence))),6)}
        models[name]=(model,p)
    improved=[n for n,m in val_metrics.items() if m["average_precision"]>m["validation_prevalence"] and m["brier_score"]<m["train_prevalence_baseline_brier"]]
    pool=improved or list(val_metrics)
    selected=max(pool,key=lambda n:(val_metrics[n]["average_precision"],-val_metrics[n]["brier_score"]))
    threshold=f2_threshold(val[TARGET],models[selected][1])
    fit=pd.concat([train,val],ignore_index=True)
    model=make_model(selected,numeric); model.fit(fit[cols],fit[TARGET].astype(int))
    ptest=model.predict_proba(test[cols])[:,1]
    metrics=evaluate(test[TARGET],ptest,threshold,float(fit[TARGET].mean()))
    focus={}
    for code,label in FOCUS_GAUGES.items():
        mask=test.target_station.eq(code).to_numpy()
        focus[code]={"label":label,**evaluate(test.loc[mask,TARGET],ptest[mask],threshold,
            float(fit.loc[fit.target_station.eq(code),TARGET].mean()))}
    MODEL_DIR.mkdir(parents=True,exist_ok=True); OUT_DIR.mkdir(parents=True,exist_ok=True)
    artifact=MODEL_DIR/f"{STEM}.joblib"; meta_path=MODEL_DIR/f"{STEM}.metadata.json"
    joblib.dump(model,artifact,compress=3)
    pred=test[["target_station","prediction_date","target_date",TARGET]].copy()
    pred["predicted_probability"]=ptest; pred["predicted_at_validation_f2_threshold"]=(ptest>=threshold).astype(int)
    pred.to_csv(PREDICTIONS,index=False)
    metadata={
        "model_name":"VarshaGuard Bihar CWC first-crossing next-day gauge research model",
        "trained_at_utc":datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "training_source":path.name,"source_sha256":sha256_file(path),
        "source_upstream":"CWC Flood Forecast System observations mirrored as Parquet by diagram-chasing/cwc-flood-forecasts",
        "source_urls":["https://ffs.india-water.gov.in/","https://github.com/diagram-chasing/cwc-flood-forecasts","https://diagram-chasing.github.io/cwc-flood-forecasts/daily.parquet"],
        "source_license_note":"Mirror states Open Database License and requests CWC attribution; verify terms before redistribution.",
        "target_column":TARGET,
        "target_definition":"For an observed gauge-day still below danger, predict whether the next observed calendar day's maximum stage reaches the published danger level.",
        "forecast_horizon":"Next calendar day; source timestamps do not establish an exact rolling 24-hour issue time.",
        "geographic_resolution":"Pooled model for 13 nearby Bihar CWC gauges; focus outputs include Gandhighat (Patna) and Sikandarpur (Muzaffarpur). Same-day readings across the local gauge network are predictors.",
        "features":cols,"data_quality":source_meta,
        "runtime_sklearn_version":sklearn.__version__,
        "split":{"training_target_years":"through 2015","validation_target_years":"2016-2019","untouched_test_target_years":"2020 through latest observed target day",
            "training_rows":int(len(train)),"training_first_crossings":int(train[TARGET].sum()),
            "validation_rows":int(len(val)),"validation_first_crossings":int(val[TARGET].sum()),
            "test_rows":int(len(test)),"test_first_crossings":int(test[TARGET].sum())},
        "candidate_validation_metrics":val_metrics,"selected_model":selected,
        "threshold_selection":"F2 maximized on 2016-2019 validation data","decision_threshold":round(float(threshold),6),
        "test_metrics":metrics,"focus_gauge_test_metrics":focus,
        "operational_eligible":False,"loaded_by_dashboard_server":True,
        "warning":"Research-only gauge threshold estimate exposed in Bihar Live using current CWC stage and rainfall observations. It does not predict grid-cell inundation, extent, or depth. Live feature coverage, probability calibration, gauge datums, and local performance require expert validation before any public-safety use.",
        "artifact_path":str(artifact.relative_to(ROOT)),"holdout_predictions_path":str(PREDICTIONS.relative_to(ROOT))}
    meta_path.write_text(json.dumps(metadata,indent=2),encoding="utf-8")
    print(json.dumps({"selected_model":selected,"training_rows":len(train),"training_first_crossings":int(train[TARGET].sum()),
        "validation_rows":len(val),"validation_first_crossings":int(val[TARGET].sum()),
        "test_rows":len(test),"test_first_crossings":int(test[TARGET].sum()),
        "test_metrics":metrics,"focus_gauge_test_metrics":focus,"artifact":str(artifact),
        "metadata":str(meta_path),"holdout_predictions":str(PREDICTIONS)},indent=2))
    return 0

if __name__=="__main__": raise SystemExit(main())


