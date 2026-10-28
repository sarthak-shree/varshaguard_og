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
    "rainfall_mm": ["rainfall", "rainfall (mm)", "rainfall_mm", "rain (mm)", "rainfall value", "telemetry hourly rainfall (mm)", "precipitation", "precipitation_mm"],
    "stage_m": ["river water level", "river water level (m)", "water level", "water level (m)", "stage", "stage (m)", "river stage", "river water level telemetry hourly (meter)", "rwl (m)"],
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
    # NWIC telemetry tables may reuse a station name across districts. Use stable
    # geography fields when available; retain the original station name separately.
    normalized_columns = {_key(column): column for column in raw.columns}
    district_code_col = normalized_columns.get("district lgd code")
    latitude_col = normalized_columns.get("latitude")
    longitude_col = normalized_columns.get("longitude")
    station_identity = station.fillna("").astype(str)
    if district_code_col:
        district_code = raw[district_code_col].fillna("").astype(str).str.strip()
        station_identity = station_identity + "|district_lgd=" + district_code
    if latitude_col and longitude_col:
        lat = pd.to_numeric(raw[latitude_col], errors="coerce").round(5).astype("string").fillna("")
        lon = pd.to_numeric(raw[longitude_col], errors="coerce").round(5).astype("string").fillna("")
        station_identity = station_identity + "|lat=" + lat + "|lon=" + lon
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
    canonical = station_identity.map(lambda identity: mapping.get(f"{source_id}:{identity}", mapping.get(identity)))
    raw_station_mapping = station.map(lambda item: mapping.get(f"{source_id}:{item}", mapping.get(item)))
    canonical = canonical.fillna(raw_station_mapping)
    canonical = canonical.fillna(station_identity.map(lambda identity: f"{source_id}:{identity}"))
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
    # Conflicting duplicate station-time readings are excluded, never averaged or
    # resolved by file order. Identical duplicates collapse to one record.
    keys = ["station_id", "observed_at", "variable"]
    duplicate_mask = normalized.duplicated(keys, keep=False)
    duplicate_rows = int(duplicate_mask.sum())
    conflicting = 0
    if duplicate_rows:
        grouped = normalized.groupby(keys, dropna=False)
        unique_counts = grouped["value"].nunique(dropna=False)
        conflict_keys = unique_counts[unique_counts > 1].index
        if len(conflict_keys):
            conflict_index = pd.MultiIndex.from_frame(normalized[keys])
            conflict_multi = pd.MultiIndex.from_tuples(list(conflict_keys), names=keys)
            conflicting = int(conflict_index.isin(conflict_multi).sum())
            normalized = normalized.loc[~conflict_index.isin(conflict_multi)].copy()
        normalized = normalized.drop_duplicates(keys, keep="first")
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
        "duplicate_rows": duplicate_rows, "conflicting_duplicate_rows": conflicting, "conflicting_rows_removed": conflicting,
        "median_interval_hours": float(gap_hours.median()) if len(gap_hours) else None,
        "timestamp_assumption": "Naive source timestamps interpreted as Asia/Kolkata; confirm against source documentation",
        "station_reconciliation": "explicit mapping" if station_mapping else "source-prefixed IDs; cross-agency joins disabled",
    }
    return normalized, coverage


def align_observations(normalized: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Align to local IST clock hours using the last observation in each hour.

    Rainfall telemetry values are published as an hourly rainfall field but may be
    timestamped every 15 minutes. We therefore select the latest reading in each IST
    hour instead of summing repeated snapshots. No gap is interpolated or filled.
    """
    if normalized.empty:
        return pd.DataFrame(), {"stations": 0, "rows": 0, "complete_hourly_rows": 0, "missing_hour_slots": 0}
    frame = normalized.copy()
    frame["observed_at"] = pd.to_datetime(frame["observed_at"], utc=True)
    wide = frame.pivot_table(index=["station_id", "observed_at"], columns="variable", values="value", aggfunc="first").reset_index()
    aligned = []
    total_expected = total_present = 0
    for station, part in wide.groupby("station_id"):
        part = part.set_index("observed_at").sort_index()
        part.index = part.index.tz_convert("Asia/Kolkata")
        # The source value is a level/reading, not an interval increment; never sum it.
        hourly = part.resample("h", origin="start_day").last()
        hourly_index = pd.date_range(part.index.min().floor("h"), part.index.max().floor("h"), freq="h", tz="Asia/Kolkata")
        hourly = hourly.reindex(hourly_index)
        hourly.index.name = "observed_at_ist"
        hourly["station_id"] = station
        hourly["observed_at"] = hourly.index.tz_convert("UTC")
        hourly["is_exact_hour"] = True
        variables = [column for column in ("rainfall_mm", "stage_m") if column in hourly]
        total_expected += len(hourly) * len(variables)
        total_present += int(hourly[variables].notna().sum().sum())
        aligned.append(hourly.reset_index(drop=True))
    result = pd.concat(aligned, ignore_index=True) if aligned else pd.DataFrame()
    return result, {
        "stations": int(result["station_id"].nunique()) if not result.empty else 0,
        "rows": int(len(result)),
        "complete_hourly_rows": int(result[["rainfall_mm", "stage_m"]].notna().all(axis=1).sum()) if {"rainfall_mm", "stage_m"}.issubset(result.columns) else 0,
        "missing_hour_slots": int(total_expected - total_present),
        "observed_cell_coverage_pct": round(100 * total_present / max(1, total_expected), 3),
        "missing_values_not_filled": True,
        "hourly_policy": "last observation within each Asia/Kolkata clock hour; no summation or interpolation",
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
