"""Train and evaluate a rolling 24-hour CWC warning-level crossing model."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CSV = ROOT / "data" / "bihar_live" / "research" / "cwc_bihar_gauge_hourly.csv"
MODEL_DIR = ROOT / "models" / "research"
OUT_DIR = ROOT / "data" / "bihar_live" / "research"
MODEL_STEM = "cwc_bihar_gauge_24h_stage_research"
TARGET = "warning_crossing_within_24h"
FOCUS_GAUGES = {"003-MGD5PTN": "Patna: Gandhighat", "004-MGD4PTN": "Muzaffarpur: Sikandarpur"}
STAGE_LAGS_HOURS = (6, 12, 24, 48, 72)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _quality_observations(raw: pd.DataFrame) -> tuple[dict[str, pd.DataFrame], dict[str, pd.DataFrame], dict, dict]:
    required = {
        "station_code", "datatype_code", "timestamp_ist", "value", "source_type", "name",
        "lat", "lon", "warning_level", "danger_level", "highest_flow_level",
    }
    missing = sorted(required - set(raw.columns))
    if missing:
        raise ValueError("Missing hourly CSV columns: " + ", ".join(missing))
    d = raw.copy()
    d["station_code"] = d.station_code.astype("string").str.strip().str.upper()
    d["datatype_code"] = d.datatype_code.astype("string").str.strip().str.upper()
    d["timestamp_ist"] = pd.to_datetime(d.timestamp_ist, errors="coerce")
    for column in ["value", "warning_level", "danger_level", "highest_flow_level", "lat", "lon"]:
        d[column] = pd.to_numeric(d[column], errors="coerce")
    d = d.dropna(subset=["station_code", "timestamp_ist", "value"])
    metadata = {}
    for code, group in d.groupby("station_code"):
        row = group.iloc[0]
        metadata[code] = {
            "name": str(row["name"]), "lat": float(row.lat), "lon": float(row.lon),
            "warning_level_m": float(row.warning_level), "danger_level_m": float(row.danger_level),
            "highest_flow_level_m": float(row.highest_flow_level),
        }

    stage = d[d.datatype_code.eq("HHS")].copy()
    stage = stage[
        stage.value.ge(stage.danger_level - 25)
        & stage.value.le(stage.highest_flow_level + 2)
    ]
    # Duplicate observations at one station and timestamp are collapsed so one
    # repeated export row cannot increase the model's sample weight.
    stage = (
        stage.groupby(["station_code", "timestamp_ist"], as_index=False)
        .agg(value=("value", "median"), warning_level=("warning_level", "first"),
             danger_level=("danger_level", "first"), highest_flow_level=("highest_flow_level", "first"))
        .sort_values(["station_code", "timestamp_ist"])
    )
    rainfall = d[d.datatype_code.eq("MPS") & d.value.between(0, 500)].copy()
    rainfall = (
        rainfall.groupby(["station_code", "timestamp_ist"], as_index=False)
        .agg(value=("value", "sum"))
        .sort_values(["station_code", "timestamp_ist"])
    )
    stages = {code: group.reset_index(drop=True) for code, group in stage.groupby("station_code")}
    rains = {code: group.reset_index(drop=True) for code, group in rainfall.groupby("station_code")}
    quality = {
        "source_rows": int(len(d)), "source_stage_rows": int(d.datatype_code.eq("HHS").sum()),
        "quality_stage_rows": int(len(stage)), "rejected_stage_rows": int(d.datatype_code.eq("HHS").sum() - len(stage)),
        "source_rain_rows": int(d.datatype_code.eq("MPS").sum()), "quality_rain_rows": int(len(rainfall)),
        "stage_filter": "CWC HHS only; stage from 25m below warning threshold through published highest flow +2m; duplicates at a station-time are collapsed.",
        "rain_filter": "CWC MPS only; values 0-500mm; duplicates at a station-time are summed.",
    }
    return stages, rains, metadata, quality


def _at_or_before(times_ns: np.ndarray, values: np.ndarray, target_ns: int, tolerance_ns: int):
    pos = int(np.searchsorted(times_ns, target_ns, side="right") - 1)
    if pos < 0 or target_ns - int(times_ns[pos]) > tolerance_ns:
        return np.nan
    return float(values[pos])


def _rain_window(times_ns: np.ndarray | None, values: np.ndarray | None, issue_ns: int, hours: int, min_count: int):
    if times_ns is None or values is None or not len(times_ns):
        return np.nan
    left = int(np.searchsorted(times_ns, issue_ns - hours * 3_600_000_000_000, side="right"))
    right = int(np.searchsorted(times_ns, issue_ns, side="right"))
    if right - left < min_count:
        return np.nan
    return float(values[left:right].sum())


def build_rows(raw: pd.DataFrame) -> tuple[pd.DataFrame, dict, list[str]]:
    stages, rains, station_meta, quality = _quality_observations(raw)
    station_codes = sorted(station_meta)
    # pandas may store parsed CSV timestamps in microseconds. Normalize all
    # integer arithmetic to nanoseconds before applying time-window constants.
    stage_arrays = {
        code: (frame.timestamp_ist.to_numpy(dtype="datetime64[ns]").astype("int64"), frame.value.to_numpy(dtype=float))
        for code, frame in stages.items()
    }
    rain_arrays = {
        code: (frame.timestamp_ist.to_numpy(dtype="datetime64[ns]").astype("int64"), frame.value.to_numpy(dtype=float))
        for code, frame in rains.items()
    }
    rows = []
    issue_ns_step = 6 * 3_600_000_000_000
    horizon_ns = 24 * 3_600_000_000_000
    coverage_ns = 20 * 3_600_000_000_000
    tolerance_ns = 3 * 3_600_000_000_000
    station_counts = {}

    for code in station_codes:
        target_frame = stages.get(code)
        if target_frame is None or target_frame.empty:
            continue
        target_times, target_values = stage_arrays[code]
        warning = station_meta[code]["warning_level_m"]
        danger = station_meta[code]["danger_level_m"]
        mask = (target_frame.timestamp_ist.dt.hour.to_numpy() % 6 == 0) & (target_frame.timestamp_ist.dt.minute.to_numpy() == 0)
        issue_indices = np.flatnonzero(mask)
        produced = positives = 0

        for index in issue_indices:
            issue_ns = int(target_times[index])
            current_value = float(target_values[index])
            # Once the CWC warning threshold is already reached, this is not a
            # pre-warning prediction sample.
            if current_value >= warning:
                continue
            future_start = int(np.searchsorted(target_times, issue_ns, side="right"))
            future_end = int(np.searchsorted(target_times, issue_ns + horizon_ns, side="right"))
            if future_end - future_start < 18:
                continue
            if int(target_times[future_end - 1]) < issue_ns + coverage_ns:
                continue
            future_peak = float(target_values[future_start:future_end].max())
            issue_timestamp = pd.Timestamp(issue_ns, unit="ns")

            feature = {
                "target_station": code,
                "target_stage_margin_warning_m": current_value - warning,
                "target_stage_margin_danger_m": current_value - danger,
                "target_stage_value_m": current_value,
                "target_hour_sin": float(np.sin((issue_timestamp.hour / 24) * 2 * np.pi)),
                "target_hour_cos": float(np.cos((issue_timestamp.hour / 24) * 2 * np.pi)),
                "target_month_sin": float(np.sin(issue_timestamp.dayofyear / 365.2425 * 2 * np.pi)),
                "target_month_cos": float(np.cos(issue_timestamp.dayofyear / 365.2425 * 2 * np.pi)),
                "target_rainfall_24h_mm": _rain_window(*rain_arrays.get(code, (None, None)), issue_ns, 24, 2),
                "target_rainfall_72h_mm": _rain_window(*rain_arrays.get(code, (None, None)), issue_ns, 72, 4),
                "target_rainfall_24h_observations": np.nan,
            }
            target_rain_times, _ = rain_arrays.get(code, (None, None))
            if target_rain_times is not None and len(target_rain_times):
                rt = target_rain_times
                left = int(np.searchsorted(rt, issue_ns - 24 * 3_600_000_000_000, side="right"))
                right = int(np.searchsorted(rt, issue_ns, side="right"))
                feature["target_rainfall_24h_observations"] = right - left

            for lag in STAGE_LAGS_HOURS:
                lag_value = _at_or_before(target_times, target_values, issue_ns - lag * 3_600_000_000_000, tolerance_ns)
                feature[f"target_stage_change_{lag}h_m"] = current_value - lag_value if np.isfinite(lag_value) else np.nan
            prior_day_left = int(np.searchsorted(target_times, issue_ns - 24 * 3_600_000_000_000, side="right"))
            prior_day_right = int(np.searchsorted(target_times, issue_ns, side="right"))
            prior_day = target_values[prior_day_left:prior_day_right]
            feature["target_stage_mean_24h_m"] = float(prior_day.mean()) if len(prior_day) >= 12 else np.nan
            feature["target_stage_max_24h_m"] = float(prior_day.max()) if len(prior_day) >= 12 else np.nan

            for network_code in station_codes:
                network_values = stage_arrays.get(network_code)
                value = np.nan
                age_hours = np.nan
                if network_values is not None:
                    nt, nv = network_values
                    network_value = _at_or_before(nt, nv, issue_ns, tolerance_ns)
                    pos = int(np.searchsorted(nt, issue_ns, side="right") - 1)
                    if np.isfinite(network_value):
                        value = network_value - station_meta[network_code]["warning_level_m"]
                        age_hours = (issue_ns - int(nt[pos])) / 3_600_000_000_000
                feature[f"network_warning_margin_{network_code}_m"] = value
                feature[f"network_stage_age_{network_code}_h"] = age_hours

            feature[TARGET] = int(future_peak >= warning)
            feature["issue_time"] = issue_timestamp
            feature["forecast_valid_until"] = issue_timestamp + pd.Timedelta(hours=24)
            rows.append(feature)
            produced += 1
            positives += feature[TARGET]
        station_counts[code] = {"issue_rows": int(produced), "positive_warning_crossings": int(positives)}

    if not rows:
        raise ValueError("No rolling 24-hour issue rows passed coverage and quality checks.")
    frame = pd.DataFrame(rows).sort_values("issue_time").reset_index(drop=True)
    numeric = [column for column in frame.columns if column not in {"target_station", "issue_time", "forecast_valid_until", TARGET}]
    frame[numeric] = frame[numeric].apply(pd.to_numeric, errors="coerce")
    quality.update({
        "issue_sampling": "One issue per gauge every 6 hours at a reported HHS observation time.",
        "target_rule": "Among issue times still below the published CWC warning level, positive if any valid HHS observation in (issue time, issue time +24h] reaches that warning level.",
        "future_coverage_rule": "Require at least 18 valid stage observations in the next 24h and a final observation at least 20h after issue time; missing/low-coverage horizons are excluded.",
        "missing_future_rows_are_not_labeled_negative": True,
        "stations_used": int(len(station_meta)),
        "station_issue_counts": station_counts,
    })
    return frame, {"quality": quality, "stations": station_meta}, numeric


def f2_threshold(y: pd.Series, probability: np.ndarray) -> float:
    from sklearn.metrics import precision_recall_curve
    precision, recall, thresholds = precision_recall_curve(y.astype(int), probability)
    if not len(thresholds):
        return 0.5
    denominator = 4 * precision[:-1] + recall[:-1]
    f2 = np.divide(5 * precision[:-1] * recall[:-1], denominator, out=np.zeros_like(denominator), where=denominator > 0)
    return float(thresholds[int(np.argmax(f2))])


def evaluate(y: pd.Series, probability: np.ndarray, threshold: float, baseline: float) -> dict:
    from sklearn.metrics import average_precision_score, brier_score_loss, confusion_matrix, precision_score, recall_score, roc_auc_score
    actual = y.astype(int).to_numpy()
    predicted = (probability >= threshold).astype(int)

    def metric(function, *args, **kwargs):
        try:
            return round(float(function(*args, **kwargs)), 6)
        except (ValueError, ZeroDivisionError):
            return None

    return {
        "rows": int(len(actual)), "positive_rows": int(actual.sum()),
        "positive_fraction": round(float(actual.mean()), 6), "threshold": round(float(threshold), 6),
        "precision": metric(precision_score, actual, predicted, zero_division=0),
        "recall": metric(recall_score, actual, predicted, zero_division=0),
        "average_precision": metric(average_precision_score, actual, probability),
        "prevalence_baseline_average_precision": round(float(actual.mean()), 6),
        "roc_auc": metric(roc_auc_score, actual, probability),
        "brier_score": metric(brier_score_loss, actual, probability),
        "training_prevalence_baseline_brier": metric(brier_score_loss, actual, np.full(len(actual), baseline)),
        "confusion_matrix_labels_0_1": confusion_matrix(actual, predicted, labels=[0, 1]).tolist(),
    }


def make_model(name: str, numeric: list[str]):
    from sklearn.compose import ColumnTransformer
    from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import OneHotEncoder, StandardScaler
    numeric_steps = [("imputer", SimpleImputer(strategy="median", add_indicator=True))]
    if name == "logistic_regression":
        numeric_steps.append(("scale", StandardScaler()))
    prep = ColumnTransformer([
        ("numeric", Pipeline(numeric_steps), numeric),
        ("station", OneHotEncoder(handle_unknown="ignore", sparse_output=False), ["target_station"]),
    ], sparse_threshold=0.0)
    if name == "logistic_regression":
        classifier = LogisticRegression(C=0.4, max_iter=2000, solver="lbfgs")
    elif name == "random_forest":
        classifier = RandomForestClassifier(n_estimators=220, max_features="sqrt", min_samples_leaf=18, random_state=26071, n_jobs=-1)
    else:
        classifier = HistGradientBoostingClassifier(max_iter=120, learning_rate=0.05, max_leaf_nodes=11, min_samples_leaf=35, l2_regularization=2.0, random_state=26071)
    return Pipeline([("preprocess", prep), ("classifier", classifier)])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    args = parser.parse_args()
    path = args.csv.expanduser().resolve()
    if not path.is_file():
        parser.error(f"Hourly CWC input CSV not found: {path}. Run fetch_cwc_bihar_hourly.py first.")
    try:
        import joblib
        import sklearn
        from sklearn.metrics import average_precision_score, brier_score_loss
    except ImportError as error:
        print("Install requirements.txt first.", file=sys.stderr)
        raise SystemExit(2) from error

    frame, source_meta, numeric = build_rows(pd.read_csv(path, low_memory=False))
    frame["issue_year"] = pd.to_datetime(frame.issue_time).dt.year
    frame["forecast_end"] = pd.to_datetime(frame.forecast_valid_until)
    train = frame[(frame.issue_year <= 2024) & (frame.forecast_end < "2025-01-01")].copy()
    validation = frame[(frame.issue_year == 2025) & (frame.forecast_end < "2026-01-01")].copy()
    test = frame[(frame.issue_year == 2026)].copy()
    for label, part in [("training", train), ("validation", validation), ("test", test)]:
        if part.empty or part[TARGET].nunique() != 2:
            parser.error(f"{label} split needs both positive and negative labels; got {len(part)} rows.")
    columns = numeric + ["target_station"]
    prevalence = float(train[TARGET].mean())
    candidates = {}
    validation_metrics = {}
    for name in ["logistic_regression", "random_forest", "hist_gradient_boosting"]:
        candidate = make_model(name, numeric)
        candidate.fit(train[columns], train[TARGET].astype(int))
        probability = candidate.predict_proba(validation[columns])[:, 1]
        baseline = float(brier_score_loss(validation[TARGET], np.full(len(validation), prevalence)))
        validation_metrics[name] = {
            "average_precision": round(float(average_precision_score(validation[TARGET], probability)), 6),
            "validation_prevalence": round(float(validation[TARGET].mean()), 6),
            "brier_score": round(float(brier_score_loss(validation[TARGET], probability)), 6),
            "training_prevalence_baseline_brier": round(baseline, 6),
            "rows": int(len(validation)), "positive_rows": int(validation[TARGET].sum()),
        }
        candidates[name] = (candidate, probability)
    improved = [name for name, metrics in validation_metrics.items()
                if metrics["average_precision"] > metrics["validation_prevalence"]
                and metrics["brier_score"] < metrics["training_prevalence_baseline_brier"]]
    pool = improved or list(validation_metrics)
    selected = max(pool, key=lambda name: (validation_metrics[name]["average_precision"], -validation_metrics[name]["brier_score"]))
    threshold = f2_threshold(validation[TARGET], candidates[selected][1])

    fit = pd.concat([train, validation], ignore_index=True)
    test_model = make_model(selected, numeric)
    test_model.fit(fit[columns], fit[TARGET].astype(int))
    test_probability = test_model.predict_proba(test[columns])[:, 1]
    test_metrics = evaluate(test[TARGET], test_probability, threshold, float(fit[TARGET].mean()))
    focus_metrics = {}
    for code, label in FOCUS_GAUGES.items():
        mask = test.target_station.eq(code)
        focus = test.loc[mask]
        if focus.empty or focus[TARGET].nunique() != 2:
            focus_metrics[code] = {"label": label, "rows": int(len(focus)), "positive_rows": int(focus[TARGET].sum()) if len(focus) else 0,
                                   "note": "This holdout period does not contain both outcomes for this gauge; local skill cannot be estimated."}
        else:
            focus_metrics[code] = {"label": label, **evaluate(focus[TARGET], test_probability[mask.to_numpy()], threshold,
                float(fit.loc[fit.target_station.eq(code), TARGET].mean()))}

    # Deployment artifact uses every quality-screened historical label available;
    # all published holdout metrics above come from the untouched 2026 test split.
    final_model = make_model(selected, numeric)
    final_model.fit(frame[columns], frame[TARGET].astype(int))
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    artifact = MODEL_DIR / f"{MODEL_STEM}.joblib"
    metadata_path = MODEL_DIR / f"{MODEL_STEM}.metadata.json"
    joblib.dump(final_model, artifact, compress=3)
    pred_path = OUT_DIR / f"{MODEL_STEM}_holdout_predictions.csv"
    predictions = test[["target_station", "issue_time", "forecast_valid_until", TARGET]].copy()
    predictions["predicted_probability"] = test_probability
    predictions["predicted_at_validation_f2_threshold"] = (test_probability >= threshold).astype(int)
    predictions.to_csv(pred_path, index=False)
    metadata = {
        "model_name": "VarshaGuard Bihar CWC rolling 24-hour warning-level crossing research model",
        "trained_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "training_source": path.name, "source_sha256": sha256_file(path),
        "source_upstream": "CWC Flood Forecast System hourly observations mirrored by diagram-chasing/cwc-flood-forecasts",
        "source_urls": ["https://ffs.india-water.gov.in/", "https://github.com/diagram-chasing/cwc-flood-forecasts",
                        "https://diagram-chasing.github.io/cwc-flood-forecasts/hourly.parquet"],
        "source_license_note": "The mirror states Open Database License and requests CWC attribution; confirm terms before redistribution.",
        "target_column": TARGET,
        "target_definition": "At a six-hourly issue time still below the published CWC warning level, estimate whether any valid gauge observation in the next rolling 24 hours will reach that warning level.",
        "forecast_horizon": "Rolling 24 hours from latest accepted CWC stage observation; this is a gauge warning-level crossing estimate, not an inundation probability.",
        "geographic_resolution": "Pooled model across 13 CWC gauges in Bihar, with station identity and same-time observed nearby stage/rainfall context. Dashboard focuses on Gandhighat (Patna) and Sikandarpur (Muzaffarpur).",
        "features": columns, "data_quality": source_meta,
        "runtime_sklearn_version": sklearn.__version__,
        "split": {
            "training_issue_years": "through 2024; training forecast horizons end before 2025",
            "validation_issue_year": 2025, "untouched_test_issue_year": 2026,
            "training_rows": int(len(train)), "training_positive_rows": int(train[TARGET].sum()),
            "validation_rows": int(len(validation)), "validation_positive_rows": int(validation[TARGET].sum()),
            "test_rows": int(len(test)), "test_positive_rows": int(test[TARGET].sum()),
            "deployment_training_rows": int(len(frame)), "deployment_positive_rows": int(frame[TARGET].sum()),
        },
        "candidate_validation_metrics": validation_metrics, "selected_model": selected,
        "threshold_selection": "F2 maximized on temporally separate 2025 validation data",
        "decision_threshold": round(float(threshold), 6),
        "test_metrics": test_metrics, "focus_gauge_test_metrics": focus_metrics,
        "operational_eligible": False, "loaded_by_dashboard_server": True,
        "warning": "Research-only probability estimate for reaching a CWC gauge warning level within 24 hours. Three years of archived hourly data provide limited independent flood seasons, and focus-gauge event counts are sparse. This is not a block/grid inundation prediction or an official warning; validate with CWC/IMD and disaster-management experts before public-safety use.",
        "artifact_path": str(artifact.relative_to(ROOT)), "holdout_predictions_path": str(pred_path.relative_to(ROOT)),
    }
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(json.dumps({"selected_model": selected, "training_rows": len(train), "training_positives": int(train[TARGET].sum()),
                      "validation_rows": len(validation), "validation_positives": int(validation[TARGET].sum()),
                      "test_rows": len(test), "test_positives": int(test[TARGET].sum()), "test_metrics": test_metrics,
                      "focus_gauge_test_metrics": focus_metrics, "artifact": str(artifact), "metadata": str(metadata_path)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
