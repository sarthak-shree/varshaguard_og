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
    """Build exact-hour lag features and exact future labels without interpolation.

    Rainfall-only sources can support rainfall targets and stage-only sources can support
    stage targets. Cross-source joins happen only when an explicit station mapping has
    produced the same canonical station ID. Missing features are left missing for a
    train-fitted imputer; missing future labels are never imputed.
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
    # A canonical station/time/variable with conflicting readings is ambiguous; reject it.
    conflict_keys = []
    for key, group in frame.groupby(["station_id", "observed_at", "variable"], dropna=False):
        if group["value"].nunique(dropna=False) > 1:
            conflict_keys.append(key)
    if conflict_keys:
        conflict_index = pd.MultiIndex.from_frame(frame[["station_id", "observed_at", "variable"]])
        rejected = pd.MultiIndex.from_tuples(conflict_keys, names=["station_id", "observed_at", "variable"])
        frame = frame.loc[~conflict_index.isin(rejected)].copy()
    frame = frame.drop_duplicates(["station_id", "observed_at", "variable"], keep="first")
    rows = []
    for station, station_rows in frame.groupby("station_id", sort=False):
        series = {
            variable: group.set_index("observed_at")["value"].sort_index()
            for variable, group in station_rows.groupby("variable", sort=False)
        }
        stage_series = series.get("stage_m", pd.Series(dtype=float))
        rain_series = series.get("rainfall_mm", pd.Series(dtype=float))
        issue_times = sorted(set(stage_series.index).union(set(rain_series.index)))
        for stamp in issue_times:
            local = stamp.tz_convert("Asia/Kolkata")
            features = {
                "station_id": station, "issue_time_utc": stamp.isoformat(),
                "issue_time_ist": local.isoformat(),
                "hour_sin": math.sin(2 * math.pi * local.hour / 24),
                "hour_cos": math.cos(2 * math.pi * local.hour / 24),
                "dayofyear_sin": math.sin(2 * math.pi * local.dayofyear / 366),
                "dayofyear_cos": math.cos(2 * math.pi * local.dayofyear / 366),
            }
            for lag in (1, 3, 6, 12, 24):
                stage_value = stage_series.get(stamp - pd.Timedelta(hours=lag), np.nan)
                rain_value = rain_series.get(stamp - pd.Timedelta(hours=lag), np.nan)
                features[f"stage_lag_{lag}h_m"] = float(stage_value) if pd.notna(stage_value) else np.nan
                features[f"rain_lag_{lag}h_mm"] = float(rain_value) if pd.notna(rain_value) else np.nan
            features["stage_rate_3h_m_per_h"] = (
                (features["stage_lag_1h_m"] - features["stage_lag_3h_m"]) / 2
                if pd.notna(features["stage_lag_1h_m"]) and pd.notna(features["stage_lag_3h_m"]) else np.nan
            )
            features["stage_rate_12h_m_per_h"] = (
                (features["stage_lag_1h_m"] - features["stage_lag_12h_m"]) / 11
                if pd.notna(features["stage_lag_1h_m"]) and pd.notna(features["stage_lag_12h_m"]) else np.nan
            )
            for horizon in RAIN_HORIZONS:
                label = rain_series.get(stamp + pd.Timedelta(hours=horizon), np.nan)
                features[f"target_rainfall_{horizon}h_mm"] = float(label) if pd.notna(label) else np.nan
            for horizon in STAGE_HORIZONS:
                label = stage_series.get(stamp + pd.Timedelta(hours=horizon), np.nan)
                features[f"target_stage_{horizon}h_m"] = float(label) if pd.notna(label) else np.nan
            # Keep a row only when at least one usable input history exists.
            if any(pd.notna(features[f"rain_lag_{lag}h_mm"]) for lag in (1, 3, 6, 12, 24)) or any(
                pd.notna(features[f"stage_lag_{lag}h_m"]) for lag in (1, 3, 6, 12, 24)
            ):
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
    """Train fixed baselines and select by chronological validation, never by test scores."""
    output_dir = Path(output_dir)
    report = {"schema_version": SCHEMA_VERSION, "trained_at_utc": datetime.now(timezone.utc).isoformat(),
              "status": "insufficient_data", "models": {}, "operational": False,
              "split": {"method": "chronological_issue_time", "train_fraction": 0.70, "validation_fraction": 0.15,
                        "test_fraction": 0.15}}
    if data.empty or "issue_time_utc" not in data:
        report["message"] = "No aligned supervised rows. Collect timestamped observations before training."
        return report
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
        x_validation, y_validation = validation[FEATURE_COLUMNS], validation[target].astype(float)
        x_test, y_test = test[FEATURE_COLUMNS], test[target].astype(float)
        naive_col = "rain_lag_1h_mm" if target.startswith("target_rainfall") else "stage_lag_1h_m"
        train_median = pd.to_numeric(train[naive_col], errors="coerce").median()
        if not np.isfinite(train_median):
            train_median = 0.0
        validation_naive = pd.to_numeric(validation[naive_col], errors="coerce").fillna(train_median).to_numpy()
        test_naive = pd.to_numeric(test[naive_col], errors="coerce").fillna(train_median).to_numpy()
        candidates = {
            "ridge": make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), Ridge(alpha=1.0)),
            "random_forest": make_pipeline(SimpleImputer(strategy="median"), RandomForestRegressor(
                n_estimators=160, min_samples_leaf=3, max_features=0.9, random_state=42, n_jobs=1)),
        }
        validation_scores = {"persistence_baseline": _metrics(y_validation, validation_naive)}
        test_scores = {"persistence_baseline": _metrics(y_test, test_naive)}
        fitted = {}
        for name, estimator in candidates.items():
            estimator.fit(x_train, y_train)
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
        final_estimator = candidates[selected]
        final_estimator.fit(train_validation[FEATURE_COLUMNS], train_validation[target].astype(float))
        final_pred = final_estimator.predict(x_test)
        if target.startswith("target_rainfall"):
            final_pred = np.maximum(0, final_pred)
        final_metrics = _metrics(y_test, final_pred)
        persistence_metrics = test_scores["persistence_baseline"]
        output_dir.mkdir(parents=True, exist_ok=True)
        artifact = output_dir / f"{target}_{selected}.joblib"
        joblib.dump(final_estimator, artifact)
        report["models"][target] = {
            "status": "evaluated_research_only", "label_rows": len(subset),
            "train_rows": len(train), "validation_rows": len(validation), "test_rows": len(test),
            "validation_metrics": validation_scores, "test_metrics": test_scores,
            "selected_model": selected, "selected_model_final_test_metrics": final_metrics,
            "persistence_test_metrics": persistence_metrics,
            "test_mae_delta_vs_persistence": round(final_metrics["mae"] - persistence_metrics["mae"], 5),
            "artifact": str(artifact), "selected_using": "validation_mae_only",
            "note": "The chronological test period was not used for model selection. Research evaluation only; independent events and ongoing monitoring are still required."
        }
    if any(item.get("status") == "evaluated_research_only" for item in report["models"].values()):
        report["status"] = "research_models_trained_not_deployment_ready"
        report["warning"] = "Single chronological split is preliminary. Inspect seasonal/event performance and independent data before any live use."
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
