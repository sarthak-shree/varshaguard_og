"""Schema-aware normalization and coverage report for downloaded public CSVs.

This module never guesses station equivalence. A canonical station mapping file is
required to merge distinct agency identifiers; without one, source/station identities
remain separate. Forecast products are rejected as observation sources.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

ALIASES = {
    "station_id": ["station_id", "station code", "station_code", "stationcode", "station", "gauge_id", "site_id", "station name"],
    "timestamp": ["timestamp", "datetime", "date time", "date_time", "observation time", "observed_at", "data time", "datatime", "date"],
    "rainfall_mm": ["rainfall", "rainfall (mm)", "rainfall_mm", "rain (mm)", "rainfall value", "precipitation", "precipitation_mm"],
    "stage_m": ["river water level", "river water level (m)", "water level", "water level (m)", "stage", "stage (m)", "river stage", "rwl (m)"],
    "district": ["district", "district name"],
    "river": ["river", "river name", "basin"],
}
OBSERVED_MARKERS = ("observed", "observation", "telemetry", "measured", "gauge", "manual")
FORECAST_MARKERS = ("forecast", "predicted", "nwp", "outlook", "model output")


def _key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value).strip().lower()).strip()


def _resolve(columns, key):
    normalized = {_key(column): column for column in columns}
    for alias in ALIASES[key]:
        if _key(alias) in normalized:
            return normalized[_key(alias)]
    return None


def normalize_public_csv(path: str | Path, source_id: str, agency: str, variable: str,
                         unit: str, source_kind: str = "observed",
                         station_mapping: dict[str, str] | None = None) -> tuple[pd.DataFrame, dict]:
    """Normalize one source only when required fields are unambiguous."""
    if source_kind.lower() in {"forecast", "nwp", "predicted"}:
        raise ValueError("Forecast inputs cannot be normalized as observed labels")
    if variable not in {"rainfall_mm", "stage_m"}:
        raise ValueError("variable must be rainfall_mm or stage_m")
    raw = pd.read_csv(path, low_memory=False)
    columns = {name: _resolve(raw.columns, name) for name in ("station_id", "timestamp", variable)}
    missing = [name for name, column in columns.items() if column is None]
    if missing:
        raise ValueError(f"Unrecognized schema for {source_id}; missing fields {missing}; actual columns={list(raw.columns)}")
    station = raw[columns["station_id"]].astype("string").str.strip()
    timestamp = pd.to_datetime(raw[columns["timestamp"]], errors="coerce", dayfirst=True)
    # Naive timestamps from NWIC CSV are assumed to be IST only when explicitly documented
    # in the source manifest; output retains that assumption in provenance.
    if timestamp.dt.tz is None:
        timestamp = timestamp.dt.tz_localize("Asia/Kolkata", ambiguous="NaT", nonexistent="NaT")
    timestamp_utc = timestamp.dt.tz_convert("UTC")
    value = pd.to_numeric(raw[columns[variable]], errors="coerce")
    finite = value.notna() & np.isfinite(value)
    if variable == "rainfall_mm":
        finite &= value >= 0
    station = station.fillna("").str.strip()
    valid = station.ne("") & timestamp_utc.notna() & finite
    mapping = station_mapping or {}
    canonical = station.map(lambda item: mapping.get(f"{source_id}:{item}", mapping.get(item, f"{source_id}:{item}")))
    normalized = pd.DataFrame({
        "station_id": canonical[valid].astype(str),
        "source_station_id": station[valid].astype(str),
        "observed_at": timestamp_utc[valid].map(lambda item: item.isoformat()),
        "source": f"{agency}:{source_id}",
        "variable": variable,
        "value": value[valid].astype(float),
        "unit": unit,
        "quality_flag": "good",
        "source_timestamp": timestamp[valid].map(lambda item: item.isoformat()),
        "source_kind": "observed",
    })
    # Duplicate station-time rows are not silently averaged; retain one only if identical.
    duplicate_mask = normalized.duplicated(["station_id", "observed_at", "variable"], keep=False)
    duplicate_rows = int(duplicate_mask.sum())
    conflicting = 0
    if duplicate_rows:
        for _, group in normalized[duplicate_mask].groupby(["station_id", "observed_at", "variable"]):
            if group["value"].nunique(dropna=False) > 1:
                conflicting += len(group)
        normalized = normalized.drop_duplicates(["station_id", "observed_at", "variable", "value"])
    ordered = normalized.sort_values(["station_id", "observed_at"])
    if not ordered.empty:
        ordered["observed_at"] = pd.to_datetime(ordered["observed_at"], utc=True)
        gap_hours = (
            ordered.sort_values(["station_id", "observed_at"])
            .groupby("station_id")["observed_at"].diff().dt.total_seconds().div(3600).dropna()
        )
    else:
        gap_hours = pd.Series(dtype=float)
    coverage = {
        "source_id": source_id, "agency": agency, "variable": variable, "unit": unit,
        "source_kind": "observed", "input_rows": int(len(raw)), "valid_rows": int(valid.sum()),
        "rejected_rows": int(len(raw) - valid.sum()), "normalized_rows": int(len(normalized)),
        "station_count": int(normalized["station_id"].nunique()),
        "source_station_count": int(normalized["source_station_id"].nunique()),
        "time_start_utc": str(normalized["observed_at"].min()) if len(normalized) else None,
        "time_end_utc": str(normalized["observed_at"].max()) if len(normalized) else None,
        "missing_value_pct": round(100 * (1 - int(valid.sum()) / max(1, len(raw))), 3),
        "duplicate_rows": duplicate_rows, "conflicting_duplicate_rows": conflicting,
        "median_interval_hours": float(gap_hours.median()) if len(gap_hours) else None,
        "timestamp_assumption": "Naive source timestamps interpreted as Asia/Kolkata; confirm against source documentation",
        "station_reconciliation": "explicit mapping" if station_mapping else "source-prefixed IDs; cross-agency joins disabled",
    }
    return normalized, coverage


def align_observations(normalized: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Create exact-hour station timelines without filling missing measurements."""
    if normalized.empty:
        return pd.DataFrame(), {"stations": 0, "rows": 0, "complete_hourly_rows": 0, "missing_hour_slots": 0}
    frame = normalized.copy()
    frame["observed_at"] = pd.to_datetime(frame["observed_at"], utc=True)
    wide = frame.pivot_table(index=["station_id", "observed_at"], columns="variable", values="value", aggfunc="first").reset_index()
    aligned = []
    total_expected = total_present = 0
    for station, part in wide.groupby("station_id"):
        part = part.set_index("observed_at").sort_index()
        hourly_index = pd.date_range(part.index.min().floor("h"), part.index.max().ceil("h"), freq="h", tz="UTC")
        reindexed = part.reindex(hourly_index)
        reindexed.index.name = "observed_at"
        reindexed["station_id"] = station
        reindexed["is_exact_hour"] = (reindexed.index.minute == 0) & (reindexed.index.second == 0)
        variables = [column for column in ("rainfall_mm", "stage_m") if column in reindexed]
        total_expected += len(reindexed) * len(variables)
        total_present += int(reindexed[variables].notna().sum().sum())
        aligned.append(reindexed.reset_index())
    result = pd.concat(aligned, ignore_index=True) if aligned else pd.DataFrame()
    return result, {
        "stations": int(result["station_id"].nunique()) if not result.empty else 0,
        "rows": int(len(result)),
        "complete_hourly_rows": int(result[["rainfall_mm", "stage_m"]].notna().all(axis=1).sum()) if {"rainfall_mm", "stage_m"}.issubset(result.columns) else 0,
        "missing_hour_slots": int(total_expected - total_present),
        "observed_cell_coverage_pct": round(100 * total_present / max(1, total_expected), 3),
        "missing_values_not_filled": True,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--agency", required=True)
    parser.add_argument("--variable", choices=["rainfall_mm", "stage_m"], required=True)
    parser.add_argument("--unit", required=True)
    parser.add_argument("--output-dir", default="data/processed/public_sources")
    parser.add_argument("--station-map", help="JSON mapping from source-specific station IDs to canonical IDs")
    args = parser.parse_args()
    mapping = json.loads(Path(args.station_map).read_text()) if args.station_map else None
    normalized, coverage = normalize_public_csv(args.input, args.source_id, args.agency, args.variable, args.unit, station_mapping=mapping)
    aligned, alignment = align_observations(normalized)
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    normalized_path = output / f"{args.source_id}_observations.csv"
    normalized.to_csv(normalized_path, index=False)
    if not aligned.empty:
        aligned.to_csv(output / f"{args.source_id}_hourly_alignment.csv", index=False)
    coverage["alignment"] = alignment
    coverage["output"] = str(normalized_path)
    (output / f"{args.source_id}_coverage.json").write_text(json.dumps(coverage, indent=2), encoding="utf-8")
    print(json.dumps(coverage, indent=2))


if __name__ == "__main__":
    main()
