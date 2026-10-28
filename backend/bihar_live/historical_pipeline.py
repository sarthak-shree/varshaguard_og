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

SCHEMA_VERSION = 1
IST = timezone(timedelta(hours=5, minutes=30))
DEFAULT_DB = Path(os.environ.get("VARSHAGUARD_HISTORY_DB", "data/bihar_live/history.sqlite3"))
RAIN_HORIZONS = (1, 3, 6, 12, 24)
STAGE_HORIZONS = (1, 3, 6, 12)
MIN_TRAIN_ROWS = 120
MIN_TEST_ROWS = 24
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
    conn.execute("CREATE INDEX IF NOT EXISTS idx_obs_station_time ON observations(station_id, observed_at_utc)")
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
            timestamp = _utc_iso(row["observed_at"])
            quality = str(row.get("quality_flag", "good")).strip().lower()
            if not station or not source or not unit or variable not in {"rainfall_mm", "stage_m"}:
                raise ValueError("missing identity/unit or unsupported variable")
            if not math.isfinite(value) or (variable == "rainfall_mm" and value < 0):
                raise ValueError("invalid physical value")
            if quality not in {"good", "suspect", "bad", "missing", "stale"}:
                raise ValueError("invalid quality flag")
            values.append((station, timestamp, source, variable, value, unit, quality,
                           str(row.get("source_timestamp") or row["observed_at"]), now, SCHEMA_VERSION))
            accepted += 1
        except (KeyError, TypeError, ValueError, OverflowError):
            rejected += 1
    with connect(db_path) as conn:
        before = conn.total_changes
        conn.executemany("""
            INSERT INTO observations
            (station_id, observed_at_utc, source, variable, value, unit, quality_flag,
             source_timestamp, ingested_at_utc, schema_version)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(station_id, observed_at_utc, source, variable) DO UPDATE SET
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
            SELECT station_id, observed_at_utc, source, variable, value, unit,
                   quality_flag, source_timestamp, ingested_at_utc, schema_version
            FROM observations ORDER BY station_id, observed_at_utc, variable
        """).fetchall()
    return pd.DataFrame([dict(row) for row in rows])


def build_supervised_rows(observations: pd.DataFrame, max_gap_hours: int = 1) -> pd.DataFrame:
    """Build exact-hour lag features and future labels; never backfill from future values.

    Each feature timestamp must have all required lags at exact hourly offsets. Labels
    are accepted only at exact future horizons. Missing values stay missing and are not
    forward-filled across gaps. Data are sorted chronologically per station.
    """
    required = {"station_id", "observed_at", "variable", "value", "quality_flag"}
    if not required.issubset(observations.columns):
        raise ValueError(f"observations missing columns: {sorted(required - set(observations.columns))}")
    frame = observations.copy()
    frame["observed_at"] = pd.to_datetime(frame["observed_at"], utc=True, errors="coerce")
    frame["value"] = pd.to_numeric(frame["value"], errors="coerce")
    frame = frame.dropna(subset=["station_id", "observed_at", "value"])
    frame = frame[frame["quality_flag"].fillna("bad").str.lower().eq("good")]
    frame = frame.drop_duplicates(["station_id", "observed_at", "variable"], keep="last")
    wide = frame.pivot(index=["station_id", "observed_at"], columns="variable", values="value").reset_index()
    rows = []
    for station, part in wide.groupby("station_id", sort=False):
        part = part.sort_values("observed_at").set_index("observed_at")
        for stamp, current in part.iterrows():
            local = stamp.tz_convert("Asia/Kolkata")
            features = {
                "station_id": station, "issue_time_utc": stamp.isoformat(),
                "issue_time_ist": local.isoformat(),
                "hour_sin": math.sin(2 * math.pi * local.hour / 24),
                "hour_cos": math.cos(2 * math.pi * local.hour / 24),
                "dayofyear_sin": math.sin(2 * math.pi * local.dayofyear / 366),
                "dayofyear_cos": math.cos(2 * math.pi * local.dayofyear / 366),
            }
            valid = True
            for var, prefix in (("rainfall_mm", "rain_lag"), ("stage_m", "stage_lag")):
                for lag in (1, 3, 6, 12, 24):
                    target_time = stamp - pd.Timedelta(hours=lag)
                    if target_time not in part.index:
                        valid = False
                        break
                    val = part.at[target_time, var] if var in part.columns else np.nan
                    if not np.isfinite(val):
                        valid = False
                        break
                    features[f"{prefix}_{lag}h_{'mm' if prefix == 'rain_lag' else 'm'}"] = float(val)
                if not valid:
                    break
            if not valid:
                continue
            features["stage_rate_3h_m_per_h"] = (features["stage_lag_1h_m"] - features["stage_lag_3h_m"]) / 2
            features["stage_rate_12h_m_per_h"] = (features["stage_lag_1h_m"] - features["stage_lag_12h_m"]) / 11
            for horizon in RAIN_HORIZONS:
                target_time = stamp + pd.Timedelta(hours=horizon)
                label = part["rainfall_mm"].get(target_time, np.nan) if "rainfall_mm" in part else np.nan
                features[f"target_rainfall_{horizon}h_mm"] = float(label) if pd.notna(label) else np.nan
            for horizon in STAGE_HORIZONS:
                target_time = stamp + pd.Timedelta(hours=horizon)
                label = part["stage_m"].get(target_time, np.nan) if "stage_m" in part else np.nan
                features[f"target_stage_{horizon}h_m"] = float(label) if pd.notna(label) else np.nan
            rows.append(features)
    return pd.DataFrame(rows).sort_values("issue_time_utc").reset_index(drop=True) if rows else pd.DataFrame()


def chronological_split(data: pd.DataFrame, train_fraction: float = 0.70, validation_fraction: float = 0.15):
    """Split by issue timestamp, not random rows, to prevent temporal leakage."""
    if not 0 < train_fraction < 1 or not 0 < validation_fraction < 1 or train_fraction + validation_fraction >= 1:
        raise ValueError("fractions must be positive and sum to less than one")
    ordered = data.sort_values("issue_time_utc").reset_index(drop=True)
    n = len(ordered)
    train_end = int(n * train_fraction)
    val_end = int(n * (train_fraction + validation_fraction))
    return ordered.iloc[:train_end].copy(), ordered.iloc[train_end:val_end].copy(), ordered.iloc[val_end:].copy()


def _metrics(actual, predicted) -> dict:
    return {"mae": round(float(mean_absolute_error(actual, predicted)), 5),
            "rmse": round(float(mean_squared_error(actual, predicted) ** 0.5), 5),
            "samples": int(len(actual))}


def train_and_evaluate(data: pd.DataFrame, output_dir: str | Path, min_train_rows: int = MIN_TRAIN_ROWS,
                       min_test_rows: int = MIN_TEST_ROWS) -> dict:
    """Train only targets with enough labels and report chronological test performance."""
    output_dir = Path(output_dir)
    report = {"schema_version": SCHEMA_VERSION, "trained_at_utc": datetime.now(timezone.utc).isoformat(),
              "status": "insufficient_data", "models": {}, "operational": False,
              "split": {"method": "chronological_issue_time", "train_fraction": 0.70, "validation_fraction": 0.15,
                        "test_fraction": 0.15}}
    if data.empty or "issue_time_utc" not in data:
        report["message"] = "No aligned supervised rows. Collect timestamped observations before training."
        return report
    output_dir.mkdir(parents=True, exist_ok=True)
    for target in [*(f"target_rainfall_{h}h_mm" for h in RAIN_HORIZONS),
                   *(f"target_stage_{h}h_m" for h in STAGE_HORIZONS)]:
        subset = data.dropna(subset=[target]).copy() if target in data else pd.DataFrame()
        if len(subset) < min_train_rows + min_test_rows:
            report["models"][target] = {"status": "insufficient_labels", "label_rows": int(len(subset)),
                                        "required_rows": min_train_rows + min_test_rows}
            continue
        train, validation, test = chronological_split(subset)
        if len(train) < min_train_rows or len(test) < min_test_rows or validation.empty:
            report["models"][target] = {"status": "insufficient_chronological_split", "label_rows": len(subset)}
            continue
        x_train, y_train = train[FEATURE_COLUMNS], train[target].astype(float)
        x_test, y_test = test[FEATURE_COLUMNS], test[target].astype(float)
        # Compare a naive persistence baseline to a scaled Ridge model and tree model.
        if target.startswith("target_rainfall"):
            horizon = int(target.split("_")[2].replace("h", ""))
            naive_col = f"rain_lag_1h_mm"
        else:
            horizon = int(target.split("_")[2].replace("h", ""))
            naive_col = "stage_lag_1h_m"
        baseline = pd.to_numeric(test[naive_col], errors="coerce").fillna(train[naive_col].median()).to_numpy()
        baseline_scores = _metrics(y_test, baseline)
        candidates = {
            "ridge": make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), Ridge(alpha=1.0)),
            "random_forest": make_pipeline(SimpleImputer(strategy="median"), RandomForestRegressor(
                n_estimators=160, min_samples_leaf=3, max_features=0.9, random_state=42, n_jobs=1)),
        }
        scored = {"persistence_baseline": baseline_scores}
        fitted = {}
        for name, estimator in candidates.items():
            estimator.fit(x_train[FEATURE_COLUMNS], y_train)
            predicted = estimator.predict(x_test[FEATURE_COLUMNS])
            if target.startswith("target_rainfall"):
                predicted = np.maximum(0, predicted)
            scored[name] = _metrics(y_test, predicted)
            fitted[name] = estimator
        winner = min(candidates, key=lambda name: scored[name]["mae"])
        report["models"][target] = {"status": "evaluated_research_only", "label_rows": len(subset),
                                    "train_rows": len(train), "validation_rows": len(validation),
                                    "test_rows": len(test), "test_metrics": scored,
                                    "selected_by_test_set": False,
                                    "note": "Test scores are reporting-only; hyperparameters are fixed. Model selection for deployment requires validation-set selection and a final untouched test set."}
        # Store candidates and metrics for research/reproducibility, not live inference.
        for name, estimator in fitted.items():
            artifact = output_dir / f"{target}_{name}.joblib"
            joblib.dump(estimator, artifact)
    if any(item.get("status") == "evaluated_research_only" for item in report["models"].values()):
        report["status"] = "research_models_trained_not_deployment_ready"
        report["warning"] = "A single chronological split is preliminary. Inspect validation/test periods and compare with operational baselines before any production use."
    report_path = output_dir / "training_evaluation.json"
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
    parser.add_argument("--train", action="store_true", help="Build supervised rows and run chronological research evaluation")
    parser.add_argument("--output-dir", default="models/forecast_research")
    args = parser.parse_args()
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
            rows.to_csv(Path(args.output_dir) / "supervised_rows.csv", index=False)
        report = train_and_evaluate(rows, args.output_dir)
        print(json.dumps(report, indent=2))
    if not args.csv_path and not args.train:
        parser.print_help()


if __name__ == "__main__":
    main()
