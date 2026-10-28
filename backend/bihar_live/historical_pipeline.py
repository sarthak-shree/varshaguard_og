"""Persistent observation store and leakage-aware supervised forecast training.

Data rows are observations, not predictions. UTC timestamps are the canonical join key;
station, source, units and quality metadata are retained. Local SQLite is convenient for
development, but on serverless hosts set VARSHAGUARD_HISTORY_DB to a mounted persistent
volume or use an external database adapter. Never rely on ephemeral deployment storage.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor, HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.pipeline import make_pipeline
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler
import joblib

SCHEMA_VERSION = 2
IST = timezone(timedelta(hours=5, minutes=30))
DEFAULT_DB = Path(os.environ.get("VARSHAGUARD_HISTORY_DB", "data/bihar_live/history.sqlite3"))
RAIN_HORIZONS = (1, 3, 6, 12, 24)
STAGE_HORIZONS = (1, 3, 6, 12)
MIN_TRAIN_ROWS = 120
MIN_TEST_ROWS = 24
MAX_FIT_ROWS = 100_000
TIME_FEATURE_COLUMNS = ["hour_sin", "hour_cos", "dayofyear_sin", "dayofyear_cos"]
RAIN_FEATURE_COLUMNS = [*(f"rain_lag_{lag}h_mm" for lag in (1, 3, 6, 12, 24)), *TIME_FEATURE_COLUMNS]
STAGE_FEATURE_COLUMNS = [*(f"stage_lag_{lag}h_m" for lag in (1, 3, 6, 12, 24)), "stage_rate_3h_m_per_h", "stage_rate_12h_m_per_h", *(f"rain_lag_{lag}h_mm" for lag in (1, 3, 6, 12, 24)), *TIME_FEATURE_COLUMNS]
FEATURE_COLUMNS = [
    "rain_lag_1h_mm", "rain_lag_3h_mm", "rain_lag_6h_mm",
    "rain_lag_12h_mm", "rain_lag_24h_mm",
    "stage_lag_1h_m", "stage_lag_3h_m", "stage_lag_6h_m",
    "stage_lag_12h_m", "stage_lag_24h_m",
    "stage_rate_3h_m_per_h", "stage_rate_12h_m_per_h",
    "hour_sin", "hour_cos", "dayofyear_sin", "dayofyear_cos",
]


def _utc_iso(value) -> str:
    stamp = pd.Timestamp(value)
    if pd.isna(stamp):
        raise ValueError("timestamp is not parseable")
    if stamp.tzinfo is None:
        stamp = stamp.tz_localize("Asia/Kolkata")
    return stamp.tz_convert("UTC").isoformat()


def connect(db_path: str | Path = DEFAULT_DB) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=20)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS observations (
            station_id TEXT NOT NULL,
            observed_at_utc TEXT NOT NULL,
            source TEXT NOT NULL,
            source_station_id TEXT,
            source_kind TEXT NOT NULL DEFAULT 'observed' CHECK(source_kind = 'observed'),
            variable TEXT NOT NULL CHECK(variable IN ('rainfall_mm','stage_m')),
            value REAL NOT NULL,
            unit TEXT NOT NULL,
            quality_flag TEXT NOT NULL DEFAULT 'good',
            source_timestamp TEXT,
            ingested_at_utc TEXT NOT NULL,
            schema_version INTEGER NOT NULL,
            PRIMARY KEY(station_id, observed_at_utc, source, variable)
        )
    """)
    existing_columns = {row[1] for row in conn.execute("PRAGMA table_info(observations)").fetchall()}
    if "source_station_id" not in existing_columns:
        conn.execute("ALTER TABLE observations ADD COLUMN source_station_id TEXT")
    if "source_kind" not in existing_columns:
        conn.execute("ALTER TABLE observations ADD COLUMN source_kind TEXT NOT NULL DEFAULT 'observed'")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_obs_station_time ON observations(station_id, observed_at_utc)")
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    conn.commit()
    return conn


def ingest_observations(rows: Iterable[dict], db_path: str | Path = DEFAULT_DB) -> dict:
    """Idempotently ingest normalised rows; malformed/physically invalid rows are rejected."""
    accepted, rejected = 0, 0
    now = datetime.now(timezone.utc).isoformat()
    values = []
    for row in rows:
        try:
            station = str(row["station_id"]).strip()
            source = str(row["source"]).strip()
            variable = str(row["variable"]).strip()
            value = float(row["value"])
            unit = str(row["unit"]).strip()
            source_kind = str(row.get("source_kind", "observed")).strip().lower()
            if source_kind != "observed":
                raise ValueError("forecast inputs cannot be stored as observation labels")
            source_station_id = str(row.get("source_station_id") or row.get("station_id")).strip()
            timestamp = _utc_iso(row["observed_at"])
            quality = str(row.get("quality_flag", "good")).strip().lower()
            if not station or not source or not unit or variable not in {"rainfall_mm", "stage_m"}:
                raise ValueError("missing identity/unit or unsupported variable")
            if not math.isfinite(value) or (variable == "rainfall_mm" and value < 0):
                raise ValueError("invalid physical value")
            if quality not in {"good", "suspect", "bad", "missing", "stale"}:
                raise ValueError("invalid quality flag")
            values.append((station, timestamp, source, source_station_id, source_kind, variable, value, unit, quality,
                           str(row.get("source_timestamp") or row["observed_at"]), now, SCHEMA_VERSION))
            accepted += 1
        except (KeyError, TypeError, ValueError, OverflowError):
            rejected += 1
    with connect(db_path) as conn:
        before = conn.total_changes
        conn.executemany("""
            INSERT INTO observations
            (station_id, observed_at_utc, source, source_station_id, source_kind, variable, value, unit, quality_flag,
             source_timestamp, ingested_at_utc, schema_version)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(station_id, observed_at_utc, source, variable) DO UPDATE SET
                source_station_id=excluded.source_station_id, source_kind=excluded.source_kind,
                value=excluded.value, unit=excluded.unit, quality_flag=excluded.quality_flag,
                source_timestamp=excluded.source_timestamp, ingested_at_utc=excluded.ingested_at_utc,
                schema_version=excluded.schema_version
        """, values)
        changed = conn.total_changes - before
        total = conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0]
    return {"accepted_input_rows": accepted, "rejected_input_rows": rejected,
            "database_changes": changed, "stored_rows": total, "schema_version": SCHEMA_VERSION}


def export_observations(db_path: str | Path = DEFAULT_DB) -> pd.DataFrame:
    with connect(db_path) as conn:
        rows = conn.execute("""
            SELECT station_id, observed_at_utc, source, source_station_id, source_kind, variable, value, unit,
                   quality_flag, source_timestamp, ingested_at_utc, schema_version
            FROM observations ORDER BY station_id, observed_at_utc, variable
        """).fetchall()
    return pd.DataFrame([dict(row) for row in rows])


def build_supervised_rows(observations: pd.DataFrame, max_gap_hours: int = 1) -> pd.DataFrame:
    """Build exact-hour lag features and future labels without interpolation.

    This implementation vectorizes timestamp shifts per station. A full hourly index is
    used to preserve missing hours as NaN, so a lag/label is available only at the exact
    requested timestamp; gaps are never silently bridged.
    """
    required = {"station_id", "observed_at", "variable", "value", "quality_flag"}
    if not required.issubset(observations.columns):
        raise ValueError(f"observations missing columns: {sorted(required - set(observations.columns))}")
    frame = observations.copy()
    frame["observed_at"] = pd.to_datetime(frame["observed_at"], utc=True, errors="coerce")
    frame["value"] = pd.to_numeric(frame["value"], errors="coerce")
    frame = frame.dropna(subset=["station_id", "observed_at", "value"])
    frame = frame[frame["quality_flag"].fillna("bad").str.lower().eq("good")]
    frame = frame[frame["variable"].isin(["rainfall_mm", "stage_m"])]
    if frame.empty:
        return pd.DataFrame()

    keys = ["station_id", "observed_at", "variable"]
    # Vectorized ambiguity check: reject every row belonging to a conflicting key.
    distinct_counts = frame.groupby(keys, dropna=False)["value"].transform("nunique")
    frame = frame.loc[distinct_counts.le(1)].drop_duplicates(keys, keep="first")
    if frame.empty:
        return pd.DataFrame()

    rows = []
    for station, station_rows in frame.groupby("station_id", sort=False):
        wide = station_rows.pivot_table(
            index="observed_at", columns="variable", values="value", aggfunc="first"
        ).sort_index()
        if wide.empty:
            continue
        # Preserve the source cadence's minute offset (e.g. :30 UTC for IST clock hours).
        hourly_index = pd.date_range(wide.index.min(), wide.index.max(), freq="h", tz="UTC")
        wide = wide.reindex(hourly_index)
        rain = wide["rainfall_mm"] if "rainfall_mm" in wide else pd.Series(np.nan, index=hourly_index)
        stage = wide["stage_m"] if "stage_m" in wide else pd.Series(np.nan, index=hourly_index)
        local = hourly_index.tz_convert("Asia/Kolkata")
        result = pd.DataFrame({
            "station_id": str(station),
            "issue_time_utc": hourly_index.map(lambda x: x.isoformat()),
            "issue_time_ist": local.map(lambda x: x.isoformat()),
            "hour_sin": np.sin(2 * np.pi * local.hour / 24),
            "hour_cos": np.cos(2 * np.pi * local.hour / 24),
            "dayofyear_sin": np.sin(2 * np.pi * local.dayofyear / 366),
            "dayofyear_cos": np.cos(2 * np.pi * local.dayofyear / 366),
        }, index=hourly_index)
        for lag in (1, 3, 6, 12, 24):
            result[f"stage_lag_{lag}h_m"] = stage.shift(lag).to_numpy()
            result[f"rain_lag_{lag}h_mm"] = rain.shift(lag).to_numpy()
        result["stage_rate_3h_m_per_h"] = (
            result["stage_lag_1h_m"] - result["stage_lag_3h_m"]
        ) / 2
        result["stage_rate_12h_m_per_h"] = (
            result["stage_lag_1h_m"] - result["stage_lag_12h_m"]
        ) / 11
        for horizon in RAIN_HORIZONS:
            result[f"target_rainfall_{horizon}h_mm"] = rain.shift(-horizon).to_numpy()
        for horizon in STAGE_HORIZONS:
            result[f"target_stage_{horizon}h_m"] = stage.shift(-horizon).to_numpy()
        history_columns = [
            *(f"rain_lag_{lag}h_mm" for lag in (1, 3, 6, 12, 24)),
            *(f"stage_lag_{lag}h_m" for lag in (1, 3, 6, 12, 24)),
        ]
        result = result.loc[result[history_columns].notna().any(axis=1)]
        if not result.empty:
            rows.append(result.reset_index(drop=True))
    return pd.concat(rows, ignore_index=True).sort_values("issue_time_utc").reset_index(drop=True) if rows else pd.DataFrame()

def chronological_split(data: pd.DataFrame, train_fraction: float = 0.70, validation_fraction: float = 0.15,
                        embargo_hours: int = 24):
    """Split on unique timestamps with a horizon-sized embargo between partitions."""
    if not 0 < train_fraction < 1 or not 0 < validation_fraction < 1 or train_fraction + validation_fraction >= 1:
        raise ValueError("fractions must be positive and sum to less than one")
    if embargo_hours < 0:
        raise ValueError("embargo_hours must be non-negative")
    ordered = data.copy()
    ordered["_split_timestamp"] = pd.to_datetime(ordered["issue_time_utc"], utc=True, errors="coerce")
    ordered = ordered.dropna(subset=["_split_timestamp"]).sort_values("_split_timestamp").reset_index(drop=True)
    unique_times = pd.DatetimeIndex(ordered["_split_timestamp"].drop_duplicates().sort_values())
    if len(unique_times) < 3:
        empty = ordered.drop(columns=["_split_timestamp"]).iloc[0:0].copy()
        return empty, empty.copy(), empty.copy()
    train_cut = unique_times[min(len(unique_times) - 1, max(0, int(len(unique_times) * train_fraction) - 1))]
    validation_cut = unique_times[min(len(unique_times) - 1, max(0, int(len(unique_times) * (train_fraction + validation_fraction)) - 1))]
    embargo = pd.Timedelta(hours=embargo_hours)
    stamp = ordered["_split_timestamp"]
    train = ordered.loc[stamp <= train_cut].copy()
    validation = ordered.loc[(stamp > train_cut + embargo) & (stamp <= validation_cut)].copy()
    test = ordered.loc[stamp > validation_cut + embargo].copy()
    return tuple(part.drop(columns=["_split_timestamp"]).reset_index(drop=True) for part in (train, validation, test))


def _metrics(actual, predicted) -> dict:
    return {"mae": round(float(mean_absolute_error(actual, predicted)), 5),
            "rmse": round(float(mean_squared_error(actual, predicted) ** 0.5), 5),
            "samples": int(len(actual))}


def _threshold_event_metrics(actual, predicted, threshold: float) -> dict:
    """Evaluate threshold events using a threshold fixed from training labels only."""
    actual_event = np.asarray(actual, dtype=float) >= threshold
    predicted_event = np.asarray(predicted, dtype=float) >= threshold
    tp = int(np.sum(actual_event & predicted_event))
    fp = int(np.sum(~actual_event & predicted_event))
    fn = int(np.sum(actual_event & ~predicted_event))
    tn = int(np.sum(~actual_event & ~predicted_event))
    return {
        "threshold_mm": round(float(threshold), 5),
        "threshold_definition": "95th percentile of training-period target rainfall; not an official warning threshold",
        "actual_test_events": int(np.sum(actual_event)),
        "predicted_test_events": int(np.sum(predicted_event)),
        "true_positives": tp, "false_positives": fp, "false_negatives": fn, "true_negatives": tn,
        "precision": round(tp / (tp + fp), 5) if tp + fp else None,
        "recall": round(tp / (tp + fn), 5) if tp + fn else None,
        "false_alarm_rate": round(fp / (fp + tn), 5) if fp + tn else None,
        "false_alarms": fp,
        "note": "Threshold-event scores are only estimable when the test period contains actual events; None means denominator is zero.",
    }


def train_and_evaluate(data: pd.DataFrame, output_dir: str | Path, min_train_rows: int = MIN_TRAIN_ROWS,
                       min_test_rows: int = MIN_TEST_ROWS) -> dict:
    """Train fixed baselines and select by chronological validation, never by test scores."""
    output_dir = Path(output_dir)
    report = {"schema_version": SCHEMA_VERSION, "trained_at_utc": datetime.now(timezone.utc).isoformat(),
              "status": "insufficient_data", "models": {}, "operational": False,
              "split": {"method": "chronological_issue_time", "train_fraction": 0.70, "validation_fraction": 0.15,
                        "test_fraction": 0.15, "embargo_hours": 24, "max_fit_rows": MAX_FIT_ROWS}}
    if data.empty or "issue_time_utc" not in data:
        report["message"] = "No aligned supervised rows. Collect timestamped observations before training."
        return report
    test_prediction_frames = []
    for target in [*(f"target_rainfall_{h}h_mm" for h in RAIN_HORIZONS),
                   *(f"target_stage_{h}h_m" for h in STAGE_HORIZONS)]:
        subset = data.dropna(subset=[target]).copy() if target in data else pd.DataFrame()
        feature_columns = RAIN_FEATURE_COLUMNS if target.startswith("target_rainfall") else STAGE_FEATURE_COLUMNS
        if not subset.empty:
            subset = subset.loc[subset[feature_columns].notna().any(axis=1)].copy()
        if len(subset) < min_train_rows + min_test_rows:
            report["models"][target] = {"status": "insufficient_labels", "label_rows": int(len(subset)),
                                        "required_rows": min_train_rows + min_test_rows}
            continue
        train, validation, test = chronological_split(subset)
        if len(train) < min_train_rows or len(test) < min_test_rows or validation.empty:
            report["models"][target] = {"status": "insufficient_chronological_split", "label_rows": len(subset)}
            continue
        x_train, y_train = train[feature_columns], train[target].astype(float)
        x_validation, y_validation = validation[feature_columns], validation[target].astype(float)
        x_test, y_test = test[feature_columns], test[target].astype(float)
        naive_col = "rain_lag_1h_mm" if target.startswith("target_rainfall") else "stage_lag_1h_m"
        train_median = pd.to_numeric(train[naive_col], errors="coerce").median()
        if not np.isfinite(train_median):
            train_median = 0.0
        validation_naive = pd.to_numeric(validation[naive_col], errors="coerce").fillna(train_median).to_numpy()
        test_naive = pd.to_numeric(test[naive_col], errors="coerce").fillna(train_median).to_numpy()
        fit_train = train if len(train) <= MAX_FIT_ROWS else train.iloc[np.linspace(0, len(train) - 1, MAX_FIT_ROWS, dtype=int)].copy()
        candidates = {
            "ridge": make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), Ridge(alpha=1.0)),
            "random_forest": make_pipeline(SimpleImputer(strategy="median"), RandomForestRegressor(
                n_estimators=160, min_samples_leaf=3, max_features=0.9, random_state=42, n_jobs=1)),
        }
        validation_scores = {"persistence_baseline": _metrics(y_validation, validation_naive)}
        test_scores = {"persistence_baseline": _metrics(y_test, test_naive)}
        fitted = {}
        for name, estimator in candidates.items():
            estimator.fit(fit_train[feature_columns], fit_train[target].astype(float))
            val_pred = estimator.predict(x_validation)
            test_pred = estimator.predict(x_test)
            if target.startswith("target_rainfall"):
                val_pred = np.maximum(0, val_pred)
                test_pred = np.maximum(0, test_pred)
            validation_scores[name] = _metrics(y_validation, val_pred)
            test_scores[name] = _metrics(y_test, test_pred)
            fitted[name] = estimator
        selected = min(candidates, key=lambda name: validation_scores[name]["mae"])
        # Fit selected configuration on train+validation only after selection; final test remains untouched.
        train_validation = pd.concat([train, validation], ignore_index=True)
        if len(train_validation) > MAX_FIT_ROWS:
            train_validation = train_validation.iloc[np.linspace(0, len(train_validation) - 1, MAX_FIT_ROWS, dtype=int)].copy()
        final_estimator = candidates[selected]
        final_estimator.fit(train_validation[feature_columns], train_validation[target].astype(float))
        final_pred = final_estimator.predict(x_test)
        if target.startswith("target_rainfall"):
            final_pred = np.maximum(0, final_pred)
        final_metrics = _metrics(y_test, final_pred)
        persistence_metrics = test_scores["persistence_baseline"]
        horizon_hours = int(target.split("_")[2].replace("h", ""))
        prediction_frame = pd.DataFrame({
            "station_id": test["station_id"].astype(str).to_numpy(),
            "issue_time_utc": test["issue_time_utc"].astype(str).to_numpy(),
            "target": target,
            "target_variable": "rainfall_mm" if target.startswith("target_rainfall") else "stage_m",
            "horizon_hours": horizon_hours,
            "observed_value": y_test.to_numpy(),
            "model_prediction": final_pred,
            "persistence_prediction": test_naive,
        })
        test_prediction_frames.append(prediction_frame)
        threshold_metrics = None
        if target.startswith("target_rainfall"):
            event_threshold = float(y_train.quantile(0.95))
            threshold_metrics = {
                "selected_model": _threshold_event_metrics(y_test, final_pred, event_threshold),
                "persistence_baseline": _threshold_event_metrics(y_test, test_naive, event_threshold),
            }
        output_dir.mkdir(parents=True, exist_ok=True)
        artifact = output_dir / f"{target}_{selected}.joblib"
        joblib.dump(final_estimator, artifact)
        report["models"][target] = {
            "status": "evaluated_research_only", "label_rows": len(subset),
            "train_rows": len(train), "fit_rows": len(fit_train), "validation_rows": len(validation), "test_rows": len(test),
            "validation_metrics": validation_scores, "test_metrics": test_scores,
            "selected_model": selected, "selected_model_final_test_metrics": final_metrics,
            "persistence_test_metrics": persistence_metrics,
            "rainfall_threshold_event_metrics": threshold_metrics,
            "test_mae_delta_vs_persistence": round(final_metrics["mae"] - persistence_metrics["mae"], 5),
            "artifact": str(artifact), "selected_using": "validation_mae_only",
            "note": "The chronological test period was not used for model selection. Research evaluation only; independent events and ongoing monitoring are still required."
        }
    if any(item.get("status") == "evaluated_research_only" for item in report["models"].values()):
        report["status"] = "research_models_trained_not_deployment_ready"
        report["warning"] = "Single chronological split is preliminary. Inspect seasonal/event performance and independent data before any live use."
    if test_prediction_frames:
        output_dir.mkdir(parents=True, exist_ok=True)
        pd.concat(test_prediction_frames, ignore_index=True).to_csv(output_dir / "chronological_test_predictions.csv", index=False)
    report_path = output_dir / "training_evaluation.json"
    if report["status"] != "insufficient_data":
        output_dir.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def rows_from_store(db_path: str | Path = DEFAULT_DB) -> pd.DataFrame:
    observations = export_observations(db_path)
    if observations.empty:
        return pd.DataFrame()
    observations = observations.rename(columns={"observed_at_utc": "observed_at"})
    return build_supervised_rows(observations)


def main():
    parser = argparse.ArgumentParser(description="VarshaGuard timestamp-aligned historical forecast pipeline")
    parser.add_argument("--db", default=str(DEFAULT_DB), help="SQLite path (must be persistent in deployment)")
    parser.add_argument("--import-csv", dest="csv_path", help="Import normalized CSV rows")
    parser.add_argument("--collect-live", action="store_true", help="Fetch recent CWC stage/rainfall observations and persist them")
    parser.add_argument("--train", action="store_true", help="Build supervised rows and run chronological research evaluation")
    parser.add_argument("--output-dir", default="models/forecast_research")
    args = parser.parse_args()
    if args.collect_live:
        # Reuse the same CWC source adapter as the live research page; persist raw
        # source timestamps and mark these observations as research inputs.
        from .research import live_prediction as cwc
        from datetime import datetime as _datetime
        metadata = cwc._load_bundle()[1]
        stations = metadata.get("data_quality", {}).get("stations", {})
        now_ist = _datetime.now(timezone.utc).astimezone(cwc.IST)
        station_codes = list(stations)
        collected = []
        for datatype, variable, unit in (("HHS", "stage_m", "m"), ("MPS", "rainfall_mm", "mm")):
            raw_rows = cwc._fetch_type(datatype, station_codes, now_ist)
            parsed = cwc._rows_frame(raw_rows)
            for item in parsed.to_dict("records"):
                value = float(item["value"])
                if variable == "stage_m":
                    meta = stations.get(item["station_code"], {})
                    try:
                        danger = float(meta.get("danger_level_m", float("nan")))
                        highest = float(meta.get("highest_flow_level_m", meta.get("published_highest_flow_level_m", float("nan"))))
                        if not (math.isfinite(danger) and math.isfinite(highest) and danger - 25 <= value <= highest + 2):
                            continue
                    except (TypeError, ValueError):
                        continue
                elif not 0 <= value <= 500:
                    continue
                collected.append({
                    "station_id": item["station_code"],
                    "observed_at": pd.Timestamp(item["timestamp"]).tz_localize("Asia/Kolkata").isoformat(),
                    "source": f"CWC-FFS:{datatype}", "variable": variable, "value": value,
                    "unit": unit, "quality_flag": "good",
                    "source_timestamp": pd.Timestamp(item["timestamp"]).tz_localize("Asia/Kolkata").isoformat(),
                })
        print(json.dumps(ingest_observations(collected, args.db), indent=2))
    if args.csv_path:
        data = pd.read_csv(args.csv_path)
        required = {"station_id", "observed_at", "source", "variable", "value", "unit"}
        missing = required - set(data.columns)
        if missing:
            raise SystemExit(f"CSV missing columns: {sorted(missing)}")
        result = ingest_observations(data.to_dict("records"), args.db)
        print(json.dumps(result, indent=2))
    if args.train:
        rows = rows_from_store(args.db)
        if not rows.empty:
            Path(args.output_dir).mkdir(parents=True, exist_ok=True)
            rows.to_csv(Path(args.output_dir) / "supervised_rows.csv", index=False)
        report = train_and_evaluate(rows, args.output_dir)
        print(json.dumps(report, indent=2))
    if not args.csv_path and not args.train:
        parser.print_help()


if __name__ == "__main__":
    main()
